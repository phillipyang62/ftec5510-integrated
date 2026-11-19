(() => {
  "use strict";
  if (document.body.dataset.integrated !== "true") return;

  const find = (selector) => document.querySelector(selector);
  const label = (zh, en) => document.documentElement.lang === "en" ? en : zh;
  const button = (text, style, action) => {
    const element = document.createElement("button");
    element.type = "button";
    element.className = style;
    element.textContent = text;
    if (action) element.addEventListener("click", action);
    return element;
  };
  const nav = find('[data-screen-target="questionnaire"]');
  const screen = find("#screen-questionnaire");
  const body = find("#questionnaire-body");
  const status = find("#questionnaire-status");
  let bank;
  let result;
  let step = 0;
  let loading = false;
  let saving = false;
  let consent = false;
  let changes = 0;
  const answers = new Map();

  async function loadBank() {
    if (bank || loading) return;
    loading = true;
    status.textContent = label("正在读取问卷…", "Loading questionnaire…");
    try {
      const response = await fetch("/api/questionnaire");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      bank = await response.json();
      render();
    } catch (error) {
      status.textContent = label(`问卷暂不可用 · ${error.message}`, `Questionnaire unavailable · ${error.message}`);
      body.replaceChildren(button(label("重试", "Retry"), "da-secondary", loadBank));
    } finally {
      loading = false;
    }
  }

  function questionField(question) {
    const group = document.createElement("fieldset");
    const title = document.createElement("legend");
    title.textContent = `${question.id} · ${question.text}`;
    group.append(title);
    for (const option of question.options) {
      const line = document.createElement("label");
      const input = document.createElement("input");
      input.type = question.multiple ? "checkbox" : "radio";
      input.name = question.id;
      input.value = option.key;
      const current = answers.get(question.id);
      input.checked = question.multiple ? Boolean(current?.includes(option.key)) : current === option.key;
      input.addEventListener("change", () => {
        const previous = answers.get(question.id);
        if (previous !== undefined) changes++;
        if (question.multiple) {
          const checked = [...group.querySelectorAll("input:checked")].map((item) => item.value);
          if (checked.length) answers.set(question.id, checked);
          else answers.delete(question.id);
        } else {
          answers.set(question.id, input.value);
        }
      });
      line.append(input, `${option.key}. ${option.text}`);
      group.append(line);
    }
    return group;
  }

  function showResult() {
    const assessment = result.assessment;
    status.textContent = label("测评结果已同步到中台和 AI。", "Assessment synced to middle office and AI.");
    const headline = document.createElement("h2");
    headline.textContent = label(`风险等级 ${assessment.risk_level} · 产品上限 ${assessment.product_cap}`,
      `Risk level ${assessment.risk_level} · Product ceiling ${assessment.product_cap}`);
    const scores = document.createElement("p");
    scores.textContent = Object.entries(assessment.dimensions)
      .map(([code, score]) => `${bank.dimensions[code]} ${score}`).join(" · ");
    const actions = document.createElement("div");
    actions.className = "da-question-actions";
    actions.append(
      button(label("去聊天", "Open assistant"), "da-primary", () => find('[data-screen-target="assistant"]').click()),
      button(label("重新测评", "Retake"), "da-secondary", () => {
        result = null;
        answers.clear();
        changes = step = 0;
        consent = false;
        render();
      }),
    );
    body.replaceChildren(headline, scores, actions);
  }

  async function save(form) {
    if (saving || !consent) return;
    saving = true;
    form.querySelectorAll("button, input").forEach((control) => { control.disabled = true; });
    status.textContent = label("正在评分和同步…", "Scoring and syncing…");
    try {
      const response = await fetch("/api/questionnaire", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
          questionnaire_version: bank.questionnaire_version,
          answers: bank.questions.map(({ id }) => ({ qid: id, value: answers.get(id) })),
          quality_signals: { answer_changes: changes },
          consent: { assessment: true, ai_processing: true },
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
      result = data;
      showResult();
    } catch (error) {
      status.textContent = label(`提交失败 · ${error.message}`, `Submission failed · ${error.message}`);
      form.querySelectorAll("button, input").forEach((control) => { control.disabled = false; });
    } finally {
      saving = false;
    }
  }

  function render() {
    if (!bank || saving) return;
    if (result) { showResult(); return; }
    const groups = Object.keys(bank.dimensions);
    const code = groups[step];
    const questions = bank.questions.filter(({ id }) => id.startsWith(code));
    const last = step === groups.length - 1;
    const form = document.createElement("form");
    const heading = document.createElement("h2");
    heading.textContent = `${step + 1}/${groups.length} · ${bank.dimensions[code]}`;
    form.append(heading, ...questions.map(questionField));
    status.textContent = label("请按实际情况填写。提交后仅保存评分结果。", "Answer based on your situation. Only derived scores are saved.");
    if (last) {
      const line = document.createElement("label");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.required = true;
      check.checked = consent;
      check.addEventListener("change", () => { consent = check.checked; });
      line.append(check, label("我同意用本次得分生成风险画像和 AI 解释。", "I agree to use the scores for my risk profile and AI explanations."));
      form.append(line);
    }
    const actions = document.createElement("div");
    actions.className = "da-question-actions";
    const advance = button(last ? label("提交测评", "Submit assessment") : label("下一组", "Next"), "da-primary");
    advance.type = "submit";
    actions.append(advance);
    if (step > 0) actions.append(button(label("上一组", "Back"), "da-secondary", () => { step--; render(); }));
    actions.append(button(label("稍后填写", "Skip for now"), "da-secondary", () => find('[data-screen-target="compare"]').click()));
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const missing = questions.find(({ id }) => !answers.has(id));
      if (missing) {
        status.textContent = label(`请先回答 ${missing.id}。`, `Please answer ${missing.id}.`);
        form.elements.namedItem(missing.id)[0]?.focus();
      } else if (last) save(form);
      else { step++; render(); }
    });
    body.replaceChildren(form);
  }

  function localize() {
    const title = label("风险问卷", "Risk questionnaire");
    nav.querySelector("span").textContent = title;
    find("#questionnaire-title").textContent = title;
    if (!screen.hidden) render();
  }

  nav.hidden = false;
  nav.addEventListener("click", () => { if (bank) render(); else loadBank(); });
  document.addEventListener("harbor-language", localize);
  localize();
  fetch("/api/profile").then(async (response) => {
    if (response.ok) {
      const profile = await response.json();
      if (profile.assessment) result = profile;
    } else if (response.status === 404 && !find("#screen-compare").hidden) {
      nav.click();
    }
  }).catch(() => {});
})();
