ARENA_CONFIG = {

    # Minimum alignment score to accept consensus and stop debating
    "consensus_threshold": 0.7,

    # Maximum debate rounds before forcing a decision
    "max_rounds": 2,

    # Which agents activate per query mode
    "query_modes": {
        "full_ic":      ["fundamental", "quant", "macro", "risk", "sentiment"],
        "quick_screen": ["fundamental", "risk"],
        "risk_check":   ["risk"],
        "macro_view":   ["macro", "sentiment"],
        "valuation":    ["fundamental", "quant"],
    },

    # When to stop the AI and escalate to a human instead
    "escalation_rules": {
        "unresolved_after_max_rounds": False,   # True = escalate, False = force finalise
        "risk_score_above": 0.95,               # if risk agent confidence > this → escalate
    },

    # How the PM resolves conflicts between agents
    # "majority_vote" | "highest_confidence" | "risk_veto"
    "conflict_resolution": "highest_confidence",

    # LLM model used by the PM for synthesis (used later when real PM is built)
    "pm_model": "claude-sonnet-4-6",
}
