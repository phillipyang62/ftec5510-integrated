(() => {
  "use strict";
  const accountName = document.body.dataset.accountName;
  if (!accountName) return;

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

  async function request(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { ...options.headers, "X-Harbor-Account": accountName } });
    if (response.status === 401) location.reload();
    return response;
  }

  async function loadBank() {
    if (bank || loading) return;
    loading = true;
    status.textContent = label("正在读取问卷…", "Loading questionnaire…");
    try {
      const response = await request("/api/questionnaire");
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
    title.textContent = question.text;
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
    status.textContent = "";
    const headline = document.createElement("h2");
    headline.textContent = label("测评结果", "Assessment result");
    const summary = document.createElement("dl");
    summary.className = "da-assessment-summary";
    for (const [name, value] of [
      [label("综合分", "Overall score"), `${assessment.rai} / 100`],
      [label("风险等级", "Risk level"), assessment.risk_level],
      [label("产品上限", "Product ceiling"), assessment.product_cap],
    ]) {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      const score = document.createElement("dd");
      term.textContent = name;
      score.textContent = value;
      item.append(term, score);
      summary.append(item);
    }
    const details = document.createElement("details");
    details.className = "da-assessment-details";
    const expand = document.createElement("summary");
    expand.textContent = label("查看五维得分", "View all five scores");
    const scores = document.createElement("p");
    scores.textContent = Object.entries(assessment.dimensions)
      .map(([code, score]) => `${bank.dimensions[code]} ${score}`).join(" · ");
    details.append(expand, scores);
    const actions = document.createElement("div");
    actions.className = "da-question-actions";
    actions.append(
      button(label("查看对应投教", "Open tailored lesson"), "da-primary", () => {
        find('[data-screen-target="assistant"]').click();
        document.dispatchEvent(new Event("harbor-education-requested"));
      }),
      button(label("重新测评", "Retake"), "da-secondary", () => {
        result = null;
        answers.clear();
        changes = step = 0;
        consent = false;
        render();
      }),
    );
    body.replaceChildren(headline, summary, details, actions);
  }

  async function save(form) {
    if (saving || !consent) return;
    saving = true;
    form.querySelectorAll("button, input").forEach((control) => { control.disabled = true; });
    status.textContent = label("正在评分…", "Scoring…");
    try {
      const response = await request("/api/questionnaire", {
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
      document.dispatchEvent(new Event("harbor-assessment-updated"));
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
    status.textContent = "";
    if (last) {
      const line = document.createElement("label");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.required = true;
      check.checked = consent;
      check.addEventListener("change", () => { consent = check.checked; });
      line.append(check, label("同意用测评结果生成风险画像和投教内容。", "Use my scores for the risk profile and tailored lessons."));
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
        status.textContent = label("请完成本组题目。", "Answer each question in this group.");
        form.elements.namedItem(missing.id)[0]?.focus();
      } else if (last) save(form);
      else { step++; render(); }
    });
    body.replaceChildren(form);
  }

  function localize() {
    const title = label("风险测评", "Risk assessment");
    nav.querySelector("span").textContent = title;
    find("#questionnaire-title").textContent = title;
    if (!screen.hidden) render();
  }

  nav.hidden = false;
  nav.addEventListener("click", () => { if (bank) render(); else loadBank(); });
  document.addEventListener("harbor-language", localize);
  localize();
  request("/api/profile").then(async (response) => {
    if (response.ok) {
      const profile = await response.json();
      if (profile.assessment) {
        result = profile;
        if (!screen.hidden) render();
      }
    } else if (response.status === 404 && !find("#screen-compare").hidden) {
      nav.click();
    }
  }).catch(() => {});
})();
