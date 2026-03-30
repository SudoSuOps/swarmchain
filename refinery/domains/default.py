"""Default domain — fallback for unclassified content."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior analyst who translates academic research into actionable intelligence. Include specific metrics, data points, and practical implications." + RJ_SYSTEM_SUFFIX,
    "You are a quantitative research analyst who bridges academic papers and real-world decisions. Focus on methodology quality, data significance, and actionable takeaways." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this research for practical applications.\n" + RJ_TRAJECTORY +
        "\nInclude at least 3 specific numbers, percentages, or calculated metrics. "
        "Use causal reasoning: 'because X, therefore Y follows'. "
        "Evaluate risks: 'if Z happens, then W results unless mitigated'. "
        "Recommend specific actions with clear rationale and supporting data."
    ),
    (
        "Translate this research into an actionable intelligence briefing.\n" + RJ_TRAJECTORY +
        "\nCALCULATE the key quantitative findings — show percentages, rates, and deltas. "
        "ANALYZE: because the data shows X, therefore the implication is Y. "
        "EVALUATE: if these findings hold, then Z changes unless assumptions are violated. "
        "RECOMMEND specific next steps with expected outcomes."
    ),
]

register_domain("default", SYSTEM_PROMPTS, INSTRUCTIONS, [])
