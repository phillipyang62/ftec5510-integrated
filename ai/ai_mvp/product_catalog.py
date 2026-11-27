"""Versioned classroom asset examples, reviewed on 2026-11-27.

Grades and five-dimensional minimum scores are teaching policy authored for this
prototype. They are neither measured volatility ratings nor investment advice.
Sources support the asset mechanisms and learning topics. The synthetic demo
prices are fixed offline fixtures, independent of current market quotations.
Requirement levels 0 through 4 map to minimum questionnaire scores. Level 0
adds no minimum score for that dimension. Numeric requirements are derived
once from the level matrix so matching and order policies use the same scale.
"""

import json


LEVEL_THRESHOLDS = {0: 0, 1: 30, 2: 45, 3: 60, 4: 85}


PRODUCTS = {
    "BTC/USDT": {
        "symbol": "BTC/USDT",
        "name": "Bitcoin",
        "group": "established",
        "grade": "R4",
        "requirement_levels": {"FC": 3, "RA": 2, "KE": 3, "BD": 3, "OC": 3},
        "tags": {
            "zh": ["原生资产", "工作量证明", "价格波动", "资金损失承受力"],
            "en": ["Native asset", "Proof of work", "Price fluctuations", "Loss capacity"],
        },
        "basis": {
            "zh": "用 BTC 学习价格回撤和交易确认，课堂规则综合检查财务承载力、认知经验、行为纪律与目标约束。",
            "en": "Study BTC drawdowns and transaction confirmations, with classroom checks on capacity, knowledge, discipline and objectives.",
        },
        "sources": ["https://bitcoin.org/en/you-need-to-know"],
        "demo_price": "68000",
    },
    "ETH/USDT": {
        "symbol": "ETH/USDT",
        "name": "Ethereum",
        "group": "established",
        "grade": "R3",
        "requirement_levels": {"FC": 2, "RA": 1, "KE": 2, "BD": 3, "OC": 2},
        "tags": {
            "zh": ["原生资产", "智能合约生态", "网络费用", "价格回撤"],
            "en": ["Native asset", "Smart contract ecosystem", "Network fees", "Price drawdowns"],
        },
        "basis": {
            "zh": "用 ETH 现货学习网络费用和回撤，课堂规则侧重行为纪律，同时检查财务承载力、认知经验与目标约束。",
            "en": "Study network fees and drawdowns with spot ETH. Classroom rules emphasize discipline while checking capacity, knowledge and objectives.",
        },
        "sources": ["https://ethereum.org/what-is-ether/"],
        "demo_price": "3500",
    },
    "SOL/USDT": {
        "symbol": "SOL/USDT",
        "name": "Solana",
        "group": "altcoin",
        "grade": "R5",
        "requirement_levels": {"FC": 2, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["权益证明网络", "通胀发行", "生态依赖", "风险纪律"],
            "en": ["Proof of stake network", "Inflationary issuance", "Ecosystem dependence", "Risk discipline"],
        },
        "basis": {
            "zh": "通过 SOL 理解通胀发行和网络生态，课堂规则对风险意愿、认知经验、纪律与目标约束设置较高要求。",
            "en": "Explore SOL issuance and ecosystem factors, with higher classroom requirements for willingness, knowledge, discipline and objectives.",
        },
        "sources": ["https://solana.com/staking"],
        "demo_price": "182",
    },
    "USDC/USDT": {
        "symbol": "USDC/USDT",
        "name": "USD Coin",
        "group": "stablecoin",
        "grade": "R1",
        "requirement_levels": {"FC": 0, "RA": 0, "KE": 0, "BD": 0, "OC": 2},
        "tags": {
            "zh": ["美元锚定目标", "发行方与赎回条件", "脱锚风险", "目标约束检查"],
            "en": ["USD peg target", "Issuer and redemption terms", "Depeg risk", "Objectives and constraints check"],
        },
        "basis": {
            "zh": "用 USDC 学习赎回与脱锚风险，课堂门槛侧重资金目标和约束，提醒核对 USDT 报价与美元价值。",
            "en": "Study USDC redemption and depeg risks. Classroom eligibility focuses on objectives and constraints, including USDT quotes versus USD value.",
        },
        "sources": [
            "https://www.circle.com/legal/usdc-terms",
            "https://www.circle.com/legal/usdc-risk-factors",
        ],
        "demo_price": "1",
    },
    "RLUSD/USDT": {
        "symbol": "RLUSD/USDT",
        "name": "Ripple USD",
        "group": "stablecoin",
        "grade": "R2",
        "requirement_levels": {"FC": 0, "RA": 0, "KE": 0, "BD": 0, "OC": 3},
        "tags": {
            "zh": ["美元锚定目标", "储备与赎回审查", "冻结与脱锚风险", "较高目标约束门槛"],
            "en": ["USD peg target", "Reserve and redemption review", "Freezing and depeg risks", "Higher objectives threshold"],
        },
        "basis": {
            "zh": "通过 RLUSD 练习审查储备、赎回和冻结条款，课堂规则提高目标与约束门槛，关注资金用途和退出条件。",
            "en": "Review RLUSD reserves, redemption and freezing provisions. Classroom rules apply a higher objectives threshold for intended use and exit conditions.",
        },
        "sources": ["https://ripple.com/legal/stablecoin/"],
        "demo_price": "1",
    },
    "XRP/USDT": {
        "symbol": "XRP/USDT",
        "name": "XRP",
        "group": "altcoin",
        "grade": "R4",
        "requirement_levels": {"FC": 2, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["账本原生资产", "账户储备", "交易费用", "使用约束"],
            "en": ["Ledger native asset", "Account reserves", "Transaction fees", "Usage constraints"],
        },
        "basis": {
            "zh": "用 XRP 的账户储备与费用机制说明余额可用性，课堂规则对风险意愿、认知经验、纪律与目标约束设置较高要求。",
            "en": "Study spendable XRP balances through reserves and fees, with higher classroom requirements for willingness, knowledge, discipline and objectives.",
        },
        "sources": [
            "https://xrpl.org/docs/concepts/accounts/reserves",
            "https://xrpl.org/docs/concepts/transactions/transaction-cost",
        ],
        "demo_price": "2.2",
    },
    "ADA/USDT": {
        "symbol": "ADA/USDT",
        "name": "Cardano",
        "group": "altcoin",
        "grade": "R4",
        "requirement_levels": {"FC": 2, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["网络原生资产", "社区治理", "供应量上限", "生态研究"],
            "en": ["Network native asset", "Community governance", "Supply cap", "Ecosystem research"],
        },
        "basis": {
            "zh": "通过 ADA 学习供应规则和社区治理，课堂规则对风险意愿、认知经验、纪律与目标约束设置较高要求。",
            "en": "Study ADA supply rules and governance, with higher classroom requirements for willingness, knowledge, discipline and objectives.",
        },
        "sources": ["https://cardano.org/constitution/"],
        "demo_price": "0.6",
    },
    "LINK/USDT": {
        "symbol": "LINK/USDT",
        "name": "Chainlink",
        "group": "altcoin",
        "grade": "R4",
        "requirement_levels": {"FC": 2, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["预言机生态", "服务代币机制", "协议知识", "独立质押评估"],
            "en": ["Oracle ecosystem", "Service token mechanics", "Protocol knowledge", "Separate staking review"],
        },
        "basis": {
            "zh": "用 LINK 理解预言机与代币用途，课堂规则对风险意愿、认知经验、纪律与目标约束设置较高要求，质押另行评估。",
            "en": "Study LINK oracle services and utility with higher classroom requirements for willingness, knowledge, discipline and objectives. Assess staking separately.",
        },
        "sources": [
            "https://docs.chain.link/docs/getting-started",
            "https://chain.link/economics/staking",
        ],
        "demo_price": "15",
    },
    "AVAX/USDT": {
        "symbol": "AVAX/USDT",
        "name": "Avalanche",
        "group": "altcoin",
        "grade": "R5",
        "requirement_levels": {"FC": 2, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["多链生态", "费用销毁", "奖励发行", "供应机制"],
            "en": ["Multi-chain ecosystem", "Fee burning", "Reward issuance", "Supply mechanics"],
        },
        "basis": {
            "zh": "通过 AVAX 比较费用销毁和奖励发行，课堂规则对风险意愿、认知经验、纪律与目标约束设置较高要求。",
            "en": "Compare AVAX fee burning and reward issuance, with higher classroom requirements for willingness, knowledge, discipline and objectives.",
        },
        "sources": ["https://support.avax.network/en/articles/6912428-tokenomics-faq"],
        "demo_price": "25",
    },
    "SUI/USDT": {
        "symbol": "SUI/USDT",
        "name": "Sui",
        "group": "altcoin",
        "grade": "R5",
        "requirement_levels": {"FC": 3, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["较新公链生态", "分期代币释放", "流通供应变化", "信息核查"],
            "en": ["Newer chain ecosystem", "Scheduled token releases", "Circulating supply changes", "Evidence review"],
        },
        "basis": {
            "zh": "用 SUI 的分期代币释放学习供应变化，课堂规则提高财务承载力要求，并严格检查风险意愿、认知经验、纪律与目标约束。",
            "en": "Study SUI supply releases, with an elevated capacity requirement and strict checks on willingness, knowledge, discipline and objectives.",
        },
        "sources": ["https://www.sui.io/token-schedule"],
        "demo_price": "3",
    },
    "DOGE/USDT": {
        "symbol": "DOGE/USDT",
        "name": "Dogecoin",
        "group": "speculative",
        "grade": "R5",
        "requirement_levels": {"FC": 4, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["模因与支付资产", "持续发行", "投机行为讨论", "行为纪律"],
            "en": ["Meme and payment asset", "Ongoing issuance", "Speculative behavior discussion", "Behavioral discipline"],
        },
        "basis": {
            "zh": "通过 DOGE 讨论模因资产与持续发行，课堂规则在五个维度均采用最高档门槛，重点讨论冲动交易。",
            "en": "Discuss DOGE meme activity and ongoing issuance, applying the highest classroom threshold in all five dimensions and examining impulsive trading.",
        },
        "sources": [
            "https://dogecoin.com/dogepedia/faq/dogecoin-inflation/",
            "https://www.binance.com/en/research/projects/dogecoin",
        ],
        "demo_price": "0.15",
    },
    "PEPE/USDT": {
        "symbol": "PEPE/USDT",
        "name": "Pepe",
        "group": "speculative",
        "grade": "R5",
        "requirement_levels": {"FC": 4, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["模因代币", "匿名团队", "用途证据有限", "高纪律门槛"],
            "en": ["Meme token", "Anonymous team", "Limited utility evidence", "High discipline requirement"],
        },
        "basis": {
            "zh": "用 PEPE 的模因定位与匿名团队练习审查用途证据，课堂规则在五个维度均采用最高档门槛。",
            "en": "Examine PEPE utility evidence through its meme focus and anonymous team, applying the highest classroom threshold in all five dimensions.",
        },
        "sources": ["https://www.binance.com/en/research/projects/pepe"],
        "demo_price": "0.000012",
    },
    "MON/USDT": {
        "symbol": "MON/USDT",
        "name": "Monad",
        "group": "altcoin",
        "grade": "R5",
        "requirement_levels": {"FC": 3, "RA": 4, "KE": 4, "BD": 4, "OC": 4},
        "tags": {
            "zh": ["较新公链生态", "EVM 兼容", "网络机制研究", "交易场所核查"],
            "en": ["Newer chain ecosystem", "EVM compatible", "Network mechanism research", "Venue availability review"],
        },
        "basis": {
            "zh": "通过 MON 学习 EVM 兼容公链和交易场所核查，课堂规则提高财务承载力要求，并严格检查其余四个维度。",
            "en": "Study MON network compatibility and venue availability, with an elevated capacity requirement and strict checks across the other four dimensions.",
        },
        "sources": [
            "https://docs.monad.xyz/developer-essentials/network-information",
            "https://www.okx.com/en-gb/help/okx-to-list-mon-monad-for-spot-trading",
        ],
        "demo_price": "0.03",
    },
}


for _product in PRODUCTS.values():
    _product["requirements"] = {
        dimension: LEVEL_THRESHOLDS[level]
        for dimension, level in _product["requirement_levels"].items()
    }
del _product


def order_policies():
    return {
        symbol: {"grade": int(product["grade"][1]), "requirements": product["requirements"].copy()}
        for symbol, product in PRODUCTS.items()
    }


if __name__ == "__main__":
    print(json.dumps(order_policies(), indent=2))
