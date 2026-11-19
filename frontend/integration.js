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

  async function request(path, method = "GET", payload) {
    const options = { method, headers: { Accept: "application/json" } };
    if (payload !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
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

  hide(".da-topmeta .da-iconbtn, .da-avatar, #screen-compare .da-kpis, .da-route-panel, .da-crossasset, " +
    ".da-segmented, .da-quote-panel .da-textbtn, .da-quote-panel .da-footnote, " +
    "#screen-compare .da-headactions .da-primary, #screen-trade .da-headactions, .da-watchlist .da-iconbtn, " +
    ".da-watchlist-head, .da-watchfoot, .da-watchrow > :not(.da-asset), .da-quickamounts, " +
    ".da-order-summary > div:nth-child(3), .da-context-panel, #screen-account .da-headactions, " +
    ".da-account-grid, .da-holdings .da-textbtn");
  bilingual(one(".da-status"), "模拟账户", "Simulation account");
  bilingual(one("#screen-compare .da-pagehead p:not(.da-eyebrow)"), "比较同一交易对的买卖报价。", "Compare venues for the same trading pair.");
  bilingual(one("#screen-trade .da-pagehead p:not(.da-eyebrow)"), "选择币种并预览或提交模拟订单。", "Select an asset, preview it, and place a simulated order.");
  bilingual(one(".da-watchlist h2"), "选择币种", "Choose an asset");
  hide(".da-watchlist .da-panelhead p");
  bilingual(one("#screen-assistant .da-pagehead p:not(.da-eyebrow)"), "结合问卷结果、行情和模拟账户回答。", "Ask about your assessment, market quotes, or simulation account.");
  bilingual(one("#screen-account .da-pagehead p:not(.da-eyebrow)"), "查看中台账本、持仓和挂单，以及 AI 风险指标。", "View the middle-office ledger, holdings, open orders, and AI risk metrics.");
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
  const amount = one("#order-amount");
  const kind = one("#order-type");
  const limit = one("#order-limit");
  const venue = one("#venue-select");
  const submit = one("#submit-order");
  const marketBody = one(".da-quote-panel tbody");
  const marketNotice = notice(one(".da-quote-panel"), "market-status");
  const orderNotice = one(".da-precheck span");
  const marketColumns = all(".da-quote-panel th");
  bilingual(marketColumns[1], "买入价（Ask）", "Ask");
  bilingual(marketColumns[2], "卖出价（Bid）", "Bid");
  bilingual(marketColumns[4], "报价时间（UTC）", "Quote time (UTC)");
  bilingual(one(".da-order-note"), "确认后由中台按当时行情复核并模拟成交。", "Middle office rechecks the latest quote and executes in simulation.");
  bilingual(one(".da-precheck strong"), "中台交易前检查", "Middle-office order check");
  bilingual(one(".da-order-summary .da-summary-total span"), "估算净额", "Estimated net amount");
  bilingual(amount.closest("label").querySelector(":scope > span"), "委托数量", "Quantity");
  text(limit.closest("label").querySelector("b"), "USDT");
  amount.step = "any";
  amount.value = "0.01";
  kind.value = "market";
  limit.value = "";
  let preview = null;
  let submitting = false;
  let orderVersion = 0;

  function invalidateOrder() {
    preview = null;
    orderVersion++;
    limit.disabled = kind.value !== "limit";
    for (const id of ["#order-notional", "#order-fee", "#order-total"]) text(one(id), "—");
    bilingual(submit, "预览模拟订单", "Preview simulated order");
    bilingual(orderNotice, "预览时检查余额、仓位与适当性。", "Preview checks balance, position, and suitability.");
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

  async function loadMarket(selectedVenue = "", background = false) {
    const version = ++marketVersion;
    const symbol = pair;
    text(one(".da-quote-panel h2"), symbol);
    text(one(".da-order h2"), symbol);
    text(amount.closest("label").querySelector("b"), symbol.split("/")[0]);
    if (!background) {
      text(one(".da-quote-pill"), "—");
      text(one(".da-clock"), "—");
      text(one(".da-fresh"), "—");
      marketBody.replaceChildren();
      setVenues([], selectedVenue);
      bilingual(one(".da-order .da-panelhead p"), "模拟交易", "Simulated trading");
      bilingual(marketNotice, "正在读取中台报价…", "Loading middle-office quotes…");
    }
    try {
      const query = new URLSearchParams({ symbol, quantity: "0.01", side: "buy" });
      const result = await request(`/api/market/venues?${query}`);
      if (version !== marketVersion) return;
      const publicMarket = result.market_mode === "public";
      const preFee = result.ranking_basis === "bid_ask_excluding_fees";
      const compareCaption = one(".da-quote-panel .da-panelhead p");
      if (publicMarket) {
        if (!marketTimer) {
          marketTimer = setInterval(() => {
            if (!document.hidden) loadMarket(venue.value, true);
          }, 10000);
        }
        bilingual(marketColumns[3], "卖一挂单数量", "Best ask size");
        bilingual(compareCaption, "比较 0.01 币的现货报价，优先列出卖一档可覆盖的平台。", "Compare quotes for 0.01 units and prioritize venues with enough at the best ask.");
      } else {
        bilingual(marketColumns[3], "手续费", "Fee");
        bilingual(compareCaption, "按买入 0.01 币的报价比较。", "Compare quotes to buy 0.01 units.");
      }
      if (preFee) bilingual(marketColumns[5], "报价金额（未计费）", "Notional (fees excluded)");
      else bilingual(marketColumns[5], "含费总额（0.01 币）", "Total with fee (0.01 units)");
      if (!preview && !submitting) setVenues(result.venues, background ? venue.value : selectedVenue);
      marketBody.replaceChildren();
      for (const quote of result.venues) {
        const select = node("button", "", "da-rowbtn");
        select.type = "button";
        bilingual(select, "选择", "Select");
        select.addEventListener("click", () => { venue.value = quote.source; invalidateOrder(); navigate("trade"); });
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
          publicMarket ? money(quote.ask_size, symbol.split("/")[0]) : fee, timestamp, notional, select]);
      }
      const latest = result.venues.map((quote) => quote.as_of).sort().at(-1);
      text(one(".da-clock"), time(latest));
      if (publicMarket) bilingual(one(".da-fresh"), `公开现货 · ${time(latest)}`, `Public spot · ${time(latest)}`);
      else bilingual(one(".da-fresh"), `模拟 · ${time(latest)}`, `Simulation · ${time(latest)}`);
      const best = result.venues[0];
      text(one(".da-quote-pill"), best ? money(best.price, best.quote_currency) : "—");
      if (publicMarket) {
        const unavailable = [...result.excluded_sources, ...result.missing_sources];
        const details = unavailable.length ? ` · ${unavailable.join(", ")}` : "";
        if (result.status === "ok") bilingual(marketNotice, `报价未计交易费，订单仍为模拟${details}`, `Fees excluded; simulated orders only${details}`);
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

  function choosePair(index) {
    pair = pairs[index];
    for (const group of [assets, watch]) {
      group.forEach((button, position) => {
        button.classList.toggle("is-selected", position === index);
        button.setAttribute("aria-pressed", String(position === index));
      });
    }
    invalidateOrder();
    loadMarket();
  }

  pairs.forEach((_, index) => {
    assets[index].addEventListener("click", () => choosePair(index));
    watch[index].addEventListener("click", () => choosePair(index));
  });
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
        const detail = result.reason || result.order_id;
        bilingual(orderNotice, `${zh} · ${detail}`, `${en} · ${detail}`);
        loadAccount();
      } else {
        const payload = { symbol: pair, side, order_type: kind.value, quantity: amount.value };
        if (limit.value && kind.value === "limit") payload.limit_price = limit.value.trim();
        if (venue.value) payload.source = venue.value;
        const result = await request("/api/orders/preview", "POST", payload);
        if (version !== orderVersion) return;
        preview = result;
        for (const key of ["notional", "fee", "total"]) text(one(`#order-${key}`), money(result[key], result.quote_currency));
        bilingual(submit, "确认模拟下单", "Confirm simulated order");
        const feeZh = result.fee_assumed ? " · 模拟手续费按 0 计" : "";
        const feeEn = result.fee_assumed ? " · Simulated fee assumed zero" : "";
        bilingual(orderNotice, `${result.source} · ${result.expires_in} 秒内确认${feeZh}`, `${result.source} · Confirm within ${result.expires_in}s${feeEn}`);
      }
    } catch (error) {
      if (error.code === "preview_expired") invalidateOrder();
      if (version === orderVersion || confirming) text(orderNotice, errorMessage(error));
    } finally {
      submitting = submit.disabled = false;
    }
  });

  const messages = one(".da-messages");
  const input = one("#assistant-input");
  const send = one(".da-send");
  const chatStatus = one(".da-chathead p");
  let history = [];
  messages.replaceChildren();
  input.maxLength = 2000;
  bilingual(chatStatus, "模拟账户 · AI 助手", "Simulation account · AI assistant");
  one(".da-chathead button").addEventListener("click", () => { messages.replaceChildren(); history = []; input.focus(); });

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
    const newChat = one(".da-chathead button");
    send.disabled = newChat.disabled = true;
    addMessage("user", message);
    input.value = "";
    try {
      const data = await request("/api/assistant/chat", "POST", { message, history, market_queries: marketQueries(message) });
      addMessage("ai", data.reply);
      const detail = [data.mode, data.product_cap, data.generation].filter(Boolean).join(" · ");
      bilingual(chatStatus, `模拟账户 · ${detail}`, `Simulation account · ${detail}`);
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

  async function loadAccount() {
    const version = ++accountVersion;
    holdings.replaceChildren();
    pending.replaceChildren();
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
  choosePair(0);
  loadAccount();
})();
