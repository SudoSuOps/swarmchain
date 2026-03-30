"""Legal domain — regulatory compliance, case law, governance."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a legal research analyst evaluating papers on regulatory frameworks, case law, and compliance. Reference specific statutes, jurisdictions, and penalty ranges." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this legal research for regulatory compliance impact.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: compliance cost estimates $, penalty ranges, filing deadlines, statute of limitations periods. "
        "ANALYZE: because ruling X establishes precedent Y, therefore liability exposure increases for Z category. "
        "EVALUATE: if enforcement intensifies, then compliance costs rise by X% unless proactive measures are taken. "
        "RECOMMEND specific compliance program changes with implementation timelines."
    ),
    (
        "From a corporate governance and risk management perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific figures: damages awarded $, settlement ranges, regulatory fine brackets. "
        "Explain: because this legal framework shifts from X to Y standard, therefore burden of proof changes. "
        "Evaluate: if class action thresholds are met, then exposure multiplies unless early resolution pursued. "
        "Recommend risk mitigation with specific contract or policy provisions."
    ),
]

CONCEPT_TERMS = [
    "statute", "regulation", "compliance", "court", "filing",
    "jurisdiction", "liability", "precedent", "enforcement",
    "legislation", "amendment", "ruling", "arbitration",
]

register_domain("legal", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
