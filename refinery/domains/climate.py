"""Climate domain — emissions, adaptation, ESG, sustainability."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a climate risk analyst evaluating research on emissions, adaptation strategies, and environmental policy. Reference IPCC frameworks and Paris Agreement targets. Include specific temperature, emission, and cost figures." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this climate research for risk assessment and policy.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: temperature anomalies °C, emission rates GtCO2/yr, sea level projections mm/yr. "
        "ANALYZE: because GHG concentrations reached X ppm, therefore warming of Y°C is locked in. "
        "EVALUATE: if emissions continue at current rate, then Z scenario by 2050 unless mitigation targets are met. "
        "RECOMMEND specific adaptation and mitigation strategies with quantified targets."
    ),
    (
        "From an ESG and corporate sustainability perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific metrics: carbon intensity kg CO2/unit, Scope 1/2/3 breakdowns, offset prices. "
        "Explain: because this research shows X trend, therefore corporate disclosure requirements shift. "
        "Evaluate: if TCFD frameworks adopt these findings, then reporting burden increases unless automated. "
        "Recommend compliance actions with specific cost estimates."
    ),
]

CONCEPT_TERMS = [
    "temperature", "emission", "carbon", "greenhouse", "warming",
    "sea level", "precipitation", "drought", "permafrost", "ice",
    "deforestation", "ecosystem", "biodiversity", "sustainability",
]

register_domain("climate", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
