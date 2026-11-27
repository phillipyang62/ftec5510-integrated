"""Match the classroom catalog against verified profile scores."""

import re
from copy import deepcopy

from .product_catalog import LEVEL_THRESHOLDS, PRODUCTS


POLICY = "classroom-v2"
DIMENSIONS = {
    "FC": ("财务承载力", "Financial capacity"),
    "RA": ("风险意愿", "Risk willingness"),
    "KE": ("认知与经验", "Knowledge and experience"),
    "BD": ("行为纪律", "Behavioral discipline"),
    "OC": ("目标与约束", "Objectives and constraints"),
}
HOLDING_TIPS = {
    "FC": ("先留出日常开支和应急资金，只用即使亏损也能承受的资金参与。",
           "Keep living expenses and emergency funds separate. Limit exposure to an amount you could afford to lose."),
    "RA": ("先想想这类资产出现明显回撤时你能否接受，再选择和你风险意愿相符的波动范围。",
           "Consider how you would react to a large drawdown, then look for volatility you are comfortable with."),
    "KE": ("先弄清产品靠什么运转、主要风险是什么、什么情况下会难以退出，再考虑新增投入。",
           "Learn how the product works, what could go wrong and how easily you could exit before adding exposure."),
    "BD": ("下次先写好参与条件和暂停规则。遇到突然上涨或下跌时，先按规则检查一遍再决定。",
           "Write down your entry and pause rules first. Check those rules before reacting to a sudden price move."),
    "OC": ("把用钱和还款的时间列出来，再核对产品赎回、锁仓和退出条件。",
           "Check when you need the money or must repay debt against the product's redemption, lockup and exit terms."),
}
_MATCH_TERMS = (
    "适合", "匹配", "推荐", "买什么", "能买吗", "该买吗", "荐币", "投资建议", "配置建议",
    "稳定币", "资产类别", "哪些币", "suitable", "recommend", "what should i buy", "stablecoin",
    "asset matching", "investment advice", "investment recommendation", "which assets", "which coins",
    "what can i buy", "suit me",
)
_EXPLANATION_TERMS = (
    "介绍", "了解", "学习", "是什么", "风险", "解释", "讲解", "怎么样", "怎么看", "对比", "比较", "买入", "购买",
    "learn", "explain", "what is", "risk", "buy", "compare",
)
_GROUP_TERMS = {
    "stablecoin": ("稳定币", "stablecoin"),
    "established": ("主流币", "主流资产", "主流波动资产", "established", "major assets"),
    "altcoin": ("山寨币", "替代币", "公链代币", "协议代币", "altcoin", "protocol token"),
    "speculative": ("投机", "迷因", "模因", "meme", "speculative"),
}
_ASSET_ALIASES = {
    "BTC": ("比特币",), "ETH": ("以太坊", "以太币"), "XRP": ("瑞波币",),
    "ADA": ("艾达币", "卡尔达诺"), "AVAX": ("雪崩",), "DOGE": ("狗狗币",), "PEPE": ("佩佩币",),
}


def catalog_products():
    return [{key: deepcopy(value) for key, value in product.items() if key != "demo_price"}
            for product in PRODUCTS.values()]


def requested_products(message):
    lower = message.casefold()
    groups = {group for group, terms in _GROUP_TERMS.items() if any(term in lower for term in terms)}
    selected = []
    for symbol, product in PRODUCTS.items():
        base = symbol.split("/")[0].casefold()
        if (re.search(r"(?<![a-z0-9_])" + re.escape(base) + r"(?![a-z0-9_])", lower)
                or re.search(r"(?<![a-z0-9_])" + re.escape(product["name"].casefold()) + r"(?![a-z0-9_])", lower)
                or any(alias in lower for alias in _ASSET_ALIASES.get(base.upper(), ()))
                or product["group"] in groups):
            selected.append(symbol)
    return selected


def asset_guidance_requested(message):
    lower = message.casefold()
    return (any(term in lower for term in _MATCH_TERMS)
            or bool(requested_products(message)) and any(term in lower for term in _EXPLANATION_TERMS))


def _compare_thresholds(assessment, product):
    above_cap = int(product["grade"][1]) > int(assessment.product_cap[1])
    unmet = [code for code in DIMENSIONS if assessment.dimensions[code] < product["requirements"][code]]
    return above_cap, unmet


