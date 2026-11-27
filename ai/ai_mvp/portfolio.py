"""Render the read-only middle-office portfolio data in chat."""

from decimal import Decimal


def portfolio_text(snapshot, *, zh):
    holdings_title = "当前持仓" if zh else "Current holdings"
    if snapshot["state"] not in {"ok", "partial"}:
        unavailable = "暂时无法读取中台账户数据。" if zh else "Middle-office account data is currently unavailable."
        return f"{holdings_title}\n{unavailable}"

    positions = []
    for row in snapshot["positions"]:
        symbol = row["symbol"]
        base = symbol.split("/")[0]
        value = row["market_value"]
        if value is None:
            valuation = "估值暂缺" if zh else "Valuation unavailable"
        else:
            valuation = f"{'估值' if zh else 'Value'} {value} {row['quote_currency']}"
        positions.append(f"{symbol} · {row['quantity']} {base} · {valuation}")
    if not positions:
        positions.append("当前没有持仓。" if zh else "There are no open positions.")

    currency = snapshot["valuation_currency"]
    exposure_title = "风险敞口" if zh else "Risk exposure"
    exposure = snapshot["gross_exposure"]
    if exposure is not None:
        label = "持仓总市值" if zh else "Total position value"
        risk = [f"{label} · {exposure} {currency}"]
    elif snapshot["observed_gross_exposure"] is not None:
        label = "已估值持仓" if zh else "Valued positions"
        value = snapshot["observed_gross_exposure"]
        risk = [f"{label} · {value} {currency}",
                "账户估值不完整，暂无法计算总敞口。" if zh else "Valuation is incomplete. Total exposure is unavailable."]
    else:
        risk = ["暂无可用报价，无法计算敞口。" if zh else "Exposure is unavailable because quotes are missing."]

    largest = snapshot["largest_position"]
    if largest is not None:
        share = f"{Decimal(largest['concentration_pct']):.2f}%"
        symbol = largest["symbol"]
        risk.append(f"最大单项持仓 · {symbol} 占账户总资产 {share}" if zh
                    else f"Largest position · {symbol} is {share} of total account assets")

    balances = ", ".join(f"{row['available']} {row['currency']}" for row in snapshot["balances"])
    sections = ["\n".join([holdings_title, *positions]), "\n".join([exposure_title, *risk])]
    if balances:
        label = "可用余额" if zh else "Available balance"
        sections.append(f"{label} · {balances}")
    return "\n\n".join(sections)
