"""Finance domain — equity research, M&A, valuation, capital markets."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior equity research analyst evaluating papers on corporate finance, valuation, and capital markets. Include specific multiples, margins, growth rates, and DCF assumptions." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this financial research for investment strategy.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: valuation multiples (P/E, EV/EBITDA), margin %, revenue growth rates, DCF assumptions. "
        "ANALYZE: because earnings growth of X% exceeds sector average by Y, therefore valuation premium is justified. "
        "EVALUATE: if multiple compression occurs from Z to W, then downside is X% unless earnings accelerate. "
        "RECOMMEND specific portfolio actions with price targets and position sizing."
    ),
    (
        "From a corporate finance and M&A perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific numbers: deal values $, synergy estimates %, IRR projections, leverage ratios. "
        "Explain: because accretion/dilution analysis shows X, therefore EPS impact is Y%. "
        "Evaluate: if interest rates rise Z bps, then deal financing costs increase unless structure is modified. "
        "Recommend deal parameters with specific financial covenants."
    ),
]

CONCEPT_TERMS = [
    "revenue", "earnings", "eps", "margin", "guidance", "valuation",
    "dividend", "equity", "debt", "balance sheet", "cash flow",
    "income statement", "quarterly", "annual", "profit", "loss",
    "shareholder", "acquisition", "merger", "ipo", "underwriter",
]

register_domain("finance", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
