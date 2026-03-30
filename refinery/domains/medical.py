"""Medical domain — pharma, clinical research, drug development."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a clinical research analyst evaluating pharmaceutical and medical papers. Include specific clinical data — efficacy rates, p-values, dosage ranges, trial phases, and regulatory pathways." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this pharmaceutical/medical research for clinical impact.\n" + RJ_TRAJECTORY +
        "\nCALCULATE clinical metrics: efficacy rates, p-values, NNT, hazard ratios, dosage ranges. "
        "ANALYZE: because the mechanism of action targets X receptor, therefore therapeutic effect Y follows. "
        "EVALUATE: if contraindications include Z, then patient selection must exclude W unless monitoring is enhanced. "
        "RECOMMEND treatment protocol changes with specific evidence levels."
    ),
    (
        "From a healthcare infrastructure perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific numbers: trial enrollment, phase timelines, cost per patient, market size estimates. "
        "Explain causal chains: because Phase III showed X% efficacy, therefore FDA pathway is Y. "
        "Evaluate: if adverse events exceed Z%, then label changes required unless dose is adjusted. "
        "Recommend regulatory strategy with timeline estimates."
    ),
    (
        "Evaluate this research for drug development and clinical practice.\n" + RJ_TRAJECTORY +
        "\nCALCULATE pharmacokinetic parameters: half-life, bioavailability %, clearance rates. "
        "ANALYZE: because drug-drug interaction with X increases plasma levels by Y%, therefore dose adjustment is Z. "
        "EVALUATE: if renal impairment is present, then clearance drops unless compensated. "
        "RECOMMEND specific monitoring protocols with numerical thresholds."
    ),
]

CONCEPT_TERMS = [
    "patient", "diagnosis", "treatment", "dosage", "clinical",
    "contraindication", "adverse", "protocol", "trial", "endpoint",
    "biomarker", "cohort", "efficacy", "pathology", "therapeutic",
]

register_domain("medical", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
