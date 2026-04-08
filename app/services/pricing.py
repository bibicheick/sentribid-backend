from __future__ import annotations

from typing import Dict, Any, List, Optional
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# =========================
# CONFIG
# =========================

# Risk buffer applied to total true cost
RISK_BUFFER_PCT = {1: 0.02, 2: 0.04, 3: 0.06, 4: 0.08, 5: 0.10}

# Base margin by competition level (high competition => lower baseline margin)
COMP_BASE_MARGIN = {"high": 0.06, "medium": 0.12, "low": 0.20}

# Margin adjustments by contract type
CONTRACT_ADJ = {"supply": -0.02, "service": 0.05, "mixed": 0.03}

# Margin adjustments by urgency level
URGENCY_ADJ = {1: 0.00, 2: 0.00, 3: 0.02, 4: 0.04, 5: 0.06}

MIN_MARGIN = 0.05
MAX_MARGIN = 0.35


# ----------------------------
# Agency Profiles (weights + floors)
# ----------------------------

PROFILES = {
    "county":  {"win_weight": 0.50, "profit_weight": 0.50, "min_margin": 0.05, "risk_floor": 0.10},
    "federal": {"win_weight": 0.55, "profit_weight": 0.45, "min_margin": 0.06, "risk_floor": 0.12},
    "state":   {"win_weight": 0.52, "profit_weight": 0.48, "min_margin": 0.05, "risk_floor": 0.10},
}


# =========================
# HELPERS
# =========================

def _norm_str(x: Any) -> str:
    return (str(x).strip().lower() if x is not None else "")


def _safe_int(x: Any, default: int) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def money(x: Any) -> float:
    """
    Stable 2-decimal rounding (bank-safe enough for bids).
    Always returns float.
    """
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def get_profile_name(bid) -> str:
    p = _norm_str(getattr(bid, "agency_type", None))
    return p if p in PROFILES else "county"


def get_profile(bid) -> dict:
    return PROFILES.get(get_profile_name(bid), PROFILES["county"])


# =========================
# TOTALS
# =========================

