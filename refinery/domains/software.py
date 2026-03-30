"""Software domain — systems design, infrastructure, DevOps, SRE."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior software architect evaluating papers on systems design, distributed computing, and infrastructure. Include specific latency, throughput, and reliability metrics." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this software engineering research for production systems.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: latency p99 ms, throughput RPS, error rates %, resource utilization metrics. "
        "ANALYZE: because architecture X reduces coupling by Y%, therefore deployment frequency improves. "
        "EVALUATE: if traffic spikes 10x, then system degrades unless auto-scaling is configured with Z thresholds. "
        "RECOMMEND specific implementation with infrastructure specs and SLA targets."
    ),
    (
        "From a platform engineering and reliability perspective:\n" + RJ_TRAJECTORY +
        "\nInclude numbers: uptime %, MTTR minutes, deployment frequency/day, test coverage %. "
        "Explain: because observability gap in X layer, therefore MTTR increases by Y minutes. "
        "Evaluate: if dependency fails, then cascade risk exists unless circuit breaker timeout is set to Z ms. "
        "Recommend specific SRE practices with numerical thresholds."
    ),
]

CONCEPT_TERMS = [
    "api", "deployment", "latency", "throughput", "microservice",
    "container", "kubernetes", "database", "ci/cd", "repository",
    "dependency", "runtime", "scalability", "middleware", "endpoint",
    "refactor", "migration", "architecture", "backend", "frontend",
]

register_domain("software", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
