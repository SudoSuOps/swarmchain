"""AI domain — ML research, model architectures, training, inference."""

from domains.base import RJ_TRAJECTORY, RJ_SYSTEM_SUFFIX, register_domain

SYSTEM_PROMPTS = [
    "You are a senior ML engineer evaluating AI research for production deployment. Include specific performance metrics — accuracy, latency, throughput, parameter counts, and hardware requirements." + RJ_SYSTEM_SUFFIX,
]

INSTRUCTIONS = [
    (
        "Analyze this AI/ML research for production deployment.\n" + RJ_TRAJECTORY +
        "\nCALCULATE performance deltas — accuracy %, latency ms, throughput tok/s, parameter counts. "
        "ANALYZE why this approach works: because architecture X reduces Y, therefore inference cost drops by Z%. "
        "EVALUATE: if deployed at scale, then what GPU/memory requirements? Unless quantized, what is the cost? "
        "RECOMMEND specific integration steps with hardware specs."
    ),
    (
        "Evaluate this paper's training methodology.\n" + RJ_TRAJECTORY +
        "\nInclude specific numbers: learning rates, batch sizes, dataset sizes, FLOPs. "
        "Explain causal chains: because the loss function does X, therefore convergence improves by Y%. "
        "If applied to fine-tuning domain models, then what data volume is needed? Unless regularized, what overfitting risk? "
        "Recommend specific training configurations."
    ),
    (
        "Assess this research for model efficiency and optimization.\n" + RJ_TRAJECTORY +
        "\nCALCULATE compression ratios, speedups, memory savings — show percentages. "
        "ANALYZE: because quantization reduces precision from FP16 to INT8, therefore memory drops by X%. "
        "EVALUATE: if batch size doubles, then throughput increases unless memory-bound. "
        "RECOMMEND specific optimization pipeline with expected performance gains."
    ),
]

CONCEPT_TERMS = [
    "model", "training", "inference", "benchmark", "dataset",
    "transformer", "attention", "embedding", "parameter", "fine-tune",
    "accuracy", "loss", "gradient", "architecture", "encoder",
    "decoder", "token", "latent", "representation", "evaluation",
    "baseline", "ablation", "performance", "framework", "pipeline",
]

register_domain("ai", SYSTEM_PROMPTS, INSTRUCTIONS, CONCEPT_TERMS)
