"""Crypto domain — blockchain, DeFi, smart contracts, consensus."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a blockchain protocol analyst evaluating research on consensus mechanisms, smart contracts, and decentralized systems. Be technically precise about TPS, finality, gas costs, and security guarantees." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this blockchain/crypto research for protocol design.\n" + RJ_TRAJECTORY +
        "\nCALCULATE: TPS throughput, finality time ms, gas costs $, validator requirements. "
        "ANALYZE: because consensus mechanism X reduces latency by Y%, therefore scalability improves. "
        "EVALUATE: if network load exceeds Z TPS, then congestion occurs unless sharding is implemented. "
        "RECOMMEND specific protocol changes with expected performance metrics."
    ),
    (
        "From a DeFi and smart contract security perspective:\n" + RJ_TRAJECTORY +
        "\nInclude numbers: TVL $, exploit losses $, audit coverage %, gas optimization savings. "
        "Explain: because reentrancy guard X prevents Y attack vector, therefore TVL security improves. "
        "Evaluate: if liquidity drops below $Z, then oracle manipulation risk increases unless circuit breakers activate. "
        "Recommend security measures with specific implementation parameters."
    ),
]

CONCEPT_TERMS = [
    "blockchain", "token", "smart contract", "consensus", "hash",
    "wallet", "defi", "liquidity", "staking", "validator",
    "protocol", "transaction", "decentralized", "ledger",
]

register_domain("crypto", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
