(() => {
  "use strict";
  if (document.body.dataset.integrated !== "true") return;

  const one = (selector) => document.querySelector(selector);
  const all = (selector) => [...document.querySelectorAll(selector)];
  const hide = (selector) => all(selector).forEach((element) => { element.hidden = true; });
  const bilingual = (element, zh, en) => {
    element.dataset.demoZh = zh;
    element.dataset.demoEn = en;
    element.textContent = document.documentElement.lang === "en" ? en : zh;
  };
  const text = (element, content) => {
    delete element.dataset.demoZh;
    delete element.dataset.demoEn;
    element.textContent = content;
  };
  const node = (tag, content, className) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) text(element, content);
    return element;
  };
  const notice = (parent, id) => {
    const element = node("p", "", "da-integration-notice");
    element.id = id;
    element.setAttribute("role", "status");
    parent.append(element);
    return element;
  };
  const money = (amount, currency) => amount == null ? "—" : `${amount} ${currency}`;
  const time = (timestamp) => timestamp ? timestamp.replace("T", " ").replace(/\.\d+Z$/, "Z") : "—";
  const errorMessage = (error) => error.message || "Request failed";
  const accountName = document.body.dataset.accountName;

  async function request(path, method = "GET", payload) {
    const options = { method, headers: { Accept: "application/json" } };
    if (accountName) options.headers["X-Harbor-Account"] = accountName;
    if (payload !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    if (accountName && response.status === 401) location.reload();
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error?.message || `HTTP ${response.status}`);
      error.code = data.error?.code;
      throw error;
    }
    return data;
  }

  function tableRow(body, values) {
    const row = node("tr");
    for (const value of values) {
      const cell = node("td");
      cell.append(value instanceof Node ? value : String(value ?? "—"));
      row.append(cell);
    }
    body.append(row);
    return row;
  }

  function navigate(screen) {
    one(`[data-screen-target="${screen}"]`).click();
  }

  document.addEventListener("harbor-language", () => {
    all("[data-demo-zh]").forEach((element) => bilingual(element, element.dataset.demoZh, element.dataset.demoEn));
  });

  window.addEventListener("pageshow", (event) => { if (event.persisted) location.reload(); });
  hide(".da-topmeta .da-iconbtn, .da-avatar");
  if (!accountName) {
    const input = one("#account-name");
    const submit = one("#account-login-submit");
    const status = one("#account-login-status");
    bilingual(one("#account-login-eyebrow"), "本机演示", "LOCAL DEMO");
    bilingual(one("#account-login-title"), "登录演示账户", "Sign in to a demo account");
    bilingual(one("#account-login-description"), "输入账户名继续。首次使用该名称时会自动创建模拟账户。",
      "Enter an account name to continue. A new name creates a simulation account.");
    bilingual(one('label[for="account-name"]'), "账户名", "Account name");
    bilingual(one("#account-login-hint"), "测试账户 demo_c1 至 demo_c5 对应五个风险等级。",
      "Test accounts demo_c1 through demo_c5 cover the five risk levels.");
    bilingual(one(".da-login-note"), "仅用于模拟，不验证身份。请勿输入真实账号或密码。",
      "Simulation only. Identity is not verified. Do not enter real credentials.");
    bilingual(submit, "登录", "Sign in");
    input.addEventListener("input", () => {
      input.removeAttribute("aria-invalid");
      text(status, "");
    });
    one("#account-login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (submit.disabled) return;
      const name = input.value.trim();
      if (!/^[A-Za-z0-9_-]{1,64}$/.test(name)) {
        input.setAttribute("aria-invalid", "true");
        bilingual(status, "请输入有效的账户名。", "Enter a valid account name.");
        input.focus();
        return;
      }
      submit.disabled = true;
      input.readOnly = true;
      text(status, "");
      bilingual(submit, "正在登录…", "Signing in…");
      try {
        await request("/api/session", "POST", { account_name: name });
        location.reload();
      } catch (error) {
        if (error.code === "invalid_account_name") {
          input.setAttribute("aria-invalid", "true");
          bilingual(status, "请输入有效的账户名。", "Enter a valid account name.");
        } else {
          bilingual(status, "暂时无法打开演示账户，请重试。", "Could not open the demo account. Try again.");
        }
        submit.disabled = false;
        input.readOnly = false;
        bilingual(submit, "登录", "Sign in");
        input.focus();
      }
    });
    return;
  }

  const switchAccount = one("#account-switch");
  const switchStatus = one("#account-switch-status");
  text(one("#current-account"), accountName);
  one("#current-account").title = accountName;
  bilingual(switchAccount, "切换账户", "Switch account");
  switchAccount.addEventListener("click", async () => {
    switchAccount.disabled = true;
    switchStatus.hidden = true;
    try {
      await request("/api/session", "DELETE");
      location.reload();
    } catch {
      bilingual(switchStatus, "暂时无法切换账户，请重试。", "Could not switch accounts. Try again.");
      switchStatus.hidden = false;
      switchAccount.disabled = false;
    }
  });

  hide("#screen-compare .da-kpis, .da-route-panel, .da-crossasset, " +
    ".da-segmented, .da-quote-panel .da-textbtn, .da-quote-panel .da-footnote, " +
    "#screen-compare .da-headactions .da-primary, #screen-trade .da-headactions, .da-watchlist .da-iconbtn, " +
    ".da-watchlist-head, .da-watchfoot, .da-watchrow > :not(.da-asset), .da-quickamounts, " +
    ".da-order-summary > div:nth-child(3), .da-context-panel, #screen-account .da-headactions, " +
    ".da-account-grid, .da-screen .da-pagehead p, " +
    ".da-order-note, .da-order .da-panelhead p, .da-precheck strong, .da-chat-disclaimer");
  bilingual(one(".da-status"), "模拟账户", "Simulation account");
  bilingual(one("#trade-title"), "模拟下单", "Simulated order");
  bilingual(one('[data-screen-target="trade"] span'), "模拟下单", "Simulated order");
  bilingual(one(".da-watchlist h2"), "选择币种", "Choose an asset");
  hide(".da-watchlist .da-panelhead p");
  bilingual(one(".da-edu-badge"), "课堂投教", "Classroom education");
  one(".da-railsummary button").addEventListener("click", () => navigate("account"));

  const pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
  const assets = all('[data-choice-group="compare-asset"]');
  const watch = all(".da-watchrow");
  assets.slice(pairs.length).forEach((element) => { element.hidden = true; });
  watch.slice(pairs.length).forEach((element) => { element.hidden = true; });
  let pair = pairs[0];
  let side = "buy";
  let marketVersion = 0;
  let marketTimer;
  let marketRefreshMs;
  const amount = one("#order-amount");
  const kind = one("#order-type");
  const limit = one("#order-limit");
  const limitField = limit.closest("label");
  const venue = one("#venue-select");
  const publicAssetFilter = one("#public-asset-filter");
  const publicAsset = one("#public-asset");
  const publicPairFilter = one("#public-pair-filter");
  const publicPair = one("#public-pair");
  const allQuoteCurrencies = "all";
  const spotAssets = new Map();
  bilingual(publicAssetFilter.querySelector("span"), "币种", "Asset");
  bilingual(publicPairFilter.querySelector("span"), "计价币", "Quote currency");
  const submit = one("#submit-order");
  const marketBody = one(".da-quote-panel tbody");
  const marketNotice = notice(one(".da-quote-panel"), "market-status");
  const orderNotice = one(".da-precheck span");
  const orderStatus = orderNotice.closest(".da-precheck");
  orderStatus.setAttribute("role", "status");
  const orderRisk = one("#order-risk-notice");
  const marketColumns = all(".da-quote-panel th");
  bilingual(marketColumns[1], "买入价（Ask）", "Ask");
  bilingual(marketColumns[2], "卖出价（Bid）", "Bid");
  bilingual(marketColumns[4], "报价时间（UTC）", "Quote time (UTC)");
  bilingual(one(".da-order-summary .da-summary-total span"), "估算净额", "Estimated net amount");
  bilingual(amount.closest("label").querySelector(":scope > span"), "委托数量", "Quantity");
  text(limitField.querySelector("b"), "USDT");
  amount.step = "any";
  amount.value = "0.01";
  kind.value = "market";
  limit.value = "";
  let preview = null;
  let submitting = false;
  let orderVersion = 0;

  function labelOrderButton(confirming) {
    const [zh, en] = side === "buy" ? ["买入", "buy"] : ["卖出", "sell"];
    bilingual(submit, confirming ? `确认模拟${zh}` : `预览${zh}`,
      confirming ? `Confirm simulated ${en}` : `Preview ${en}`);
  }

  function showSuitabilityWarning(warning) {
    orderRisk.hidden = !warning;
    if (!warning) {
      text(orderRisk, "");
      return;
    }
    const { code, risk_level: level, product_cap: cap, product_risk: product } = warning;
    const messages = {
      assessment_required: [
        "尚未测评，买入风险待评估。",
        "No assessment yet. Purchase risk is unassessed.",
      ],
      product_cap: [
        `你的等级 ${level}（上限 ${cap}），产品演示档位 ${product}。买入可能超出测评范围。`,
        `Your level is ${level} (limit ${cap}). The demo product is ${product} and may exceed your risk tolerance.`,
      ],
      assessment_prohibition: [
        "测评结果标记了买入风险，请查看你的风险说明后自行决定。",
        "Your assessment flagged a purchase restriction. Review the risk details before deciding.",
      ],
    };
    bilingual(orderRisk, ...(messages[code] ?? ["这笔买入存在测评相关风险。", "This buy may involve risks noted in your assessment."]));
  }

  function invalidateOrder() {
    preview = null;
    orderVersion++;
    limitField.hidden = limit.disabled = kind.value !== "limit";
    for (const id of ["#order-notional", "#order-fee", "#order-total"]) text(one(id), "—");
    labelOrderButton(false);
    orderStatus.hidden = true;
    text(orderNotice, "");
    showSuitabilityWarning(null);
  }

  function setVenues(quotes, selected = "") {
    const automatic = node("option");
    automatic.value = "";
    bilingual(automatic, "自动路由", "Automatic venue selection");
    venue.replaceChildren(automatic);
    for (const quote of quotes) {
      const option = node("option", quote.source);
      if (quote.source.startsWith("demo:MDGateway:")) {
        const name = venueName(quote.source);
        bilingual(option, `${name}（模拟）`, `${name} (simulated)`);
      }
      option.value = quote.source;
      venue.append(option);
    }
    if (selected && !quotes.some((quote) => quote.source === selected)) {
      const unavailable = node("option");
      unavailable.value = selected;
      unavailable.disabled = true;
      bilingual(unavailable, `${selected}（暂缺报价）`, `${selected} (quote unavailable)`);
      venue.append(unavailable);
    }
    venue.value = selected;
  }

  function venueName(source) {
    return source.replace(/^demo:MDGateway:/, "");
  }

  function refreshQuoteCurrencies() {
    const choices = spotAssets.get(publicAsset.value);
    const keepAll = publicPair.value === allQuoteCurrencies;
    const allCurrencies = new Option("", allQuoteCurrencies);
    bilingual(allCurrencies, "所有", "All");
    publicPair.replaceChildren(allCurrencies, ...choices.map(({ symbol, currency }) => new Option(currency, symbol)));
    const preferred = choices.find(({ currency, sources }) =>
      currency === "USD" && ["HashKey", "OSL"].every((name) => sources.map(venueName).includes(name)))
      ?? choices.find(({ currency, sources }) => currency === "USDT" && sources.length >= 2)
      ?? choices.find(({ sources }) => sources.length >= 2)
      ?? choices[0];
    publicPair.value = keepAll ? allQuoteCurrencies : preferred.symbol;
  }

  async function initializeMarket() {
    try {
      const catalog = await request("/api/market/catalog");
      for (const [symbol, sources] of Object.entries(catalog.pairs)) {
        const [asset, currency] = symbol.split("/");
        if (!spotAssets.has(asset)) spotAssets.set(asset, []);
        spotAssets.get(asset).push({ symbol, currency, sources });
      }
      if (catalog.market_mode === "public" && spotAssets.size) {
        const tickers = [...spotAssets.keys()].sort();
        publicAsset.replaceChildren(...tickers.map((ticker) => new Option(ticker, ticker)));
        if (spotAssets.has("BTC")) publicAsset.value = "BTC";
        refreshQuoteCurrencies();
        publicAssetFilter.hidden = publicPairFilter.hidden = false;
        assets[0].parentElement.hidden = true;
      }
    } catch {
      // A missing catalog leaves the existing trade pairs available.
    }
    choosePair(0);
  }

  function venueQuotes(symbol) {
    const query = new URLSearchParams({ symbol, quantity: "0.01", side: "buy" });
    return request(`/api/market/venues?${query}`);
  }

  function renderQuoteRows(result) {
    const { symbol, venues, market_mode: mode, quote_mode: quoteMode, ranking_basis: ranking } = result;
    const publicMarket = mode === "public";
    for (const quote of venues) {
      let action = "—";
      if (pairs.includes(symbol)) {
        action = node("button", "", "da-rowbtn");
        action.type = "button";
        bilingual(action, "选择", "Select");
        action.addEventListener("click", () => { choosePair(pairs.indexOf(symbol), quote.source); navigate("trade"); });
      }
      const timestamp = node("span", time(quote.as_of));
      if (quote.timestamp_source === "collected") bilingual(timestamp, `${time(quote.as_of)} · 采集`, `${time(quote.as_of)} · collected`);
      const venueLabel = node("span", venueName(quote.source));
      if (publicMarket) {
        const last = node("small");
        const price = money(quote.price, quote.quote_currency);
        if (quoteMode === "simulation") bilingual(last, `模拟最新价 ${price}`, `Last simulated price ${price}`);
        else bilingual(last, `最新成交 ${price}`, `Last trade ${price}`);
        venueLabel.append(document.createElement("br"), last);
      }
      const fee = quote.fee_rate === null ? "—" : `${(Number(quote.fee_rate) * 100).toPrecision(3)}%`;
      let notional = money(ranking === "bid_ask_excluding_fees" ? quote.notional : quote.total, quote.quote_currency);
      if (quote.quantity_covered === false) {
        notional = node("span");
        bilingual(notional, "卖一档数量不足", "Insufficient at best ask");
      }
      tableRow(marketBody, [venueLabel, money(quote.ask, quote.quote_currency), money(quote.bid, quote.quote_currency),
        publicMarket ? money(quote.ask_size, symbol.split("/")[0]) : fee, timestamp, notional, action]);
    }
  }

  function renderQuoteGroup(symbol, outcome) {
    const row = node("tr", undefined, "da-quote-group");
    const heading = node("th", symbol);
    heading.colSpan = marketColumns.length;
    const labels = outcome.status === "rejected" ? ["报价暂不可用", "Quotes unavailable"]
      : !outcome.value.venues.length ? ["暂无有效报价", "No current quotes"]
      : outcome.value.status !== "ok" ? ["当前可比报价不足两家", "Fewer than two current quotes"] : null;
    if (labels) {
      const status = node("span");
      bilingual(status, ...labels);
      heading.append(" · ", status);
    }
    row.append(heading);
    marketBody.append(row);
    if (outcome.status === "fulfilled") renderQuoteRows(outcome.value);
  }

  async function loadMarket(selectedVenue = "", background = false) {
    const version = ++marketVersion;
    const showAll = publicPair.value === allQuoteCurrencies;
    const symbols = showAll ? spotAssets.get(publicAsset.value).map(({ symbol }) => symbol) : [publicPair.value || pair];
    const orderPair = pair;
    const compareTitle = one(".da-quote-panel h2");
    if (showAll) bilingual(compareTitle, `${publicAsset.value} · 所有计价币`, `${publicAsset.value} · All quote currencies`);
    else text(compareTitle, symbols[0]);
    text(one(".da-order h2"), pair);
    text(amount.closest("label").querySelector("b"), pair.split("/")[0]);
    if (!background) {
      text(one(".da-clock"), "—");
      text(one(".da-fresh"), "—");
      marketBody.replaceChildren();
      bilingual(marketNotice, "正在读取中台报价…", "Loading middle-office quotes…");
    }
    try {
      const requests = new Map([...new Set([...symbols, orderPair])].map((symbol) => [symbol, venueQuotes(symbol)]));
      const outcomes = await Promise.allSettled([...symbols, orderPair].map((symbol) => requests.get(symbol)));
      if (version !== marketVersion) return;
      const orderQuotes = outcomes.pop().value;
      const results = outcomes.filter((outcome) => outcome.status === "fulfilled").map((outcome) => outcome.value);
      if (!results.length && !showAll) throw outcomes[0].reason;
      const result = results[0];
      const publicMarket = showAll || result.market_mode === "public";
      const simulatedFeed = publicMarket && result?.quote_mode === "simulation";
      const preFee = showAll || result.ranking_basis === "bid_ask_excluding_fees";
      const compareCaption = one(".da-quote-panel .da-panelhead p");
      if (publicMarket) {
        const refreshMs = simulatedFeed ? 2000 : 10000;
        if (marketRefreshMs !== refreshMs) {
          clearInterval(marketTimer);
          marketRefreshMs = refreshMs;
          marketTimer = setInterval(() => {
            if (!document.hidden) loadMarket(venue.value, true);
          }, refreshMs);
        }
        bilingual(marketColumns[3], "卖一挂单数量", "Best ask size");
        if (showAll) {
          bilingual(compareCaption, "按计价币分组，只比较同一组内的报价。", "Quotes are grouped and compared only within each quote currency.");
        } else if (simulatedFeed) {
          bilingual(compareCaption, "组内模拟器生成的买卖报价，不是交易所实时行情。", "Simulated bid and ask from the team’s generator, not live exchange quotes.");
        } else if (pairs.includes(result.symbol)) {
          bilingual(compareCaption, "比较 0.01 币的现货报价，优先列出卖一档可覆盖的平台。", "Compare quotes for 0.01 units and prioritize venues with enough at the best ask.");
        } else {
          bilingual(compareCaption, "按相同计价币比较 0.01 币的现货报价。该交易对仅供比价。", "Compare spot quotes for 0.01 units in one currency. This pair is available for comparison.");
        }
      } else {
        bilingual(marketColumns[3], "手续费", "Fee");
        bilingual(compareCaption, "按买入 0.01 币的报价比较。", "Compare quotes to buy 0.01 units.");
      }
      if (preFee) bilingual(marketColumns[5], "报价金额（未计费）", "Notional (fees excluded)");
      else bilingual(marketColumns[5], "含费总额（0.01 币）", "Total with fee (0.01 units)");
      if (!preview && !submitting) setVenues(orderQuotes?.venues ?? [], background ? venue.value : selectedVenue);
      marketBody.replaceChildren();
      if (showAll) symbols.forEach((symbol, index) => renderQuoteGroup(symbol, outcomes[index]));
      else renderQuoteRows(result);
      const latest = results.flatMap(({ venues }) => venues.map((quote) => quote.as_of)).sort().at(-1);
      text(one(".da-clock"), time(latest));
      if (!latest) text(one(".da-fresh"), "—");
      else if (publicMarket && !simulatedFeed) bilingual(one(".da-fresh"), `公开现货 · ${time(latest)}`, `Public spot · ${time(latest)}`);
      else bilingual(one(".da-fresh"), `模拟 · ${time(latest)}`, `Simulation · ${time(latest)}`);
      const best = orderQuotes?.venues[0];
      text(one(".da-quote-pill"), best ? money(best.price, best.quote_currency) : "—");
      if (showAll) {
        if (!latest) bilingual(marketNotice, "当前没有可用报价。", "No quotes are available.");
        else if (simulatedFeed) bilingual(marketNotice, "模拟报价每 2 秒更新，未计交易费。", "Simulated quotes update every 2 seconds. Fees excluded.");
        else bilingual(marketNotice, "报价未计交易费，订单仍为模拟。", "Fees excluded; simulated orders only.");
      } else if (publicMarket) {
        const unavailable = [...result.excluded_sources, ...result.missing_sources];
        const details = unavailable.length ? ` · ${unavailable.join(", ")}` : "";
        if (simulatedFeed && result.status === "ok") bilingual(marketNotice, "模拟报价每 2 秒更新，未计交易费。", "Simulated quotes update every 2 seconds. Fees excluded.");
        else if (result.status === "ok") bilingual(marketNotice, `报价未计交易费，订单仍为模拟${details}`, `Fees excluded; simulated orders only${details}`);
        else bilingual(marketNotice, `当前可比报价不足两家${details}`, `Fewer than two current quotes${details}`);
      } else if (result.status === "ok") bilingual(marketNotice, "模拟报价。按买卖价全量模拟成交。", "Simulated quotes. Full fills at bid or ask are assumed.");
      else bilingual(marketNotice, "有效报价不足两家。", "Fewer than two current venues are available.");
    } catch (error) {
      if (version === marketVersion) {
        marketBody.replaceChildren();
        text(one(".da-quote-pill"), "—");
        text(one(".da-clock"), "—");
        text(one(".da-fresh"), "—");
        text(marketNotice, errorMessage(error));
      }
    }
  }

  function choosePair(index, selectedVenue = "") {
    pair = pairs[index];
    for (const group of [assets, watch]) {
      group.forEach((button, position) => {
        button.classList.toggle("is-selected", position === index);
        button.setAttribute("aria-pressed", String(position === index));
      });
    }
    invalidateOrder();
    text(one(".da-quote-pill"), "—");
    setVenues([], selectedVenue);
    loadMarket(selectedVenue);
  }

  pairs.forEach((_, index) => {
    assets[index].addEventListener("click", () => choosePair(index));
    watch[index].addEventListener("click", () => choosePair(index));
  });
  publicAsset.addEventListener("change", () => {
    refreshQuoteCurrencies();
    loadMarket(venue.value);
  });
  publicPair.addEventListener("change", () => loadMarket(venue.value));
  one("#screen-compare .da-headactions .da-secondary").addEventListener("click", () => {
    invalidateOrder();
    loadMarket(venue.value);
  });
  all("[data-side]").forEach((button) => button.addEventListener("click", () => {
    side = button.dataset.side;
    invalidateOrder();
  }));
  for (const control of [amount, limit]) control.addEventListener("input", invalidateOrder);
  for (const control of [kind, venue]) control.addEventListener("change", invalidateOrder);
  document.addEventListener("harbor-assessment-updated", invalidateOrder);
  submit.addEventListener("click", async () => {
    if (submitting) return;
    submitting = submit.disabled = true;
    const version = orderVersion;
    const confirming = Boolean(preview);
    try {
      if (confirming) {
        const result = await request("/api/orders", "POST", { preview_id: preview.preview_id });
        invalidateOrder();
        const names = { filled: ["已成交", "Filled"], open: ["已挂单", "Open"], rejected: ["已拒绝", "Rejected"] };
        const [zh, en] = names[result.status] || [result.status, result.status];
        const detail = result.reason ? ` · ${result.reason}` : "";
        bilingual(orderNotice, zh + detail, en + detail);
        orderStatus.hidden = false;
        showSuitabilityWarning(result.suitability_warning);
        loadAccount();
      } else {
        const payload = { symbol: pair, side, order_type: kind.value, quantity: amount.value };
        if (limit.value && kind.value === "limit") payload.limit_price = limit.value.trim();
        if (venue.value) payload.source = venue.value;
        const result = await request("/api/orders/preview", "POST", payload);
        if (version !== orderVersion) return;
        preview = result;
        showSuitabilityWarning(result.suitability_warning);
        for (const key of ["notional", "fee", "total"]) text(one(`#order-${key}`), money(result[key], result.quote_currency));
        labelOrderButton(true);
        const feeZh = result.fee_assumed ? " · 模拟手续费按 0 计" : "";
        const feeEn = result.fee_assumed ? " · Simulated fee assumed zero" : "";
        bilingual(orderNotice, `${result.source} · ${result.expires_in} 秒内确认${feeZh}`, `${result.source} · Confirm within ${result.expires_in}s${feeEn}`);
        orderStatus.hidden = false;
      }
    } catch (error) {
      if (error.code === "preview_expired") invalidateOrder();
      if (version === orderVersion || confirming) {
        text(orderNotice, errorMessage(error));
        orderStatus.hidden = false;
      }
    } finally {
      submitting = submit.disabled = false;
    }
  });

  const lesson = one("#guided-lesson");
  const lessonTitle = one("#lesson-title");
  const lessonFocus = one("#lesson-focus");
  const lessonContent = one("#lesson-content");
  const lessonTrade = one("#lesson-trade");
  const lessonRetry = one("#lesson-retry");
  let lessonVersion = 0;

  async function loadLesson() {
    const version = ++lessonVersion;
    lesson.hidden = false;
    lessonFocus.hidden = lessonTrade.hidden = lessonRetry.hidden = true;
    bilingual(lessonTitle, "对应投教", "Tailored lesson");
    bilingual(lessonContent, "正在加载…", "Loading…");
    try {
      const data = await request("/api/education");
      if (version !== lessonVersion) return;
      bilingual(lessonTitle, data.title.zh, data.title.en);
      bilingual(lessonContent, data.content.zh, data.content.en);
      if (data.focus) {
        const { label, score } = data.focus;
        bilingual(lessonFocus, `${label.zh} · ${score} / 100`, `${label.en} · ${score} / 100`);
        lessonFocus.hidden = false;
      }
      bilingual(lessonTrade, "打开模拟下单页", "Open simulated order page");
      lessonTrade.hidden = false;
      if (!one("#screen-assistant").hidden) lessonTitle.focus();
    } catch (error) {
      if (version !== lessonVersion) return;
      if (error.code === "assessment_required") {
        bilingual(lessonContent, "请先完成测评。", "Complete the assessment first.");
        bilingual(lessonRetry, "打开风险问卷", "Open risk questionnaire");
        lessonRetry.onclick = () => navigate("questionnaire");
      } else {
        bilingual(lessonContent, "暂时无法加载投教。", "Lesson unavailable.");
        bilingual(lessonRetry, "重试加载投教", "Retry lesson");
        lessonRetry.onclick = loadLesson;
      }
      lessonRetry.hidden = false;
    }
  }

  lessonTrade.addEventListener("click", () => navigate("trade"));
  document.addEventListener("harbor-education-requested", loadLesson);
  document.addEventListener("harbor-assessment-updated", () => {
    lessonVersion++;
    lesson.hidden = true;
  });

  const messages = one(".da-messages");
  const input = one("#assistant-input");
  const send = one(".da-send");
  const newChat = one("#new-chat");
  const replyModel = one("#reply-model");
  const modelSettings = one("#model-settings");
  const modelProvider = one("#model-provider");
  const ollamaModel = one("#ollama-model");
  const builtinProviders = [...modelProvider.options];
  const apiFields = one("#api-model-fields");
  const apiKey = one("#api-model-key");
  const apiAgree = one("#api-model-agree");
  const modelStatus = one("#model-settings-status");
  const modelSave = one("#model-settings-save");
  const modelCancel = one("#model-settings-cancel");
  let modelLoad = 0;
  let apiProviders = new Map();
  let savedKeyProvider = null;
  let history = [];
  input.maxLength = 2000;
  newChat.addEventListener("click", () => {
    messages.replaceChildren();
    history = [];
    replyModel.hidden = true;
    input.focus();
  });

  function refreshModelFields() {
    const usingOllama = modelProvider.value === "ollama";
    const provider = apiProviders.get(modelProvider.value);
    one("#ollama-fields").hidden = !usingOllama;
    apiFields.hidden = !provider;
    ollamaModel.disabled = !usingOllama;
    apiKey.disabled = apiAgree.disabled = !provider;
    const keepsKey = savedKeyProvider === modelProvider.value;
    apiKey.required = Boolean(provider && !keepsKey);
    apiAgree.required = Boolean(provider);
    apiKey.placeholder = provider && keepsKey
      ? (document.documentElement.lang === "en" ? "Leave blank to keep the saved key" : "留空可保留已保存的 Key")
      : "";
    if (provider) {
      text(one("#api-key-label"), `${provider.name} API Key`);
      bilingual(one("#api-model-consent"),
        `同意将对话与风险画像发送给 ${provider.name}，费用按该平台的 API 规则计算。`,
        `I agree to send chat messages and my risk profile to ${provider.name} under its API billing terms.`);
    }
    modelSave.disabled = modelProvider.disabled || (usingOllama && !ollamaModel.value);
    if (usingOllama && !ollamaModel.value) {
      bilingual(modelStatus, "未找到本地模型。启动 Ollama、安装模型后重新打开设置。",
        "No local models found. Start Ollama, install a model, then reopen settings.");
    } else {
      text(modelStatus, "");
    }
  }

  one("#model-settings-open").addEventListener("click", async () => {
    const load = ++modelLoad;
    apiKey.value = "";
    apiAgree.checked = false;
    modelProvider.disabled = modelSave.disabled = true;
    one("#ollama-fields").hidden = apiFields.hidden = true;
    bilingual(modelStatus, "正在读取模型设置…", "Loading model settings…");
    modelSettings.showModal();
    try {
      const data = await request("/api/model-settings");
      if (!modelSettings.open || load !== modelLoad) return;
      savedKeyProvider = data.settings.has_api_key ? data.settings.provider : null;
      const previousCatalog = data.deepseek_model ? { deepseek: { name: "DeepSeek", model: data.deepseek_model } } : {};
      apiProviders = new Map(Object.entries(data.remote_providers ?? previousCatalog));
      modelProvider.replaceChildren(...builtinProviders, ...Array.from(apiProviders,
        ([id, provider]) => new Option(`${provider.name} API`, id)));
      ollamaModel.replaceChildren(...data.ollama.models.map((model) => new Option(model, model)));
      if (data.settings.provider === "ollama") ollamaModel.value = data.settings.model;
      modelProvider.value = data.settings.provider;
      modelProvider.disabled = false;
      refreshModelFields();
      modelProvider.focus();
    } catch {
      if (modelSettings.open && load === modelLoad) {
        bilingual(modelStatus, "暂时无法读取模型设置。关闭后可重试。", "Could not load model settings. Close and reopen to retry.");
      }
    }
  });

  modelCancel.addEventListener("click", () => modelSettings.close());
  modelSettings.addEventListener("close", () => {
    apiKey.value = "";
    apiAgree.checked = false;
  });
  modelProvider.addEventListener("change", () => {
    apiKey.value = "";
    apiAgree.checked = false;
    refreshModelFields();
  });
  ollamaModel.addEventListener("change", refreshModelFields);
  one("#model-settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (modelSave.disabled) return;
    const provider = modelProvider.value;
    const settings = { provider };
    if (provider === "ollama") settings.model = ollamaModel.value;
    if (apiProviders.has(provider)) {
      settings.api_key = apiKey.value.trim();
      settings.allow_billing = apiAgree.checked;
    }
    modelProvider.disabled = ollamaModel.disabled = apiKey.disabled = apiAgree.disabled = modelSave.disabled = true;
    modelCancel.disabled = true;
    bilingual(modelStatus, "正在保存…", "Saving…");
    try {
      await request("/api/model-settings", "PUT", settings);
      modelSettings.close();
    } catch (error) {
      modelProvider.disabled = false;
      refreshModelFields();
      bilingual(modelStatus, "无法保存设置，请检查模型或 API Key。", "Could not save settings. Check the model or API key.");
      if (error.code === "secure_model_service_required") {
        bilingual(modelStatus, "API Key 需要本机 AI 服务或 HTTPS。", "API keys require a local or HTTPS AI service.");
      }
    } finally {
      modelCancel.disabled = false;
    }
  });
  modelSettings.addEventListener("cancel", (event) => {
    if (modelCancel.disabled) event.preventDefault();
  });

  function addMessage(author, content) {
    const entry = node("div", undefined, `da-message da-message-${author}`);
    entry.append(node("div", content, "da-bubble"));
    messages.append(entry);
    entry.scrollIntoView({ block: "nearest" });
  }

  function marketQueries(message) {
    if (!/报价|价格|现价|行情|多少|币价|成本|比价|\b(price|quote|cost|compare)\b/i.test(message)) return [];
    const explicit = message.match(/\b[A-Z0-9]{2,12}[\/_-][A-Z0-9]{2,12}\b/gi);
    if (explicit) return [...new Set(explicit.map((value) => value.toUpperCase()))].slice(0, 5);
    const named = [/\b(BTC|Bitcoin)\b|比特币/i, /\b(ETH|Ethereum)\b|以太/i, /\b(SOL|Solana)\b|索拉纳/i];
    const selected = pairs.filter((_, index) => named[index].test(message));
    const otherTickers = (message.match(/\b[A-Z][A-Z0-9]{1,11}\b/g) || [])
      .filter((ticker) => !["USDT", "AI"].includes(ticker) && !named.some((name) => name.test(ticker)));
    return [...new Set([...selected, ...otherTickers])].slice(0, 5);
  }

  one("#assistant-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    send.disabled = newChat.disabled = true;
    replyModel.hidden = true;
    addMessage("user", message);
    input.value = "";
    try {
      const data = await request("/api/assistant/chat", "POST", { message, history, market_queries: marketQueries(message) });
      addMessage("ai", data.reply);
      if (data.generation === "local_model") {
        text(replyModel, data.model_name ? `Ollama · ${data.model_name}` : "Ollama");
      } else if (data.generation === "remote_model") {
        text(replyModel, data.model_name ? `API · ${data.model_name}` : "API");
      } else if (data.generation === "template_model_unavailable") {
        bilingual(replyModel, "模型不可用 · 内置回复", "Model unavailable · Built-in reply");
      } else {
        bilingual(replyModel, "内置回复", "Built-in reply");
      }
      replyModel.hidden = false;
      // Account facts stay out of the browser-provided history for later model calls.
      if (!data.account) {
        history = [...history, { role: "user", content: message.slice(0, 800) },
          { role: "assistant", content: data.reply.slice(0, 800) }].slice(-6);
      }
    } catch (error) {
      addMessage("ai", errorMessage(error));
      input.value = message;
    } finally {
      send.disabled = newChat.disabled = false;
    }
  });

  const accountNotice = notice(one(".da-holdings"), "account-status");
  const riskNotice = notice(one(".da-holdings"), "risk-status");
  const pending = node("div", undefined, "da-integration-notice");
  pending.id = "open-orders";
  one(".da-holdings").append(pending);
  const holdings = one(".da-holdings tbody");
  const cards = all(".da-kpis-account .da-kpi");
  bilingual(one(".da-holdings h2"), "持仓与挂单", "Holdings and open orders");
  const holdingColumns = all(".da-holdings th");
  bilingual(holdingColumns[4], "估值报价来源", "Valuation quote source");
  bilingual(holdingColumns[5], "报价时间（UTC）", "Quote time (UTC)");
  bilingual(cards[1].querySelector("span"), "未实现盈亏", "Unrealized P&L");
  hide(".da-kpis-account .da-kpi small");
  const accountTime = one(".da-holdings .da-panelhead p");
  const tradeHistory = one("#trade-history tbody");
  const historyStatus = one("#trade-history-status");
  const historyMore = one("#trade-history-more");
  const loadedTradeIds = new Set();
  let historyOffset = 0;
  let accountVersion = 0;

  function loadOpenOrders(orders) {
    const heading = node("strong");
    bilingual(heading, `挂单（${orders.length}）`, `Open orders (${orders.length})`);
    const list = node("ul");
    for (const order of orders) {
      const item = node("li", `${order.symbol} · ${order.side} · ${order.quantity} @ ${order.limit_price ?? "—"} `);
      const cancel = node("button", "", "da-rowbtn");
      cancel.type = "button";
      bilingual(cancel, "撤单", "Cancel order");
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await request(`/api/orders/${order.order_id}/cancel`, "POST", {});
          await loadAccount();
        } catch (error) {
          text(accountNotice, errorMessage(error));
          cancel.disabled = false;
        }
      });
      item.append(cancel);
      list.append(item);
    }
    pending.replaceChildren(heading, list);
  }

  async function loadTradeHistory(version, offset) {
    historyMore.disabled = true;
    bilingual(historyStatus, "正在读取成交记录…", "Loading trades…");
    try {
      const query = new URLSearchParams({ offset, limit: 20, sort: "newest" });
      const { trades, total } = await request(`/api/account/transactions?${query}`);
      if (version !== accountVersion) return;
      for (const trade of trades) {
        if (loadedTradeIds.has(trade.trade_id)) continue;
        loadedTradeIds.add(trade.trade_id);
        const direction = node("span");
        if (trade.side === "buy") bilingual(direction, "买入", "Buy");
        else bilingual(direction, "卖出", "Sell");
        tableRow(tradeHistory, [trade.symbol, direction, trade.quantity,
          money(trade.price, trade.symbol.split("/")[1]), trade.source, time(trade.as_of)]);
      }
      historyOffset = offset + trades.length;
      historyMore.hidden = historyOffset >= total;
      if (total === 0) bilingual(historyStatus, "暂无成交记录", "No trades yet");
      else text(historyStatus, "");
    } catch {
      if (version === accountVersion) {
        bilingual(historyStatus, "成交记录暂不可用。", "Trade history unavailable.");
      }
    } finally {
      if (version === accountVersion) historyMore.disabled = false;
    }
  }

  historyMore.addEventListener("click", () => loadTradeHistory(accountVersion, historyOffset));

  async function loadAccount() {
    const version = ++accountVersion;
    holdings.replaceChildren();
    pending.replaceChildren();
    tradeHistory.replaceChildren();
    loadedTradeIds.clear();
    historyOffset = 0;
    historyMore.hidden = true;
    loadTradeHistory(version, 0);
    text(accountTime, "—");
    text(riskNotice, "");
    text(one(".da-railsummary strong"), "—");
    cards.forEach((card) => text(card.querySelector("strong"), "—"));
    bilingual(accountNotice, "正在读取中台账本…", "Loading middle-office ledger…");
    try {
      const data = await request("/api/account/summary");
      if (version !== accountVersion) return;
      const ledger = data.portfolio;
      const currency = ledger.valuation_currency;
      const balance = ledger.balances.find((row) => row.currency === currency);
      const values = [ledger.total_assets, ledger.unrealized_pnl, ledger.fees_by_currency[currency] ?? "0", balance?.available];
      values.forEach((value, index) => text(cards[index].querySelector("strong"), money(value, currency)));
      text(one(".da-railsummary strong"), money(balance?.available, currency));
      text(accountTime, time(data.as_of));
      for (const holding of ledger.positions) tableRow(holdings, [holding.symbol, holding.quantity,
        money(holding.market_value, holding.symbol.split("/")[1]), money(holding.unrealized_pnl, holding.symbol.split("/")[1]),
        holding.source, time(holding.as_of)]);
      loadOpenOrders(data.account.open_orders);
      if (data.state === "ok") text(accountNotice, "");
      else bilingual(accountNotice, `账本数据不完整 · ${data.reasons.join(", ")}`, `Partial ledger data · ${data.reasons.join(", ")}`);
      try {
        const risk = await request(`/api/risk?${new URLSearchParams({ quote_currency: currency })}`);
        if (version !== accountVersion) return;
        const exposure = money(risk.summary?.gross_exposure, currency);
        bilingual(riskNotice, `AI 风险 · ${risk.state} · 总敞口 ${exposure}`, `AI risk · ${risk.state} · Gross exposure ${exposure}`);
      } catch (error) {
        if (version === accountVersion) bilingual(riskNotice, `AI 风险读取失败 · ${errorMessage(error)}`, `AI risk unavailable · ${errorMessage(error)}`);
      }
    } catch (error) {
      if (version !== accountVersion) return;
      text(accountNotice, errorMessage(error));
    }
  }

  one('[data-screen-target="account"]').addEventListener("click", loadAccount);
  initializeMarket();
  loadAccount();
})();
