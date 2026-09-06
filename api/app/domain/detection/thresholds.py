"""All rule thresholds, ML ensemble parameters, and composite-scoring
weights, in one place (blueprint §12.5: "weights are configuration, not
code"). Nothing in rules.py, ml.py, scoring.py, or features/engineering.py
should hardcode a threshold inline — it should live here and be imported,
so a reviewer can audit every number the detection layer acts on from a
single file.
"""

from decimal import Decimal

# Shared between feature engineering (sub_threshold_ratio) and STRUCTURING.
REPORTING_THRESHOLD = Decimal("10000.00")

# --- STRUCTURING (blueprint §12.2) ---
STRUCTURING_MIN_COUNT = 3
STRUCTURING_WINDOW_DAYS = 7
STRUCTURING_LOWER_FRACTION = 0.85  # of REPORTING_THRESHOLD

# --- SMURFING ---
SMURFING_MIN_ORIGINATORS = 5
SMURFING_WINDOW_DAYS = 14

# --- RAPID_MOVEMENT ---
RAPID_MOVEMENT_MIN_FRACTION = 0.70
RAPID_MOVEMENT_WINDOW_HOURS = 48
# Found via eval (see EVALUATION notes / commit history): without a floor,
# this rule fires on trivial background transactions — e.g. a $240 credit
# followed by an unrelated $172 debit within 48h clears 70% easily, with
# zero suspicious meaning. Reusing REPORTING_THRESHOLD as the floor (not a
# new arbitrary number) also guarantees every injected RAPID_MOVEMENT
# instance still qualifies, since the generator's injected credits
# (typologies.py: $20,000-$60,000) sit well above it.
RAPID_MOVEMENT_MIN_CREDIT_AMOUNT = REPORTING_THRESHOLD

# --- CIRCULAR_FLOW (delegates to graph.find_circular_flows) ---
CIRCULAR_FLOW_MIN_RETENTION = 0.6
CIRCULAR_FLOW_MAX_LEN = 6

# --- HIGH_VELOCITY ---
# Blueprint: "24h txn count > mean + 3*std of account baseline". This batch
# job has no separate pre-period baseline window, so the baseline is the
# account's own distribution of per-day transaction counts across the
# observed period, excluding the single busiest day (which would otherwise
# inflate its own baseline).
HIGH_VELOCITY_STD_MULTIPLIER = 3.0
HIGH_VELOCITY_MIN_ABSOLUTE_COUNT = 8  # guards against a noisy std on short/quiet histories

# --- CASH_INTENSIVE ---
CASH_INTENSIVE_RATIO = 0.6
# Part 1's schema has no "cash-intensive business" classifier, so the
# blueprint's "AND business type not cash-intensive" is approximated as
# "not a business account" — a documented simplification, not a dropped
# clause.
CASH_INTENSIVE_EXCLUDE_ACCOUNT_TYPES = frozenset({"business"})

# --- CROSS_BORDER_RISK ---
# Both bands in data/reference/high_risk_countries.json count as "the
# configured high-risk list" for this rule.
CROSS_BORDER_INCLUDE_ELEVATED = True

# --- ROUND_AMOUNTS ---
ROUND_AMOUNTS_RATIO = 0.5
ROUND_AMOUNTS_MIN_COUNT = 10

# --- PROFILE_DEVIATION ---
PROFILE_DEVIATION_MULTIPLIER = 5.0

# --- DORMANT_REACTIVATION ---
# Blueprint's illustrative "180 days inactive" assumes a full-lifetime
# monitoring window. This build's synthetic dataset is one bounded batch
# of `days` total (see data/generator/config.yaml, default 180, demo
# default 60) — and the generator's own DORMANT_REACTIVATION injection
# (Part 1: background.py / typologies.py) caps the dormancy gap at ~80% of
# that window, so it can never reach a fixed 180-day threshold regardless
# of how suspicious the injected burst is. Using the blueprint's literal
# constant here would make the rule structurally unable to fire against
# this generator — a threshold bug, not a detection failure. 30 days
# matches what this batch/demo deployment can actually observe; a
# production deployment monitoring true full account lifetimes would
# restore something closer to the blueprint's 180.
DORMANT_MIN_INACTIVE_DAYS = 30
DORMANT_REACTIVATION_MULTIPLIER = 10.0

# --- Rule severity weights, feeding the composite rule_score (§12.5) ---
# Strong, typology-defining signals get full weight; weaker/contextual
# signals that mostly corroborate another finding rather than standing
# alone get partial weight. scoring.py computes
# `rule_score = min(1.0, sum(fired weights))`, so one strong rule can
# already saturate that sub-score, while a lone weak rule cannot push an
# otherwise-clean account into a high band by itself.
RULE_WEIGHTS: dict[str, float] = {
    "STRUCTURING": 1.0,
    "SMURFING": 1.0,
    "RAPID_MOVEMENT": 0.9,
    "CIRCULAR_FLOW": 1.0,
    "HIGH_VELOCITY": 0.7,
    "DORMANT_REACTIVATION": 0.9,
    "PROFILE_DEVIATION": 0.6,
    "CASH_INTENSIVE": 0.35,
    "CROSS_BORDER_RISK": 0.3,
    "ROUND_AMOUNTS": 0.35,
}

# --- Composite scoring (§12.5) ---
RULE_SCORE_WEIGHT = 0.45
ML_SCORE_WEIGHT = 0.35
GRAPH_SCORE_WEIGHT = 0.20

# Checked in order; first (lower_inclusive, label) where score >= lower wins.
RISK_BANDS: list[tuple[float, str]] = [
    (0.75, "HIGH"),
    (0.50, "MEDIUM"),
    (0.00, "LOW"),
]

# --- ML ensemble (§12.3) ---
ML_CONTAMINATION = 0.02
ML_SEED = 42
ML_LOF_N_NEIGHBORS = 25
ML_MIN_ACCOUNTS_TO_FIT = 10  # below this, an unsupervised ensemble isn't meaningful