def holdings_comparison(positions, assessment):
    comparisons = []
    for position in positions:
        product = PRODUCTS.get(position["symbol"])
        above_cap, unmet = _compare_thresholds(assessment, product) if assessment and product else (None, [])
        comparisons.append({
            **position,
            "product_grade": product["grade"] if product else None,
            "asset_group": product["group"] if product else None,
            "above_cap": above_cap,
            "unmet_dimensions": [
                {"code": code, "score": assessment.dimensions[code], "minimum": product["requirements"][code]}
                for code in unmet
            ],
        })
    return comparisons


def holdings_text(account, comparisons, assessment, message, *, include_tips, advice=False):
    zh = any("\u4e00" <= char <= "\u9fff" for char in message)
    if account["state"] != "ok":
        return ["当前无法核实持仓。" if zh else "I couldn't verify your current holdings."]
    if not comparisons:
        return ["目前没有可供分析的持仓。" if zh else "There are no current holdings to review."]

    positions = ("、" if zh else ", ").join(f"{row['symbol']} {row['quantity']}" for row in comparisons)
    partial = account.get("truncated", False)
    if zh:
        lines = [f"{'部分持仓' if partial else '当前持仓'} · {positions}"]
    else:
        lines = [f"{'Partial holdings' if partial else 'Current holdings'} · {positions}"]
    if assessment is None:
        lines.append("这个账户还没有风险测评记录，暂时无法判断持仓与你的风险是否匹配。" if zh
                     else "This account has no risk assessment to compare with your holdings.")
        return lines

    lang = 0 if zh else 1
    risk_level, cap = assessment.risk_level, assessment.product_cap
    lines.append(f"你的风险等级是 {risk_level}，产品上限是 {cap}。" if zh
                 else f"Your risk level is {risk_level}, with a product ceiling of {cap}.")
    if advice:
        grades = [f"{row['symbol']} ({row['product_grade']})" for row in comparisons if row["product_grade"]]
        if grades:
            lines.append(("产品档位 · " if zh else "Product risk tiers · ") + " · ".join(grades))
        return lines
    notes, shortfalls = [], set()
    for row in comparisons:
        grade = row["product_grade"]
        if grade is None:
            notes.append(f"{row['symbol']} · {'目录暂无评级' if zh else 'No rating in the catalog'}")
            continue
        reasons = []
        if row["above_cap"]:
            reasons.append(f"高于你的 {cap} 上限" if zh else f"above your {cap} ceiling")
        for gap in row["unmet_dimensions"]:
            code, score, minimum = gap["code"], gap["score"], gap["minimum"]
            shortfalls.add(code)
            label = DIMENSIONS[code][lang]
            reasons.append(f"{label} {score:g} 分，门槛 {minimum:g} 分" if zh
                           else f"{label} {score:g}, minimum {minimum:g}")
        note = ("，" if zh else ", ").join(reasons) if reasons else (
            "达到档位和五维门槛" if zh else "meets the grade and score thresholds"
        )
        notes.append(f"{row['symbol']}（{grade}）· {note}")
    lines.append("\n".join(notes))
    if include_tips and shortfalls:
        lines.append(" ".join(HOLDING_TIPS[code][lang] for code in DIMENSIONS if code in shortfalls))
    elif include_tips and any(row["above_cap"] for row in comparisons):
        lines.append("下次先按产品上限筛一轮，再看你能否接受回撤和退出条件。" if zh
                     else "For future decisions, start with your product ceiling, then check drawdown and exit risks.")
    elif include_tips and all(row["product_grade"] is not None for row in comparisons):
        focus = min(DIMENSIONS, key=assessment.dimensions.__getitem__)
        lines.append(HOLDING_TIPS[focus][lang])
    elif include_tips:
        lines.append("下次考虑新币种时，可以先弄清它的主要风险、退出条件和自己能承受的损失。" if zh
                     else "Before considering another asset, check its main risks, exit terms and how much loss you could absorb.")
    return lines


