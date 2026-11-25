(() => {
  "use strict";
  const accountName = document.body.dataset.accountName;
  if (!accountName) return;

  const find = (selector) => document.querySelector(selector);
  const label = (zh, en) => document.documentElement.lang === "en" ? en : zh;
  const englishDimensions = {
    FC: "Financial capacity",
    RA: "Risk willingness",
    KE: "Knowledge and experience",
    BD: "Behavioral discipline",
    OC: "Objectives and constraints",
  };
  const englishQuestions = {
    FC1: {
      question: "Approximately how much was your household's total after-tax income over the past year?",
      A: "Less than CNY 100,000",
      B: "CNY 100,000–200,000",
      C: "CNY 200,000–500,000",
      D: "CNY 500,000–1 million",
      E: "More than CNY 1 million",
    },
    FC2: {
      question: "Approximately how much does your household hold in investable financial assets, excluding your primary home?",
      A: "Less than CNY 100,000",
      B: "CNY 100,000–500,000",
      C: "CNY 500,000–2 million",
      D: "CNY 2–5 million",
      E: "More than CNY 5 million",
    },
    FC3: {
      question: "What is your household's approximate debt-to-asset ratio (total liabilities divided by total assets, including mortgage debt)?",
      A: "Over 70%",
      B: "50%–70%",
      C: "30%–50%",
      D: "10%–30%",
      E: "Under 10%",
    },
    FC4: {
      question: "How stable is your household's main source of income?",
      A: "Very unstable. Currently unemployed or income has stopped.",
      B: "Somewhat unstable. Freelance, cyclical industry or project-based income.",
      C: "Moderately stable. Private-sector or heavily performance-based income.",
      D: "Fairly stable. State-owned employer, public institution or long-term contract.",
      E: "Very stable. A permanent public-sector post or several sources of passive income.",
    },
    FC5: {
      question: "If your household income stopped suddenly, how long could cash and highly liquid assets cover normal living expenses?",
      A: "Less than 1 month",
      B: "1–3 months",
      C: "3–6 months",
      D: "6–12 months",
      E: "More than 12 months",
    },
    FC6: {
      question: "Do you expect any major expenses in the next three years, such as a home purchase, education, healthcare or starting a business?",
      A: "Yes, more than 50% of investable assets.",
      B: "Yes, about 30%–50% of investable assets.",
      C: "Yes, about 10%–30%.",
      D: "Yes, but less than 10%.",
      E: "Little or no major spending expected.",
    },
    RA1: {
      question: "If you had CNY 100,000 to invest, which option would you prefer?",
      A: "A guaranteed gain of CNY 3,000.",
      B: "A 50% chance of gaining CNY 8,000 and a 50% chance of breaking even.",
      C: "A 50% chance of gaining CNY 15,000 and a 50% chance of losing CNY 3,000.",
      D: "A 50% chance of gaining CNY 25,000 and a 50% chance of losing CNY 8,000.",
      E: "A 50% chance of gaining CNY 50,000 and a 50% chance of losing CNY 20,000.",
    },
    RA2: {
      question: "What is the largest annual portfolio loss you could accept on a CNY 100,000 investment?",
      A: "I could not accept any loss.",
      B: "Under 5% (up to CNY 5,000).",
      C: "5%–15% (CNY 5,000–15,000).",
      D: "15%–30% (CNY 15,000–30,000).",
      E: "Over 30% (more than CNY 30,000).",
    },
    RA3: {
      question: "If your holdings fell 20% over a short period, how would you most likely react?",
      A: "Sell everything immediately to avoid further losses.",
      B: "Sell most of the holdings and keep a small position.",
      C: "Wait and take no action.",
      D: "Add a little to the position.",
      E: "Add substantially, treating the drop as a buying opportunity.",
    },
    RA4: {
      question: "Which pattern of investment returns would you prefer?",
      A: "A steady return of about 3% each year.",
      B: "A steady return of about 5% each year.",
      C: "About 7% a year on average over the long term, with possible losses of 10% in some years.",
      D: "About 10% a year on average over the long term, with possible losses of 25% in some years.",
      E: "About 15% a year on average over the long term, with possible losses of 40% in some years.",
    },
    RA5: {
      question: "If a product offered a 2% higher expected return but substantially greater volatility and drawdowns, how would you respond?",
      A: "I would reject it and choose a lower, steadier return.",
      B: "I would hesitate and most likely decline.",
      C: "It would depend on my overall portfolio.",
      D: "I would accept it in pursuit of a higher return.",
      E: "I would welcome it and accept substantially greater volatility.",
    },
    RA6: {
      question: "How would you rate your own risk preference from 1 (very conservative) to 5 (very aggressive)?",
      A: "1 (very conservative)",
      B: "2 (somewhat conservative)",
      C: "3 (moderate)",
      D: "4 (somewhat aggressive)",
      E: "5 (very aggressive)",
    },
    KE1: {
      question: "How long have you invested in securities, funds or wealth management products?",
      A: "I have never invested.",
      B: "Less than 1 year",
      C: "1–3 years",
      D: "3–8 years",
      E: "More than 8 years",
    },
    KE2: {
      question: "Which of these products have you invested in or are currently invested in? Select all that apply. Scoring uses the most complex product selected.",
      A: "Deposits, government bonds or money market funds.",
      B: "Bank wealth management products or pure bond funds.",
      C: "Balanced funds, convertible bonds or REITs.",
      D: "Stocks, equity or index funds, or QDII products.",
      E: "Options, futures, private funds, or leveraged or structured products.",
    },
    KE3: {
      question: "What is the most accurate interpretation of an unrealized loss on a net-asset-value-based wealth management product?",
      A: "Bank wealth management products guarantee principal and interest. The loss is only a display issue.",
      B: "The loss means the product broke the rules and the bank should compensate me.",
      C: "Net asset value normally fluctuates, so the product is certain to recover.",
      D: "Net asset value changes with the underlying assets. Real losses are possible, and the product's risk rating matters.",
      E: "Investors bear the risk. They should assess the underlying assets, duration and credit risk.",
    },
    KE4: {
      question: "Which statement about diversification is most accurate?",
      A: "Buying many different funds is enough to diversify.",
      B: "Diversifying means putting half the money in stocks and half in bonds.",
      C: "Diversification can reduce asset-specific risk, but it cannot eliminate market-wide risk.",
      D: "Its effectiveness depends on asset correlations, exposure to risk factors and disciplined rebalancing.",
      E: "Diversification should account for correlations, risk factors, time horizons and liquidity, with regular rebalancing.",
    },
    KE5: {
      question: "Have you held investments through a major market decline, such as China's 2015 stock market crash, the 2018 bear market or the 2022 correction?",
      A: "I have never experienced a major market decline.",
      B: "I experienced one and exited the market.",
      C: "I experienced one and sold part of my holdings to limit losses.",
      D: "I experienced one and kept most of my holdings throughout.",
      E: "I have held through several full market cycles and rebalanced as planned.",
    },
    KE6: {
      question: "How many of these concepts can you explain: compounding, duration, the Sharpe ratio and maximum drawdown?",
      A: "None",
      B: "One",
      C: "Two",
      D: "Three",
      E: "I can accurately explain all four.",
    },
    BD1: {
      question: "If one holding gained 20% and another lost 20%, what would you be most likely to do?",
      A: "Immediately sell the winner and hold the loser until it breaks even.",
      B: "Sell the winner and continue holding the loser.",
      C: "Take no action on either holding.",
      D: "Reassess both holdings based on their fundamentals.",
      E: "Follow my existing investment and rebalancing rules regardless of the purchase prices.",
    },
    BD2: {
      question: "Over the past year, how often have you bought after a sharp rise or sold in a panic after a sharp drop?",
      A: "Often",
      B: "Sometimes",
      C: "Occasionally",
      D: "Rarely",
      E: "Never. I generally followed my plan.",
    },
    BD3: {
      question: "How do you assess your ability to time the market?",
      A: "Very confident. I can identify market peaks and bottoms fairly accurately.",
      B: "Fairly confident. I usually get it right.",
      C: "Moderately confident. I sometimes get it right.",
      D: "Not very confident. I rely more on asset allocation.",
      E: "I know timing is difficult, so I stick to long-term allocation and investment discipline.",
    },
    BD4: {
      question: "What do you do when friends, relatives, social media or an influencer strongly recommend an investment?",
      A: "Usually buy based on the recommendation.",
      B: "Consider the recommendation and buy fairly quickly.",
      C: "Research the investment before deciding.",
      D: "Treat it as one source of information and make my own decision.",
      E: "Decide according to my investment framework and suitability requirements.",
    },
    BD5: {
      question: "What is the main factor in your buy and sell decisions?",
      A: "My purchase price.",
      B: "Recent price movements and market sentiment.",
      C: "Technical indicators or short-term news.",
      D: "Fundamentals and valuation.",
      E: "Asset allocation targets, risk budgets and rebalancing rules.",
    },
    BD6: {
      question: "How would you handle a windfall such as a year-end bonus or a relocation compensation payment?",
      A: "Take more risk with it because it did not come from my usual earnings.",
      B: "Keep it separate and invest it more aggressively.",
      C: "Keep some of it separate from everyday funds.",
      D: "Include it in my household financial plan.",
      E: "Include all of it in my overall asset allocation and apply the same risk budget.",
    },
    OC1: {
      question: "How clearly defined are your investment goals?",
      A: "I have no specific goals.",
      B: "My goals are vague. I mainly want to make money.",
      C: "I have a broad goal, such as keeping ahead of inflation.",
      D: "I have specific goals, amounts and deadlines.",
      E: "I have prioritized goals for preserving, growing and passing on wealth.",
    },
    OC2: {
      question: "How long can you leave this money invested?",
      A: "Less than 6 months",
      B: "6 months to 1 year",
      C: "1–3 years",
      D: "3–5 years",
      E: "More than 5 years",
    },
    OC3: {
      question: "How likely are you to need this money within the next year?",
      A: "Very likely (over 50%).",
      B: "Fairly likely (30%–50%).",
      C: "Somewhat likely (10%–30%).",
      D: "Unlikely (under 10%).",
      E: "Almost certainly will not need it.",
    },
    OC4: {
      question: "If markets perform poorly, can you postpone an investment goal such as buying a home or paying education costs, or cover it with other income?",
      A: "No. I need the full amount by the original deadline.",
      B: "The goal is fairly fixed, with little room to delay.",
      C: "I can adjust some of the goal.",
      D: "The goal is fairly flexible. I can delay it by one or two years.",
      E: "The goal is fully flexible. I can delay it or use other funds.",
    },
    OC5: {
      question: "Do you invest with borrowed funds, such as consumer loans, unsecured loans or margin financing?",
      A: "Often, and with high leverage.",
      B: "Occasionally.",
      C: "I used to, but I have stopped.",
      D: "As a rule, I do not.",
      E: "Never. I am against investing with leverage.",
    },
    OC6: {
      question: "How independently do you make investment decisions, and how much financial responsibility do you have for your household?",
      A: "Other people make all of my decisions, and I have substantial household obligations.",
      B: "Family members strongly influence my decisions, and I have substantial household obligations.",
      C: "I decide together with my family and have moderate household obligations.",
      D: "I decide independently and have relatively few household obligations.",
      E: "I decide completely independently, and my household has very little financial pressure.",
    },
  };
  const dimension = (code) => label(bank.dimensions[code], englishDimensions[code] ?? bank.dimensions[code]);
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
    const english = englishQuestions[question.id];
    title.textContent = label(question.text, english?.question ?? question.text);
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
      line.append(input, `${option.key}. ${label(option.text, english?.[option.key] ?? option.text)}`);
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
    details.open = body.querySelector(".da-assessment-details")?.open ?? false;
    const expand = document.createElement("summary");
    expand.textContent = label("查看五维得分", "View all five scores");
    const scores = document.createElement("p");
    scores.textContent = Object.entries(assessment.dimensions)
      .map(([code, score]) => `${dimension(code)} ${score}`).join(" · ");
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
    heading.textContent = `${step + 1}/${groups.length} · ${dimension(code)}`;
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
