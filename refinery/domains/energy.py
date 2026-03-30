"""Energy domain — power generation, grid, renewables, storage."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior energy analyst evaluating research on power generation, grid infrastructure, and energy storage. Include specific cost metrics ($/kWh, $/MW), capacity figures, and deployment timelines." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this energy research for grid and generation impact.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: capacity MW, efficiency %, cost $/kWh, deployment timelines. "
        "ANALYZE: because solar LCOE dropped to $X/MWh, therefore coal displacement accelerates by Y%. "
        "EVALUATE: if storage costs fall below $Z/kWh, then grid parity is achieved unless transmission bottlenecks persist. "
        "RECOMMEND specific infrastructure investments with ROI calculations."
    ),
    (
        "From an energy policy and investment perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific numbers: emission reductions in tonnes CO2, capacity factors %, payback periods. "
        "Use causal reasoning: because battery density improved by X%, therefore EV range increases by Y miles. "
        "Evaluate: if carbon price reaches $Z/tonne, then renewables dominate unless subsidies are removed. "
        "Recommend policy actions with specific targets and deadlines."
    ),
]

CONCEPT_TERMS = [
    "solar", "battery", "renewable", "grid", "power", "electricity",
    "emission", "carbon", "megawatt", "capacity", "generation",
    "turbine", "photovoltaic", "efficiency", "storage", "kwh",
]

register_domain("energy", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
