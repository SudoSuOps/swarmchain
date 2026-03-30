"""Supply chain domain — logistics, procurement, resilience, trade."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a supply chain intelligence analyst evaluating research on logistics optimization, procurement, and global trade. Include specific lead times, cost metrics, and resilience indicators." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this supply chain research for operations optimization.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: lead times days, inventory turns, fill rates %, cost per unit $, freight rates $/TEU. "
        "ANALYZE: because supplier concentration exceeds X%, therefore disruption risk increases by Y factor. "
        "EVALUATE: if lead times extend by Z days, then stockout probability rises unless safety stock is increased. "
        "RECOMMEND specific procurement and logistics actions with ROI estimates."
    ),
    (
        "From a supply chain resilience perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific metrics: dual-source %, nearshoring cost delta, demand forecast accuracy %. "
        "Explain: because tariff X adds Y% to landed cost, therefore margin erodes unless passed through. "
        "Evaluate: if port congestion exceeds Z days, then air freight triggers at $W/kg unless pre-positioned. "
        "Recommend contingency plans with specific trigger thresholds."
    ),
]

CONCEPT_TERMS = [
    "logistics", "inventory", "procurement", "warehouse", "fulfillment",
    "tariff", "freight", "supplier", "lead time", "demand forecast",
    "distribution", "manufacturing", "customs", "shipping", "sourcing",
    "disruption", "resilience", "just-in-time", "backlog",
]

register_domain("supply_chain", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
