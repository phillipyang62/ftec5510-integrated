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
  const apiMessages = new Map(Object.entries({
    insufficient_balance: ["可用余额不足。", "Insufficient available balance."],
    insufficient_position: ["可用持仓不足。", "Insufficient available holdings."],
    insufficient_top_size: ["报价数量不足，请减少委托数量。", "The quote cannot cover this quantity. Enter a smaller amount."],
    quote_unavailable: ["当前暂无报价。", "No quote is available."],
    invalid_number: ["请检查委托数量和价格。", "Check the order quantity and price."],
    preview_expired: ["预览已过期，请重新预览。", "The preview expired. Preview the order again."],
    too_many_previews: ["请稍候再预览。", "Wait a moment before previewing again."],
    order_not_found: ["未找到这笔订单。", "Order not found."],
  }));
  const requestError = (error, zh, en) => apiMessages.get(error.code) ?? [zh, en];
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
    bilingual(one('label[for="account-name"]'), "账户名", "Account name");
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
          bilingual(status, "登录失败，请重试。", "Could not sign in. Try again.");
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
    ".da-segmented, .da-chips, .da-quote-pair, .da-quote-panel .da-textbtn, .da-quote-panel .da-footnote, " +
    "#screen-compare .da-headactions .da-primary, #screen-trade .da-headactions, .da-watchlist .da-iconbtn, " +
    ".da-order-summary > div:nth-child(3), .da-context-panel, " +
    ".da-account-grid, .da-order .da-panelhead p, .da-precheck strong");
  bilingual(one("#compare-title"), "资产组 NBBO 比价", "Asset-group NBBO");
  bilingual(one(".da-quote-panel h2"), "资产组 NBBO 盘口", "Asset-group NBBO books");
  bilingual(one("#trade-title"), "模拟下单", "Simulated order");
  bilingual(one('[data-screen-target="trade"] span'), "模拟下单", "Simulated order");
  bilingual(one(".da-watchlist h2"), "模拟下单币种", "Simulated order assets");
  hide(".da-watchlist .da-panelhead p");
  one(".da-railsummary button").addEventListener("click", () => navigate("account"));

  const defaultPairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
  const assets = all('[data-choice-group="compare-asset"]');
  const tradeProducts = one("#trade-products");
  const productRequirements = one("#trade-product-requirements");
  const requirementsList = one("#trade-requirements-list");
  bilingual(one("#trade-requirements-title"), "五维门槛", "Five-dimensional requirements");
  const dimensionNames = {
    FC: ["财务承载力", "Financial capacity"],
    RA: ["风险意愿", "Risk willingness"],
    KE: ["认知与经验", "Knowledge and experience"],
    BD: ["行为纪律", "Behavioral discipline"],
    OC: ["目标与约束", "Objectives and constraints"],
  };
  let tradeCatalog = new Map(defaultPairs.map((symbol) => [symbol, { symbol }]));
  let pair = defaultPairs[0];
  let side = "buy";
  let marketVersion = 0;
  let marketTimer;
  let marketRefreshMs = null;
  const amount = one("#order-amount");
  const kind = one("#order-type");
  const limit = one("#order-limit");
  const limitField = limit.closest("label");
  const venue = one("#venue-select");
  const publicAssetFilter = one("#public-asset-filter");
  const publicAsset = one("#public-asset");
  const publicPairFilter = one("#public-pair-filter");
  const publicPair = one("#public-pair");
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
  const chartPair = one("#trade-chart-pair");
  const chartPrice = one("#trade-chart-price");
  const chartSource = one("#trade-chart-source");
  const chartChange = one("#trade-chart-change");
  const tradeScreen = one("#screen-trade");
  const chartButtons = all("[data-chart-range]");
  const chartGrid = one(".da-market-chart .da-market-grid");
  const chartCandles = one(".da-market-chart .da-candle-grid");
  const chartLabels = one(".da-market-chart .da-market-labels");
  const chartStats = ["open", "high", "low", "count"].map((field) => one(`#trade-chart-${field}`));
  const chartIntervalMs = 10000;
  let chartMinutes = "5";
  let chartVersion = 0;
  let chartLoading = false;
  const marketGroups = one("#market-groups");
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

  function updateTradeProductSelection() {
    for (const button of tradeProducts.children) {
      const active = button.dataset.pair === pair;
      button.classList.toggle("is-selected", active);
      button.setAttribute("aria-pressed", String(active));
    }
    const product = tradeCatalog.get(pair);
    productRequirements.hidden = !product?.requirement_levels;
    if (productRequirements.hidden) return;
    requirementsList.replaceChildren(...Object.entries(product.requirement_levels).map(([code, level]) => {
      const row = node("div");
      row.dataset.dimension = code;
      const label = node("dt");
      bilingual(label, ...(dimensionNames[code] ?? [code, code]));
      const threshold = node("dd");
      const score = product.requirements[code];
      if (level === 0) bilingual(threshold, "0 级 · 无门槛", "Level 0 · No minimum");
      else bilingual(threshold, `${level} 级 · 至少 ${score} 分`, `Level ${level} · At least ${score} points`);
      row.append(label, threshold);
      return row;
    }));
  }

  function renderTradeProducts() {
    tradeProducts.replaceChildren(...Array.from(tradeCatalog.values(), (product) => {
      const button = node("button", undefined, "da-watchrow");
      button.type = "button";
      button.dataset.pair = product.symbol;
      button.append(node("strong", product.symbol));
      button.addEventListener("click", () => choosePair(product.symbol));
      return button;
    }));
    updateTradeProductSelection();
  }

  async function loadTradeProducts() {
    renderTradeProducts();
    try {
      const { products } = await request("/api/trading/products");
      if (!products.length) return;
      tradeCatalog = new Map(products.map((product) => [product.symbol, product]));
      renderTradeProducts();
    } catch {
      // Keep the existing three trading controls available if the AI service is offline.
    }
  }

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
    if (code === "profile_dimensions") {
      const names = (warning.unmet_dimensions ?? []).map((dimension) => dimensionNames[dimension] ?? [dimension, dimension]);
      bilingual(orderRisk,
        `${names.map(([zh]) => zh).join("、")}未达到该币种的模拟匹配要求。`,
        `${names.map(([, en]) => en).join(", ")} below this asset's simulation thresholds.`);
      return;
    }
    const messages = {
      assessment_required: [
        "尚未测评，买入风险待评估。",
        "No assessment yet. Purchase risk is unassessed.",
      ],
      product_cap: [
        `你的风险等级是 ${level}，产品上限为 ${cap}。这笔买入的产品档位 ${product} 超出了上限。`,
        `Your risk level is ${level}. The product grade ${product} exceeds your ${cap} ceiling.`,
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

  function refreshQuoteCurrencies() {
    const choices = spotAssets.get(publicAsset.value);
    publicPair.replaceChildren(...choices.map(({ symbol, currency }) => new Option(currency, symbol)));
    const preferred = choices.find(({ currency, sources }) =>
      currency === "USD" && sources.includes("HashKey") && sources.includes("OSL"))
      ?? choices.find(({ currency, sources }) => currency === "USDT" && sources.length >= 2)
      ?? choices.find(({ sources }) => sources.length >= 2)
      ?? choices[0];
    publicPair.value = preferred.symbol;
  }

  async function initializeMarket() {
    try {
      const catalog = await request("/api/market/catalog");
      groupRefreshMs = Object.values(catalog.pairs).some((sources) =>
        sources.some((source) => String(source).startsWith("demo:MDGateway:")))
        ? 2000
        : 10000;
      for (const [symbol, sources] of Object.entries(catalog.pairs)) {
        const [asset, currency] = symbol.split("/");
        if (!spotAssets.has(asset)) spotAssets.set(asset, []);
        spotAssets.get(asset).push({ symbol, currency, sources });
      }
      if (spotAssets.size) {
        const tickers = [...spotAssets.keys()].sort();
        publicAsset.replaceChildren(...tickers.map((ticker) => new Option(ticker, ticker)));
        if (spotAssets.has("BTC")) publicAsset.value = "BTC";
        refreshQuoteCurrencies();
        publicAssetFilter.hidden = publicPairFilter.hidden = true;
        assets[0].parentElement.hidden = true;
      }
    } catch {
      // A missing catalog leaves the existing trade pairs available.
    }
    choosePair(pair);
    loadAssetGroups();
    if (!groupTimer) {
      groupTimer = setInterval(() => {
        if (!document.hidden && !one("#screen-compare").hidden) loadAssetGroups();
      }, groupRefreshMs);
    }
  }

  function venueQuotes(symbol) {
    const query = new URLSearchParams({ symbol, quantity: "0.01", side: "buy" });
    return request(`/api/market/venues?${query}`);
  }

  function svgNode(tag, attributes, label) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    if (label !== undefined) text(element, label);
    return element;
  }

  function clearPriceChart() {
    chartGrid.replaceChildren();
    chartCandles.replaceChildren();
    chartLabels.replaceChildren();
    for (const element of [chartPrice, chartChange, ...chartStats]) text(element, "—");
    chartChange.classList.remove("da-positive", "da-negative");
  }

  function renderPriceChart(result) {
    clearPriceChart();
    const { candles, start, end, quote_currency: currency, simulated, source, status, as_of: asOf } = result;
    if (!candles.length) {
      bilingual(chartSource, "正在积累报价，暂无走势", "Collecting quotes; no history yet");
      return;
    }
    const sourceLabel = source.replace(/^demo:(?:MDGateway:)?/, "");
    const quotesZh = simulated ? "模拟报价" : "公开报价";
    const quotesEn = simulated ? "Simulated quotes" : "Public quotes";
    bilingual(chartSource, `${quotesZh} · ${sourceLabel} · ${time(asOf)}${status === "stale" ? " · 报价已过期" : ""}`,
      `${quotesEn} · ${sourceLabel} · ${time(asOf)}${status === "stale" ? " · Stale quotes" : ""}`);
    const opening = Number(candles[0].open);
    const latest = candles.at(-1).close;
    const high = Math.max(...candles.map(({ high }) => Number(high)));
    const low = Math.min(...candles.map(({ low }) => Number(low)));
    const change = (Number(latest) / opening - 1) * 100;
    text(chartPrice, money(latest, currency));
    text(chartChange, `${change > 0 ? "+" : ""}${change.toFixed(3)}%`);
    chartChange.classList.toggle("da-positive", change > 0);
    chartChange.classList.toggle("da-negative", change < 0);
    [money(candles[0].open, currency), money(high, currency), money(low, currency), candles.length]
      .forEach((value, index) => text(chartStats[index], value));

    const windowStart = Date.parse(start);
    const windowSize = Date.parse(end) - windowStart;
    const interval = result.interval_seconds * 1000;
    const left = 12, right = 670, top = 14, bottom = 268;
    const padding = Math.max((high - low) * 0.12, Math.min(high * 0.01, 0.01), 0.00000001);
    const upper = high + padding, lower = Math.max(0, low - padding);
    const priceY = (price) => top + (upper - Number(price)) / (upper - lower) * (bottom - top);
    const candleWidth = Math.min(16, (right - left) * interval / windowSize * 0.65);
    const priceFormat = new Intl.NumberFormat(document.documentElement.lang, {
      minimumFractionDigits: 2, maximumFractionDigits: high < 0.01 ? 8 : high < 10 ? 4 : 2,
    });
    for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
      const level = upper - (upper - lower) * fraction;
      const height = priceY(level);
      chartGrid.append(svgNode("line", { x1: left, y1: height, x2: right, y2: height }));
      chartLabels.append(svgNode("text", { x: right + 8, y: height + 3 }, priceFormat.format(level)));
    }
    for (const fraction of [0, 1 / 3, 2 / 3, 1]) {
      const x = left + (right - left) * fraction;
      const label = new Date(windowStart + windowSize * fraction).toISOString().slice(11, 19);
      chartLabels.append(svgNode("text", { x, y: 289, "text-anchor": fraction === 0 ? "start" : fraction === 1 ? "end" : "middle" }, label));
    }
    for (const candle of candles) {
      const x = left + (Date.parse(candle.start) - windowStart + interval / 2) / windowSize * (right - left);
      const openY = priceY(candle.open), closeY = priceY(candle.close);
      const group = svgNode("g", { class: Number(candle.close) >= Number(candle.open) ? "is-up" : "is-down" });
      group.append(
        svgNode("title", {}, `${time(candle.start)} · O ${candle.open} / H ${candle.high} / L ${candle.low} / C ${candle.close} ${currency}`),
        svgNode("line", { x1: x, y1: priceY(candle.high), x2: x, y2: priceY(candle.low) }),
        svgNode("rect", { x: x - candleWidth / 2, y: Math.min(openY, closeY), width: candleWidth,
          height: Math.max(1, Math.abs(openY - closeY)), rx: 1 }),
      );
      chartCandles.append(group);
    }
  }

  async function loadPriceChart(reset = false) {
    if (tradeScreen.hidden || (chartLoading && !reset)) return;
    const version = ++chartVersion;
    chartLoading = true;
    text(chartPair, pair);
    if (reset) {
      clearPriceChart();
      bilingual(chartSource, "正在读取中台报价…", "Loading middle-office quotes…");
    }
    try {
      const query = new URLSearchParams({ symbol: pair, minutes: chartMinutes });
      const result = await request(`/api/market/history?${query}`);
      if (version === chartVersion) renderPriceChart(result);
    } catch {
      if (version === chartVersion) {
        clearPriceChart();
        bilingual(chartSource, "报价走势读取失败", "Price history unavailable");
      }
    } finally {
      if (version === chartVersion) chartLoading = false;
    }
  }

  const chartStatLabels = [["区间开盘", "Window open"], ["区间最高", "Window high"],
    ["区间最低", "Window low"], ["K 线数", "Candles"]];
  all(".da-chart-stats small").forEach((label, index) => bilingual(label, ...chartStatLabels[index]));
  bilingual(one("#trade-chart-caption"), "每 10 秒更新 · 时间为 UTC", "Updates every 10 sec · UTC");
  bilingual(one("#trade-chart-svg-title"), "下单价格走势图", "Order price chart");
  chartButtons.forEach((button) => {
    const minutes = button.dataset.chartRange;
    bilingual(button, `${minutes} 分钟`, `${minutes} min`);
    button.addEventListener("click", () => {
      chartMinutes = minutes;
      chartButtons.forEach((peer) => {
        peer.classList.toggle("is-selected", peer === button);
        peer.setAttribute("aria-pressed", String(peer === button));
      });
      loadPriceChart(true);
    });
  });
  one('[data-screen-target="trade"]').addEventListener("click", () => loadPriceChart(true));
  setInterval(() => { if (!document.hidden) loadPriceChart(); }, chartIntervalMs);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadPriceChart(); });

  const FX_PER_USD = Object.freeze({ USD: 1, USDT: 1, HKD: 7.8 });
  const ASSET_GROUPS = Object.freeze([
    { asset: "BTC", zh: "比特币", en: "Bitcoin" },
    { asset: "ETH", zh: "以太坊", en: "Ethereum" },
    { asset: "SOL", zh: "索拉纳", en: "Solana" },
    { asset: "XRP", zh: "瑞波币", en: "XRP" },
    { asset: "ADA", zh: "艾达币", en: "Cardano" },
    { asset: "LINK", zh: "Chainlink", en: "Chainlink" },
    { asset: "AVAX", zh: "雪崩协议", en: "Avalanche" },
    { asset: "DOGE", zh: "狗狗币", en: "Dogecoin" },
    { asset: "USDC", zh: "USDC", en: "USDC" },
    { asset: "RLUSD", zh: "RLUSD", en: "RLUSD" },
  ]);
  let groupVersion = 0;
  let groupTimer = null;
  let groupRefreshMs = 10000;

  function numeric(value) {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
  }

  function usdEquivalent(value, currency) {
    const amount = numeric(value);
    const rate = FX_PER_USD[currency];
    return amount == null || !rate ? null : amount / rate;
  }

  function formatGroupPrice(value, currency = "USD") {
    const amount = numeric(value);
    if (amount == null) return "—";
    const digits = amount >= 10 ? 2 : amount >= 0.01 ? 4 : 8;
    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(amount) + ` ${currency}`;
  }

  function venueName(source) {
    return String(source || "Unknown")
      .replace(/^demo:MDGateway:/i, "")
      .replace(/^demo:/i, "");
  }

  function groupContracts(asset) {
    const contracts = spotAssets.get(asset);
    return contracts?.length
      ? contracts.map((entry) => entry.symbol)
      : defaultPairs.filter((symbol) => symbol.startsWith(asset + "/"));
  }

  async function loadAssetGroup(asset) {
    const symbols = groupContracts(asset);
    const results = await Promise.all(symbols.map((symbol) =>
      venueQuotes(symbol).catch(() => ({ venues: [], symbol }))
    ));
    const rows = [];
    for (const result of results) {
      for (const quote of result.venues || []) {
        const currency = quote.quote_currency || quote.symbol.split("/")[1];
        const bid = numeric(quote.bid);
        const ask = numeric(quote.ask);
        const bidUsd = usdEquivalent(quote.bid, currency);
        const askUsd = usdEquivalent(quote.ask, currency);
        if (bid == null || ask == null || bidUsd == null || askUsd == null) continue;
        rows.push({
          source: venueName(quote.source),
          sourceRaw: quote.source,
          contract: quote.symbol,
          currency,
          bid,
          ask,
          bidUsd,
          askUsd,
          asOf: quote.as_of,
        });
      }
    }
    let bestAsk = null;
    let bestBid = null;
    for (const row of rows) {
      if (!bestAsk || row.askUsd < bestAsk.askUsd - 1e-8) bestAsk = row;
      if (!bestBid || row.bidUsd > bestBid.bidUsd + 1e-8) bestBid = row;
    }
    for (const row of rows) {
      row.bestAsk = row === bestAsk;
      row.bestBid = row === bestBid;
    }
    return {
      rows,
      bestAsk,
      bestBid,
      sourceCount: new Set(rows.map((row) => row.sourceRaw)).size,
      simulated: rows.some((row) => row.sourceRaw.startsWith("demo:")),
    };
  }

  function addGroupHeader(group, definition, data) {
    const head = node("div", undefined, "da-market-group-head");
    const title = node("div", undefined, "da-group-title");
    const badge = node("b", definition.asset.slice(0, 1), "da-group-symbol");
    const copy = node("div");
    const heading = node("h3", `${definition.asset} 资产组`);
    bilingual(heading, `${definition.asset} 资产组`, `${definition.asset} asset group`);
    const details = node("p");
    const contractCount = data.rows.length;
    const [feedZh, feedEn] = !data.rows.length ? ["暂无报价", "No quotes"]
      : data.simulated ? ["模拟报价", "Simulated quotes"] : ["公开现货", "Public spot feed"];
    bilingual(details,
      `${definition.zh} · ${data.sourceCount} 家交易所 · ${contractCount} 条报价 · ${feedZh}`,
      `${definition.en} · ${data.sourceCount} venues · ${contractCount} quotes · ${feedEn}`);
    details.dataset.contractCount = String(contractCount);
    copy.append(heading, details);
    title.append(badge, copy);

    const stats = node("div", undefined, "da-group-stats");
    const askStat = node("div", undefined, "da-group-stat is-ask");
    const askLabel = node("small", "最佳 Ask（买入）");
    bilingual(askLabel, "最佳 Ask（买入）", "Best ask (buy)");
    const askValue = node("strong", data.bestAsk
      ? `${formatGroupPrice(data.bestAsk.askUsd, "USD")} · ${data.bestAsk.source} · ${data.bestAsk.contract}`
      : "—");
    askStat.append(askLabel, askValue);
    const bidStat = node("div", undefined, "da-group-stat is-bid");
    const bidLabel = node("small", "最佳 Bid（卖出）");
    bilingual(bidLabel, "最佳 Bid（卖出）", "Best bid (sell)");
    const bidValue = node("strong", data.bestBid
      ? `${formatGroupPrice(data.bestBid.bidUsd, "USD")} · ${data.bestBid.source} · ${data.bestBid.contract}`
      : "—");
    bidStat.append(bidLabel, bidValue);
    const spreadValue = data.bestAsk && data.bestBid
      ? (data.bestAsk.askUsd - data.bestBid.bidUsd) / ((data.bestAsk.askUsd + data.bestBid.bidUsd) / 2) * 10000
      : null;
    const spreadStat = node("div", undefined, "da-group-stat");
    const spreadLabel = node("small", "NBBO 价差");
    bilingual(spreadLabel, "NBBO 价差", "NBBO spread");
    const normalizedSpread = spreadValue != null && Math.abs(spreadValue) < 0.005 ? 0 : spreadValue;
    spreadStat.append(spreadLabel, node("strong", normalizedSpread == null ? "—" : `${normalizedSpread.toFixed(2)} bps`));
    stats.append(askStat, bidStat, spreadStat);
    head.append(title, stats);
    group.append(head);
  }

  function addGroupTable(group, data) {
    const wrap = node("div", undefined, "da-group-tablewrap");
    const table = node("table", undefined, "da-group-table");
    const thead = node("thead");
    const headerRow = node("tr");
    const headings = [
      ["交易所", "Venue"],
      ["合约", "Contract"],
      ["最佳 Ask（买入）", "Best ask (buy)"],
      ["最佳 Bid（卖出）", "Best bid (sell)"],
      ["USD 等值", "USD equivalent"],
      ["更新时间（UTC）", "Updated (UTC)"],
    ];
    for (const [zh, en] of headings) {
      const cell = node("th");
      bilingual(cell, zh, en);
      headerRow.append(cell);
    }
    thead.append(headerRow);

    const tbody = node("tbody");
    for (const row of data.rows) {
      const tr = node("tr");
      const venue = node("td");
      const venueWrap = node("span", undefined, "da-group-venue");
      venueWrap.append(
        node("i", row.source.slice(0, 1)),
        document.createTextNode(row.source),
      );
      venue.append(venueWrap);
      const contract = node("td");
      const contractTag = node("span", row.contract, "da-contract");
      contract.append(contractTag);
      const ask = node("td");
      ask.append(node("span", formatGroupPrice(row.ask, row.currency)));
      if (row.currency !== "USD") ask.append(node("small", formatGroupPrice(row.askUsd), "da-normalized"));
      if (row.bestAsk) {
        ask.classList.add("is-nbbo-ask");
        ask.append(node("span", "NBBO", "da-nbbo-pill"));
      }
      const bid = node("td");
      bid.append(node("span", formatGroupPrice(row.bid, row.currency)));
      if (row.currency !== "USD") bid.append(node("small", formatGroupPrice(row.bidUsd), "da-normalized"));
      if (row.bestBid) {
        bid.classList.add("is-nbbo-bid");
        bid.append(node("span", "NBBO", "da-nbbo-pill"));
      }
      const mid = node("td");
      mid.append(node("span", formatGroupPrice((row.askUsd + row.bidUsd) / 2)));
      const timestamp = node("td", time(row.asOf));
      timestamp.className = "da-group-time";
      tr.append(venue, contract, ask, bid, mid, timestamp);
      tbody.append(tr);
    }
    table.append(thead, tbody);
    wrap.append(table);
    group.append(wrap);
  }

  function renderAssetGroup(definition, data) {
    const group = node("section", undefined, "da-market-group");
    group.dataset.asset = definition.asset;
    addGroupHeader(group, definition, data);
    if (data.rows.length) addGroupTable(group, data);
    else {
      const empty = node("div", undefined, "da-group-loading");
      bilingual(empty, "该资产组暂无可用盘口。", "No quotes are available for this asset group.");
      group.append(empty);
    }
    return group;
  }

  async function loadAssetGroups() {
    const version = ++groupVersion;
    bilingual(one(".da-fresh"), "正在刷新资产组…", "Refreshing asset groups…");
    const visibleGroups = ASSET_GROUPS.filter(({ asset }) =>
      defaultPairs.includes(asset + "/USDT") ||
      spotAssets.get(asset)?.some(({ sources }) => sources.some((source) => source.startsWith("demo:MDGateway:"))));
    const groups = await Promise.all(visibleGroups.map(async (definition) => ({
      definition,
      data: await loadAssetGroup(definition.asset),
    })));
    if (version !== groupVersion) return;
    marketGroups.replaceChildren(...groups.map(({ definition, data }) => renderAssetGroup(definition, data)));
    const timestamps = groups.flatMap(({ data }) => data.rows.map((row) => row.asOf).filter(Boolean));
    const latest = timestamps.sort().at(-1);
    bilingual(one(".da-fresh"), `资产组 NBBO · ${time(latest) || "—"}`,
      `Asset NBBO · ${time(latest) || "—"}`);
  }

  async function loadMarket(selectedVenue = "", background = false) {
    const version = ++marketVersion;
    const symbol = publicPair.value || pair;
    const orderPair = pair;
    const canTrade = tradeCatalog.has(symbol);
    text(one(".da-order h2"), pair);
    text(amount.closest("label").querySelector("b"), pair.split("/")[0]);
    if (!background) {
      text(one(".da-fresh"), "—");
      marketBody.replaceChildren();
      bilingual(marketNotice, "正在读取中台报价…", "Loading middle-office quotes…");
    }
    try {
      const comparison = venueQuotes(symbol);
      const [result, orderQuotes] = await Promise.all([comparison, symbol === orderPair ? comparison : venueQuotes(orderPair)]);
      if (version !== marketVersion) return;
      const publicMarket = result.market_mode === "public";
      const simulatedFeed = result.quote_mode === "simulation";
      const preFee = result.ranking_basis === "bid_ask_excluding_fees";
      const runningSimulator = [...result.venues, ...orderQuotes.venues]
        .some((quote) => quote.source.startsWith("demo:MDGateway:"));
      const refreshMs = runningSimulator ? 2000 : 10000;
      if (marketRefreshMs !== refreshMs) {
        clearInterval(marketTimer);
        marketRefreshMs = refreshMs;
        marketTimer = setInterval(() => {
          if (!document.hidden) loadMarket(venue.value, true);
        }, refreshMs);
      }
      if (preFee) bilingual(marketColumns[3], "卖一挂单数量", "Best ask size");
      else bilingual(marketColumns[3], "手续费", "Fee");
      if (preFee) bilingual(marketColumns[5], "报价金额（未计费）", "Notional (fees excluded)");
      else bilingual(marketColumns[5], "含费总额（0.01 币）", "Total with fee (0.01 units)");
      if (!preview && !submitting) setVenues(orderQuotes.venues, background ? venue.value : selectedVenue);
      marketBody.replaceChildren();
      for (const quote of result.venues) {
        let action = "—";
        if (canTrade) {
          action = node("button", "", "da-rowbtn");
          action.type = "button";
          bilingual(action, "选择", "Select");
          action.addEventListener("click", () => { choosePair(symbol, quote.source); navigate("trade"); });
        }
        const timestamp = node("span", time(quote.as_of));
        if (quote.timestamp_source === "collected") bilingual(timestamp, `${time(quote.as_of)} · 采集`, `${time(quote.as_of)} · collected`);
        const venueLabel = node("span", quote.source);
        if (publicMarket) {
          const last = node("small");
          const price = money(quote.price, quote.quote_currency);
          bilingual(last, `最新成交 ${price}`, `Last trade ${price}`);
          venueLabel.append(document.createElement("br"), last);
        }
        const fee = quote.fee_rate === null ? "—" : `${(Number(quote.fee_rate) * 100).toPrecision(3)}%`;
        let notional = money(preFee ? quote.notional : quote.total, quote.quote_currency);
        if (quote.quantity_covered === false) {
          notional = node("span");
          bilingual(notional, "卖一档数量不足", "Insufficient at best ask");
        }
        tableRow(marketBody, [venueLabel, money(quote.ask, quote.quote_currency), money(quote.bid, quote.quote_currency),
          preFee ? money(quote.ask_size, symbol.split("/")[0]) : fee, timestamp, notional, action]);
      }
      const latest = result.venues.map((quote) => quote.as_of).sort().at(-1);
      if (publicMarket && !simulatedFeed) bilingual(one(".da-fresh"), `公开现货 · ${time(latest)}`, `Public spot · ${time(latest)}`);
      else bilingual(one(".da-fresh"), `模拟 · ${time(latest)}`, `Simulation · ${time(latest)}`);
      const best = orderQuotes.venues[0];
      text(one(".da-quote-pill"), best ? money(best.price, best.quote_currency) : "—");
      if (result.status === "ok") text(marketNotice, "");
      else bilingual(marketNotice, "有效报价不足两家。", "Fewer than two current venues are available.");
    } catch (error) {
      if (version === marketVersion) {
        marketBody.replaceChildren();
        text(one(".da-quote-pill"), "—");
        text(one(".da-fresh"), "—");
        bilingual(marketNotice, ...requestError(error, "报价暂不可用。", "Quotes are temporarily unavailable."));
      }
    }
  }

  function choosePair(nextPair, selectedVenue = "") {
    if (!tradeCatalog.has(nextPair)) return;
    const pairChanged = nextPair !== pair;
    pair = nextPair;
    assets.forEach((button, position) => {
      const active = defaultPairs[position] === pair;
      button.classList.toggle("is-selected", active);
      button.setAttribute("aria-pressed", String(active));
    });
    updateTradeProductSelection();
    invalidateOrder();
    text(one(".da-quote-pill"), "—");
    setVenues([], selectedVenue);
    loadMarket(selectedVenue);
    if (pairChanged) loadPriceChart(true);
  }

  defaultPairs.forEach((symbol, index) => {
    assets[index].addEventListener("click", () => choosePair(symbol));
  });
  publicAsset.addEventListener("change", () => {
    refreshQuoteCurrencies();
    loadMarket(venue.value);
  });
  publicPair.addEventListener("change", () => loadMarket(venue.value));
  one("#screen-compare .da-headactions .da-secondary").addEventListener("click", () => {
    invalidateOrder();
    loadMarket(venue.value);
    loadAssetGroups();
  });
  one('[data-screen-target="compare"]').addEventListener("click", loadAssetGroups);
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
        const names = { filled: ["已成交", "Filled"], open: ["已挂单", "Open"],
          rejected: ["委托被拒绝", "Order rejected"], cancelled: ["已撤单", "Cancelled"] };
        const [zh, en] = result.reason && apiMessages.has(result.reason)
          ? apiMessages.get(result.reason)
          : names[result.status] ?? ["订单状态已更新", "Order status updated"];
        bilingual(orderNotice, zh, en);
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
        const feeZh = result.fee_assumed ? " · 手续费暂按 0 估算" : "";
        const feeEn = result.fee_assumed ? " · Fee estimated at zero" : "";
        bilingual(orderNotice, `${result.source} · ${result.expires_in} 秒内确认${feeZh}`, `${result.source} · Confirm within ${result.expires_in}s${feeEn}`);
        orderStatus.hidden = false;
      }
    } catch (error) {
      if (error.code === "preview_expired") invalidateOrder();
      if (version === orderVersion || confirming) {
        bilingual(orderNotice, ...requestError(error, "暂时无法处理订单，请重试。", "Could not process the order. Try again."));
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
  const lessonAssets = one("#lesson-assets");
  const lessonTrade = one("#lesson-trade");
  const lessonRetry = one("#lesson-retry");
  let lessonVersion = 0;

  async function loadLesson() {
    const version = ++lessonVersion;
    lesson.hidden = false;
    lessonFocus.hidden = lessonTrade.hidden = lessonRetry.hidden = true;
    lessonAssets.hidden = true;
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
      const examples = data.asset_examples ?? [];
      lessonAssets.replaceChildren(...examples.map((product) => {
        const example = node("li");
        const needsOc = product.group === "stablecoin" && product.unmet?.includes("OC");
        const basisZh = `${product.symbol} · ${product.basis.zh}`;
        const basisEn = `${product.symbol} · ${product.basis.en}`;
        bilingual(example, needsOc ? `${basisZh} ${product.reasons.zh}` : basisZh,
          needsOc ? `${basisEn} ${product.reasons.en}` : basisEn);
        return example;
      }));
      lessonAssets.hidden = examples.length === 0;
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
  function localizeKeyPlaceholder() {
    const keepsKey = apiProviders.has(modelProvider.value) && savedKeyProvider === modelProvider.value;
    apiKey.placeholder = keepsKey
      ? (document.documentElement.lang === "en" ? "Leave blank to keep the saved key" : "留空可保留已保存的 Key")
      : "";
  }

  document.addEventListener("harbor-language", localizeKeyPlaceholder);

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
    localizeKeyPlaceholder();
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
    const bubble = node("div", undefined, "da-bubble");
    if (typeof content === "string") text(bubble, content);
    else bilingual(bubble, content.zh, content.en);
    entry.append(bubble);
    messages.append(entry);
    entry.scrollIntoView({ block: "nearest" });
  }

  function marketQueries(message) {
    if (!/报价|价格|现价|行情|多少|币价|成本|比价|\b(price|quote|cost|compare)\b/i.test(message)) return [];
    const explicit = message.match(/\b[A-Z0-9]{2,12}[\/_-][A-Z0-9]{2,12}\b/gi);
    if (explicit) return [...new Set(explicit.map((value) => value.toUpperCase()))].slice(0, 5);
    const named = [/\b(BTC|Bitcoin)\b|比特币/i, /\b(ETH|Ethereum)\b|以太/i, /\b(SOL|Solana)\b|索拉纳/i];
    const selected = defaultPairs.filter((_, index) => named[index].test(message));
    const words = message.match(/\b[A-Z][A-Z0-9]{1,11}\b/gi) ?? [];
    for (const word of words) {
      const ticker = word.toUpperCase();
      if (named.some((name) => name.test(ticker))) continue;
      if (tradeCatalog.has(`${ticker}/USDT`)) selected.push(`${ticker}/USDT`);
      else if (word === ticker && !["USDT", "AI"].includes(ticker)) selected.push(ticker);
    }
    return [...new Set(selected)].slice(0, 5);
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
      const generated = ["local_model", "remote_model"].includes(data.generation);
      if (data.reply) addMessage("ai", data.reply);
      if (data.model_status?.message && !generated) addMessage("ai", data.model_status.message);
      if (data.generation === "local_model") {
        text(replyModel, data.model_name ? `Ollama · ${data.model_name}` : "Ollama");
      } else if (data.generation === "remote_model") {
        text(replyModel, data.model_name ? `API · ${data.model_name}` : "API");
      } else if (data.generation === "model_not_configured") {
        bilingual(replyModel, "尚未配置模型", "Model setup required");
      } else if (data.generation === "model_unavailable") {
        bilingual(replyModel, "模型调用失败", "Model request failed");
      } else if (data.generation === "model_privacy_blocked") {
        bilingual(replyModel, "账户数据仅本机处理", "Account data stays local");
      } else if (data.generation === "policy_guard") {
        bilingual(replyModel, "回复未通过核验", "Response verification failed");
      } else {
        bilingual(replyModel, "测评与数据规则", "Assessment and data rules");
      }
      replyModel.hidden = false;
      if (!data.reply && !input.value) input.value = message;
      // Account facts stay out of the browser-provided history for later model calls.
      if (generated && !data.account) {
        history = [...history, { role: "user", content: message.slice(0, 800) },
          { role: "assistant", content: data.reply.slice(0, 800) }].slice(-6);
      }
    } catch {
      addMessage("ai", {zh: "暂时无法发送消息，请重试。", en: "Could not send the message. Try again."});
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
    pending.hidden = orders.length === 0;
    const heading = node("strong");
    bilingual(heading, `挂单（${orders.length}）`, `Open orders (${orders.length})`);
    const list = node("ul");
    for (const order of orders) {
      const item = node("li");
      const terms = node("span");
      const [zh, en] = order.side === "buy" ? ["买入", "Buy"] : ["卖出", "Sell"];
      const details = `${order.quantity} @ ${order.limit_price ?? "—"}`;
      bilingual(terms, `${order.symbol} · ${zh} · ${details}`, `${order.symbol} · ${en} · ${details}`);
      const cancel = node("button", "", "da-rowbtn");
      cancel.type = "button";
      bilingual(cancel, "撤单", "Cancel order");
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await request(`/api/orders/${order.order_id}/cancel`, "POST", {});
          await loadAccount();
        } catch (error) {
          bilingual(accountNotice, ...requestError(error, "撤单失败，请重试。", "Could not cancel the order. Try again."));
          cancel.disabled = false;
        }
      });
      item.append(terms, " ", cancel);
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

  const depositDialog = one("#deposit-dialog");
  const depositAmount = one("#deposit-amount");
  const depositSubmit = one("#deposit-submit");
  const depositCancel = one("#deposit-cancel");
  const depositStatus = one("#deposit-status");
  const depositResult = one("#deposit-result");
  let depositRequest = null;

  one("#deposit-open").addEventListener("click", () => {
    text(depositStatus, "");
    depositDialog.showModal();
  });
  depositCancel.addEventListener("click", () => depositDialog.close());
  depositDialog.addEventListener("cancel", (event) => {
    if (depositSubmit.disabled) event.preventDefault();
  });
  depositAmount.addEventListener("input", () => text(depositStatus, ""));
  one("#deposit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (depositSubmit.disabled) return;
    const amount = depositAmount.value.trim();
    if (!/^\d+(?:\.\d{1,8})?$/.test(amount) || !/[1-9]/.test(amount)) {
      bilingual(depositStatus, "请输入大于 0 的金额，最多 8 位小数。", "Enter a positive amount with up to 8 decimal places.");
      depositAmount.focus();
      return;
    }
    if (depositRequest?.amount !== amount) depositRequest = { amount, request_id: crypto.randomUUID() };
    depositAmount.disabled = depositSubmit.disabled = depositCancel.disabled = true;
    bilingual(depositStatus, "正在充值…", "Adding funds…");
    try {
      const receipt = await request("/api/account/deposits", "POST", depositRequest);
      const credited = money(receipt.amount, receipt.currency);
      depositRequest = null;
      depositAmount.value = "";
      depositDialog.close();
      bilingual(depositResult, `已充值 ${credited}`, `Added ${credited}`);
      depositResult.hidden = false;
      loadAccount();
    } catch (error) {
      if (error.code === "invalid_number" || error.code === "invalid_amount") {
        bilingual(depositStatus, "金额超出账户上限。", "The amount exceeds the account limit.");
      } else {
        bilingual(depositStatus, "充值未确认，请重试。", "Top-up unconfirmed. Please retry.");
      }
    } finally {
      depositAmount.disabled = depositSubmit.disabled = depositCancel.disabled = false;
    }
  });

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
      else if (data.reasons.includes("missing_or_stale_quote")) {
        bilingual(accountNotice, "部分持仓缺少近期报价。", "Some holdings lack a recent quote.");
      } else {
        bilingual(accountNotice, "部分账户数据暂不可用。", "Some account data is unavailable.");
      }
      try {
        const risk = await request(`/api/risk?${new URLSearchParams({ quote_currency: currency })}`);
        if (version !== accountVersion) return;
        const exposure = risk.summary?.gross_exposure;
        if (risk.state === "ok" && exposure != null) {
          bilingual(riskNotice, `总敞口 ${money(exposure, currency)}`, `Gross exposure ${money(exposure, currency)}`);
        } else if (risk.state === "partial") {
          bilingual(riskNotice, "部分持仓暂无法计入风险统计。", "Some holdings could not be included in the risk totals.");
        } else {
          bilingual(riskNotice, "风险统计暂不可用。", "Risk totals are temporarily unavailable.");
        }
      } catch {
        if (version === accountVersion) bilingual(riskNotice, "风险统计暂不可用。", "Risk totals are temporarily unavailable.");
      }
    } catch {
      if (version !== accountVersion) return;
      bilingual(accountNotice, "账户数据暂不可用。", "Account data is temporarily unavailable.");
    }
  }

  one('[data-screen-target="account"]').addEventListener("click", loadAccount);
  loadTradeProducts();
  initializeMarket();
  loadAccount();
})();