def compute_totals(bid) -> Dict[str, Any]:
    items = getattr(bid, "items", []) or []
    labor_lines = getattr(bid, "labor_lines", []) or []
    equipment_lines = getattr(bid, "equipment_lines", []) or []
    transport = getattr(bid, "transport", None)
    overhead = getattr(bid, "overhead", None)

    item_subtotal = 0.0
    for it in items:
        qty = _safe_float(getattr(it, "quantity", 0.0), 0.0)
        unit_cost = _safe_float(getattr(it, "unit_cost", 0.0), 0.0)
        # guard negatives (bad input)
        item_subtotal += max(qty, 0.0) * max(unit_cost, 0.0)

    labor_total = 0.0
    for ln in labor_lines:
        rate = _safe_float(getattr(ln, "hourly_rate", 0.0), 0.0)
        hours = _safe_float(getattr(ln, "hours", 0.0), 0.0)
        workers = _safe_int(getattr(ln, "workers", 1), 1)
        labor_total += max(rate, 0.0) * max(hours, 0.0) * max(workers, 1)

    transport_total = 0.0
    if transport:
        t = transport
        trips = max(_safe_int(getattr(t, "trips", 1), 1), 1)
        per_trip = (
            max(_safe_float(getattr(t, "truck_rental_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(t, "fuel_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(t, "mileage_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(t, "toll_fees", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(t, "driver_cost", 0.0), 0.0), 0.0)
        )
        transport_total = per_trip * trips

    equipment_total = 0.0
    for eq in equipment_lines:
        rental_cost = max(_safe_float(getattr(eq, "rental_cost", 0.0), 0.0), 0.0)
        rental_days = max(_safe_int(getattr(eq, "rental_days", 1), 1), 1)
        equipment_total += rental_cost * rental_days

        operator_required = bool(getattr(eq, "operator_required", False))
        if operator_required:
            equipment_total += max(_safe_float(getattr(eq, "operator_cost", 0.0), 0.0), 0.0)

    overhead_total = 0.0
    if overhead:
        o = overhead
        overhead_total = (
            max(_safe_float(getattr(o, "insurance_allocation", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(o, "storage_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(o, "admin_time_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(o, "bonding_compliance_cost", 0.0), 0.0), 0.0) +
            max(_safe_float(getattr(o, "misc_overhead", 0.0), 0.0), 0.0)
        )

    true_cost = item_subtotal + labor_total + transport_total + equipment_total + overhead_total

    risk_level = int(clamp(_safe_int(getattr(bid, "risk_level", 1), 1), 1, 5))
    risk_pct = RISK_BUFFER_PCT.get(risk_level, RISK_BUFFER_PCT[1])
    risk_buffer = true_cost * risk_pct
    adjusted_cost = true_cost + risk_buffer

    return {
        "item_subtotal": money(item_subtotal),
        "labor_total": money(labor_total),
        "transport_total": money(transport_total),
        "equipment_total": money(equipment_total),
        "overhead_total": money(overhead_total),
        "true_cost": money(true_cost),
        "risk_pct": float(risk_pct),
        "risk_buffer": money(risk_buffer),
        "adjusted_cost": money(adjusted_cost),
    }


# =========================
# MARGINS + WIN SCORE
# =========================

def compute_final_margin_pct(bid) -> float:
    comp = _norm_str(getattr(bid, "competition_level", None))
    ctype = _norm_str(getattr(bid, "contract_type", None))
    urgency = int(clamp(_safe_int(getattr(bid, "urgency_level", 1), 1), 1, 5))

    base = COMP_BASE_MARGIN.get(comp, 0.12)
    contract_adj = CONTRACT_ADJ.get(ctype, 0.0)
    urgency_adj = URGENCY_ADJ.get(urgency, 0.0)

    final_margin = base + contract_adj + urgency_adj

    # If user overrides margin percent (stored as percent, e.g. 12.5)
    margin_override_pct = getattr(bid, "margin_override_pct", None)
    if margin_override_pct is not None:
        final_margin = (_safe_float(margin_override_pct, 0.0) / 100.0)

    # Profile floors
    prof = get_profile(bid)
    prof_min = float(prof.get("min_margin", MIN_MARGIN))
    risk_floor = float(prof.get("risk_floor", 0.10))

    # Extra guardrail: higher risk should not run too thin
    risk_level = int(clamp(_safe_int(getattr(bid, "risk_level", 1), 1), 1, 5))
    if risk_level >= 4:
        final_margin = max(final_margin, risk_floor)

    return clamp(final_margin, max(MIN_MARGIN, prof_min), MAX_MARGIN)


def margin_for_mode(final_margin: float, mode: str) -> float:
    mode = _norm_str(mode)
    if mode == "conservative":
        return clamp(final_margin * 0.70, MIN_MARGIN, MAX_MARGIN)
    if mode == "aggressive":
        return clamp(final_margin * 1.25, MIN_MARGIN, MAX_MARGIN)
    return clamp(final_margin, MIN_MARGIN, MAX_MARGIN)


def compute_win_score(bid, mode: str) -> int:
    """
    Heuristic score (20-95):
    - conservative (lower price) -> higher win score
    - aggressive (higher price) -> lower win score
    - high competition penalizes
    - high urgency slightly penalizes
    - high risk penalizes
    """
    score = 60

    mode = _norm_str(mode)
    comp = _norm_str(getattr(bid, "competition_level", None))
    urgency = int(clamp(_safe_int(getattr(bid, "urgency_level", 1), 1), 1, 5))
    risk = int(clamp(_safe_int(getattr(bid, "risk_level", 1), 1), 1, 5))

    # Mode impact
    if mode == "conservative":
        score += 15
    elif mode == "balanced":
        score += 5
    elif mode == "aggressive":
        score -= 10

    # Competition impact
    if comp == "high":
        score -= 15
    elif comp == "medium":
        score -= 5
    elif comp == "low":
        score += 10

    # Urgency impact
    if urgency >= 4:
        score -= 5

    # Risk impact
    if risk >= 4:
        score -= 5

    return int(clamp(score, 20, 95))


# =========================
# RECOMMENDATIONS
# =========================

def compute_recommendations(bid, db=None) -> Dict[str, Any]:
    """
    Returns:
      {
        "totals": {...},
        "base_margin_pct": <percent float>,
        "recommendations": [
            {"mode": "...", "margin_pct": <percent>, "profit_amount": <money>, "bid_price": <money>, ...},
            ...
        ]
      }

    NOTE: db is accepted for API compatibility (future enhancements), but not required.
    """
    totals = compute_totals(bid)
    base_margin = compute_final_margin_pct(bid)

    recs: List[Dict[str, Any]] = []
    for mode in ["conservative", "balanced", "aggressive"]:
        m = margin_for_mode(base_margin, mode)

        adjusted_cost = _safe_float(totals.get("adjusted_cost", 0.0), 0.0)
        profit = adjusted_cost * m
        bid_price = adjusted_cost + profit

        warnings: List[str] = []
        min_profit = getattr(bid, "min_acceptable_profit", None)
        if min_profit is not None and profit < float(min_profit):
            warnings.append("Profit below minimum threshold")
        if (_safe_int(getattr(bid, "risk_level", 1), 1) >= 4) and m <= 0.08:
            warnings.append("High risk with low margin")

        recs.append({
            "mode": mode,
            "margin_pct": money(m * 100.0),
            "profit_amount": money(profit),
            "profit_pct": money(m * 100.0),
            "bid_price": money(bid_price),
            "win_score": compute_win_score(bid, mode),
            "warnings": warnings,
        })

    return {
        "totals": totals,
        "base_margin_pct": money(base_margin * 100.0),
        "recommendations": recs,
    }


# =========================
# AUTO SELECTION
# =========================

def auto_select_best(
    recommendations: list,
    win_weight: float = 0.5,
    profit_weight: float = 0.5
) -> Optional[dict]:
    """
    Weighted Win + Profit selection.

    IMPORTANT:
    - Filters out non-mode entries (e.g., learning messages inserted into recommendations)
    """
    if not recommendations:
        return None

    # Keep only actual priced options
    mode_recs = [r for r in recommendations if isinstance(r, dict) and r.get("mode") in {"conservative", "balanced", "aggressive"}]
    if not mode_recs:
        return None

    max_profit = max(_safe_float(r.get("profit_amount", 0.0), 0.0) for r in mode_recs) or 1.0

    best: Optional[dict] = None
    best_score = -1.0

    for r in mode_recs:
        profit_amt = _safe_float(r.get("profit_amount", 0.0), 0.0)
        win = _safe_float(r.get("win_score", 0.0), 0.0)

        profit_score = profit_amt / max_profit
        win_score = win / 100.0

        score = (win_weight * win_score) + (profit_weight * profit_score)

        if score > best_score:
            best_score = score
            best = r

    return best