def suitability_for(profile):
    assessment = profile.assessment if profile else None
    route = profile.route if profile else "clarify"
    blocked = None
    if assessment is None:
        blocked = ("先完成五维测评，再查看课堂模拟候选。", "Complete the five-dimensional assessment to view classroom candidates.")
    elif assessment.prohibitions:
        blocked = ("测评存在禁止项，请先复核限制。", "Review the restrictions recorded in your assessment.")
    elif "LEVERAGE_USE" in assessment.flags:
        blocked = ("测评标记了杠杆使用，请先复核借款与偿还需求。", "Review the borrowing and repayment needs flagged by your assessment.")
    elif route == "clarify":
        blocked = ("测评需要复核，先确认资金需求与可接受亏损。", "Review your cash needs and acceptable losses before comparing candidates.")
    elif route == "education":
        blocked = ("当前先学习基础概念和资产风险。", "Start with the basic concepts and asset risks for your current knowledge level.")

    products = []
    for product in catalog_products():
        above_cap, unmet = _compare_thresholds(assessment, product) if assessment else (False, [])
        if blocked or above_cap or unmet:
            status = "learn" if product["group"] == "stablecoin" else "caution"
            zh_parts, en_parts = [], []
            if blocked:
                zh_parts.append(blocked[0].rstrip("。"))
                en_parts.append(blocked[1].rstrip("."))
            if above_cap:
                zh_parts.append(f"产品等级 {product['grade']} 超出测评上限 {assessment.product_cap}")
                en_parts.append(f"Product grade {product['grade']} exceeds your {assessment.product_cap} ceiling")
            for code in unmet:
                score, minimum = assessment.dimensions[code], product["requirements"][code]
                level = product["requirement_levels"][code]
                dimension_zh, dimension_en = DIMENSIONS[code]
                zh_parts.append(f"{dimension_zh}（{code}）得分 {score:g}，第 {level} 档模拟练习门槛 {minimum}")
                en_parts.append(f"{dimension_en} ({code}) score {score:g}, tier {level} simulation threshold {minimum}")
            if product["group"] == "stablecoin":
                zh_parts.append("可继续阅读稳定币通识内容，学习发行方、赎回和脱锚风险。个性化模拟练习需满足测评路径、产品上限与维度门槛")
                en_parts.append("General stablecoin lessons remain available for issuer, redemption and depeg risks. Personalized simulation practice requires the assessment route, product ceiling and score thresholds to qualify")
            zh, en = "。".join(zh_parts) + "。", ". ".join(en_parts) + "."
        else:
            status = "suitable"
            scores = "、".join(f"{code} {assessment.dimensions[code]:g}≥{product['requirements'][code]}" for code in DIMENSIONS)
            zh = f"可作为个性化课堂模拟候选。产品等级 {product['grade']} 在测评上限 {assessment.product_cap} 内，维度门槛均通过（{scores}）。"
            en = f"Eligible as a personalized classroom simulation candidate. Product grade {product['grade']} is within your {assessment.product_cap} ceiling, and the score thresholds are met ({scores})."
        products.append({**product, "status": status, "reasons": {"zh": zh, "en": en}, "unmet": unmet})

    return {
        "policy": POLICY,
        "level_thresholds": dict(LEVEL_THRESHOLDS),
        "route": route,
        "risk_level": assessment.risk_level if assessment else None,
        "product_cap": assessment.product_cap if assessment else None,
        "products": products,
        "recommendations": [row["symbol"] for row in products if row["status"] == "suitable"],
        "learning": [row["symbol"] for row in products if row["status"] == "learn"],
    }


def guidance_text(guidance, message):
    language = "zh" if any("\u4e00" <= char <= "\u9fff" for char in message) else "en"
    selected = requested_products(message) or guidance["recommendations"][:3] or guidance["learning"][:2]
    heading = "课堂资产学习与模拟匹配" if language == "zh" else "Classroom asset learning and simulated matching"
    lines = [heading]
    for product in guidance["products"]:
        if product["symbol"] in selected:
            lines.append(f"{product['symbol']} · {product['grade']}\n{product['reasons'][language]}\n{product['basis'][language]}")
    if not selected:
        lines.append("请先完成或复核五维测评。" if language == "zh" else "Complete or review your five-dimensional assessment first.")
    return "\n\n".join(lines)
