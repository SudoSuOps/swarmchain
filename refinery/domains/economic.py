"""Economic domain — macro, monetary policy, fiscal dynamics."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a macroeconomic research analyst evaluating papers on monetary policy, fiscal dynamics, and market indicators. Include specific data points, rate figures, and forecasting implications." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this economics research for CRE and capital markets impact.\n" + RJ_TRAJECTORY +
        "\nCALCULATE rate impacts: basis point changes, yield spreads, GDP growth percentages. "
        "ANALYZE: because the Fed policy implies X, therefore mortgage rates move by Y bps. "
        "EVALUATE: if inflation exceeds Z%, then cap rates widen unless risk premiums compress. "
        "RECOMMEND portfolio positioning with specific rate scenarios."
    ),
    (
        "From a macro intelligence perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific economic indicators: CPI %, unemployment rate, Treasury yields. "
        "Use causal reasoning: because fiscal deficit reaches $X, therefore credit availability contracts. "
        "Evaluate: if recession probability rises above 40%, then defensive assets outperform unless stimulus intervenes. "
        "Recommend specific timing signals with numerical thresholds."
    ),
]

CONCEPT_TERMS = [
    "gdp", "inflation", "interest rate", "unemployment", "yield",
    "monetary", "fiscal", "deficit", "surplus", "fed", "treasury",
    "cpi", "pce", "employment", "recession", "growth",
]

register_domain("economic", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
