"""Patents domain — IP strategy, prosecution, competitive intelligence."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a patent intelligence analyst evaluating research on innovation landscapes, IP strategy, and prosecution. Reference specific patent classes, citation counts, and prosecution timelines." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this patent research for IP strategy.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: patent family size, citation counts, filing costs $, time-to-grant months, licensing rates %. "
        "ANALYZE: because claim scope X covers Y use cases, therefore freedom-to-operate risk exists for Z competitors. "
        "EVALUATE: if prior art challenge succeeds, then claim narrowing reduces coverage by X% unless continuation filed. "
        "RECOMMEND specific IP portfolio actions with prosecution timeline estimates."
    ),
    (
        "From a competitive intelligence and R&D perspective:\n" + RJ_TRAJECTORY +
        "\nInclude specific figures: patent landscape density, whitespace %, R&D spend $ as % of revenue. "
        "Explain: because innovation velocity in X domain shows Y patents/year trend, therefore first-mover advantage narrows. "
        "Evaluate: if competitor files continuation, then design-around cost is $Z unless alternative approach taken. "
        "Recommend R&D priorities with specific technology targets."
    ),
]

CONCEPT_TERMS = [
    "claim", "prior art", "specification", "embodiment", "apparatus",
    "method", "assignee", "patent office", "filing date", "priority",
    "novelty", "inventive step", "prosecution", "examiner", "grant",
    "infringement", "licensing", "continuation", "provisional",
]

register_domain("patents", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
