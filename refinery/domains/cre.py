"""CRE domain — commercial real estate underwriting, capital markets, leasing."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior analyst at a CRE intelligence platform. You translate academic research into actionable market intelligence with specific metrics, named markets, and asset-level detail." + RJ_SYSTEM_SUFFIX,
    "You are a quantitative research analyst who bridges academic papers and real-world CRE decisions. You focus on methodology quality, data significance, and practical implications." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this research for CRE investment strategy.\n" + RJ_TRAJECTORY +
        "\nInclude cap rate, NOI, DSCR, or LTV calculations where applicable. "
        "Reference specific asset types, markets, and deal structures. "
        "Explain WHY findings matter using 'because' and 'therefore'. "
        "Address what happens IF assumptions change and UNLESS risks are mitigated."
    ),
    (
        "From an institutional CRE underwriting perspective:\n" + RJ_TRAJECTORY +
        "\nCALCULATE the impact on cap rate spreads, rent growth, or vacancy rates — show percentages. "
        "ANALYZE the causal chain: because this research shows X, therefore Y follows for deal pricing. "
        "EVALUATE: if interest rates shift by 50bps, then how does this change the thesis? "
        "Unless the market corrects, what is the risk exposure?"
    ),
    (
        "Translate this research into a CRE market intelligence briefing.\n" + RJ_TRAJECTORY +
        "\nInclude at least 3 specific numbers ($/SF, cap rates, occupancy %). "
        "Use causal reasoning: 'because vacancy is X%, therefore rent pressure implies Y'. "
        "Evaluate conditional scenarios: 'if debt costs rise, then refinancing risk increases unless...' "
        "Recommend specific portfolio actions with supporting calculations."
    ),
]

CONCEPT_TERMS = [
    "noi", "cap rate", "dscr", "ltv", "rent", "lease", "tenant",
    "occupancy", "vacancy", "underwriting", "proforma", "escrow",
    "due diligence", "appraisal", "zoning", "square feet", "psf",
]

register_domain("cre", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
