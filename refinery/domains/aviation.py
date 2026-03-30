"""Aviation domain — flight ops, maintenance, safety, ATC, weather."""

from domains.base import RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior aviation safety analyst and ATP-rated pilot with 20,000+ hours. You translate aerospace research into operationally precise guidance for pilots, controllers, mechanics, and dispatchers. Reference FAA/ICAO/EASA regulations by number." + RJ_SYSTEM_SUFFIX,
    "You are an aviation maintenance engineer (A&P/IA) who evaluates aerospace research for airworthiness, inspection procedures, and maintenance planning. Reference ADs, service bulletins, and manufacturer guidance. Include specific tolerances and intervals." + RJ_SYSTEM_SUFFIX,
    "You are a flight safety investigator who analyzes incidents using TEM methodology. You identify error chains, contributing factors, and systemic defenses. Reference specific regulations, procedures, and operational standards." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this aviation research using the full 5-step trajectory:\n"
        "1. IDENTIFY the core operational issue this research addresses\n"
        "2. CALCULATE the key metrics — include specific numbers, percentages, performance figures, or safety statistics from the paper\n"
        "3. ANALYZE why these findings matter — use causal reasoning (because, therefore, consequently) to connect research to operations\n"
        "4. EVALUATE the operational risks — what happens IF these findings are ignored? What changes UNLESS action is taken?\n"
        "5. RECOMMEND specific procedural changes, regulatory actions, or training requirements with clear rationale\n\n"
        "Include at least 3 specific numbers or percentages. Reference applicable FARs, ADs, or ICAO standards by number. "
        "Use domain terminology: aircraft, airspace, altitude, approach, clearance, maintenance, knots."
    ),
    (
        "From an aircraft maintenance engineering perspective, apply the 5-step trajectory:\n"
        "1. IDENTIFY the airworthiness concern or maintenance implication\n"
        "2. CALCULATE relevant inspection intervals, failure rates, MTBF, or cost impacts — show the math\n"
        "3. ANALYZE the causal chain — explain WHY this matters using 'because' and 'therefore' to link cause and effect\n"
        "4. EVALUATE compliance risk — IF this research is validated, THEN what MEL/CDL or AD changes follow? UNLESS mitigated, what failure modes emerge?\n"
        "5. RECOMMEND specific maintenance procedures, inspection criteria, or regulatory submissions\n\n"
        "Include specific numerical thresholds, tolerances, or performance limits. "
        "Reference FAA 14 CFR Part 43/145, applicable ADs, or manufacturer service bulletins."
    ),
    (
        "Analyze this research from an aviation safety investigation perspective:\n"
        "1. IDENTIFY the systemic risk, human factor, or failure mode this paper reveals\n"
        "2. CALCULATE the risk quantification — incident rates, probability figures, exposure hours, or statistical significance from the data\n"
        "3. ANALYZE the accident/incident chain — explain each causal link using 'because', 'therefore', 'consequently'\n"
        "4. EVALUATE defenses — IF the Swiss cheese model applies, THEN which barriers failed? UNLESS new defenses are added, what is the residual risk?\n"
        "5. RECOMMEND safety actions — specific SMS changes, training requirements, or regulatory proposals\n\n"
        "Reference specific FAA/ICAO safety frameworks, advisory circulars, or accident data by number. "
        "Include altitude, airspace, approach, and clearance context where relevant."
    ),
]

CONCEPT_TERMS = [
    "aircraft", "runway", "faa", "maintenance", "airspace",
    "atc", "metar", "ifr", "vfr", "approach", "clearance",
    "turbine", "flap", "altitude", "knots",
]

register_domain("aviation", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
