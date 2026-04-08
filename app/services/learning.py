from __future__ import annotations

import json
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models

VALID_OUTCOMES = {"won", "lost", "no_decision", "cancelled"}


def _norm_competition(x: Optional[str]) -> str:
    if not x:
        return "unknown"
    x = x.strip().lower()
    if x in {"low", "medium", "high"}:
        return x
    return "unknown"


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _latest_version_snapshot(bid: models.Bid) -> Dict[str, Any]:
    """
    Returns parsed totals_json from the latest BidVersion (best-effort).
    """
    if not getattr(bid, "versions", None):
        return {}
    try:
        latest = max(bid.versions, key=lambda v: ((v.version_no or 0), v.created_at))
        if not latest or not latest.totals_json:
            return {}
        return json.loads(latest.totals_json)
    except Exception:
        return {}


def record_outcome(db: Session, bid: models.Bid, payload: Dict[str, Any]) -> models.BidOutcome:
    """
    Upsert outcome for a bid.
    Auto-fills submitted_total / submitted_margin_pct / selected_mode from the latest BidVersion
    if not provided in payload.
    """
    outcome = (payload.get("outcome") or "").strip().lower()
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome '{outcome}'. Must be one of: {sorted(VALID_OUTCOMES)}")

    submitted_total = _safe_float(payload.get("submitted_total"))
    submitted_margin_pct = _safe_float(payload.get("submitted_margin_pct"))
    selected_mode = payload.get("selected_mode")

    # If missing, attempt to infer from the latest BidVersion snapshot
    if submitted_total is None or submitted_margin_pct is None or selected_mode is None:
        snap = _latest_version_snapshot(bid)
        # Your BidVersion frozen payload uses:
        # - final_bid_price
        # - margin_pct
        # - selected_mode
        if submitted_total is None:
            submitted_total = _safe_float(snap.get("final_bid_price"))
        if submitted_margin_pct is None:
            submitted_margin_pct = _safe_float(snap.get("margin_pct"))
        if selected_mode is None:
            selected_mode = snap.get("selected_mode") or snap.get("selected_mode".lower()) or snap.get("selected_mode".upper())

    existing = db.query(models.BidOutcome).filter(models.BidOutcome.bid_id == bid.id).first()
    if not existing:
        existing = models.BidOutcome(
            bid_id=bid.id,
            agency_name=bid.agency_name,
            agency_type=bid.agency_type,
            competition_level=_norm_competition(bid.competition_level),
            contract_type=bid.contract_type,
            outcome=outcome,
        )
        db.add(existing)

    # snapshot (keep in sync with bid)
    existing.agency_name = bid.agency_name
    existing.agency_type = bid.agency_type
    existing.competition_level = _norm_competition(bid.competition_level)
    existing.contract_type = bid.contract_type

    # payload
    existing.outcome = outcome
    existing.loss_reason = payload.get("loss_reason")
    existing.competitor_price = _safe_float(payload.get("competitor_price"))
    existing.award_amount = _safe_float(payload.get("award_amount"))
    existing.notes = payload.get("notes")

    existing.submitted_total = submitted_total
    existing.submitted_margin_pct = submitted_margin_pct
    existing.selected_mode = selected_mode

    db.commit()
    db.refresh(existing)
    return existing


def _learning_scope(bid: models.Bid) -> Dict[str, Any]:
    return {
        "agency_name": bid.agency_name,
        "competition_level": _norm_competition(bid.competition_level),
        "contract_type": bid.contract_type,
    }


def learning_summary_for_bid(
    db: Session, bid: models.Bid
) -> Tuple[Dict[str, Any], int, float, Optional[float], Optional[float]]:
    """
    Returns stats for similar past bids:
    - sample size
    - win_rate
    - avg_margin_wins
    - avg_margin_losses
    """
    scope = _learning_scope(bid)

    q = db.query(models.BidOutcome).filter(
        models.BidOutcome.agency_name == scope["agency_name"],
        models.BidOutcome.competition_level == scope["competition_level"],
        models.BidOutcome.contract_type == scope["contract_type"],
    )

    decided = q.filter(models.BidOutcome.outcome.in_(["won", "lost"]))

    sample_size = decided.count()
    if sample_size == 0:
        return scope, 0, 0.0, None, None

    wins = decided.filter(models.BidOutcome.outcome == "won").count()
    win_rate = wins / max(sample_size, 1)

    avg_margin_wins = db.query(func.avg(models.BidOutcome.submitted_margin_pct)).filter(
        models.BidOutcome.agency_name == scope["agency_name"],
        models.BidOutcome.competition_level == scope["competition_level"],
        models.BidOutcome.contract_type == scope["contract_type"],
        models.BidOutcome.outcome == "won",
        models.BidOutcome.submitted_margin_pct.isnot(None),
    ).scalar()

    avg_margin_losses = db.query(func.avg(models.BidOutcome.submitted_margin_pct)).filter(
        models.BidOutcome.agency_name == scope["agency_name"],
        models.BidOutcome.competition_level == scope["competition_level"],
        models.BidOutcome.contract_type == scope["contract_type"],
        models.BidOutcome.outcome == "lost",
        models.BidOutcome.submitted_margin_pct.isnot(None),
    ).scalar()

    return scope, sample_size, float(win_rate), _safe_float(avg_margin_wins), _safe_float(avg_margin_losses)


def recommend_margin_delta(
    db: Session, bid: models.Bid, base_margin_pct: float
) -> Tuple[float, str, int, float, Optional[float], Optional[float]]:
    """
    Outputs (delta_pct, reasoning, sample_size, win_rate, avg_margin_wins, avg_margin_losses)
    """
    scope, n, win_rate, avg_wins, avg_losses = learning_summary_for_bid(db, bid)

    if n < 3:
        return 0.0, "Not enough similar outcomes yet (need at least 3 decided bids).", n, win_rate, avg_wins, avg_losses

    comp = scope["competition_level"]
    if comp == "high":
        step = 1.0
    elif comp == "medium":
        step = 1.5
    else:
        step = 2.0

    if avg_wins is not None and avg_losses is not None:
        if win_rate < 0.35 and (avg_losses > avg_wins + 1.0):
            return -step, (
                f"Similar bids are losing more often (win rate {win_rate:.0%}). "
                f"Loss margins avg {avg_losses:.2f}% vs win margins avg {avg_wins:.2f}%. "
                f"Recommend lowering margin by {step:.1f}%."
            ), n, win_rate, avg_wins, avg_losses

        if win_rate > 0.65 and (avg_wins >= base_margin_pct - 0.5):
            return +step, (
                f"Similar bids have strong win rate ({win_rate:.0%}). "
                f"Average winning margin is {avg_wins:.2f}%. "
                f"Recommend increasing margin by {step:.1f}%."
            ), n, win_rate, avg_wins, avg_losses

    if win_rate < 0.35:
        return -step, f"Similar bids show low win rate ({win_rate:.0%}). Recommend reducing margin by {step:.1f}%.", n, win_rate, avg_wins, avg_losses
    if win_rate > 0.65:
        return +step, f"Similar bids show high win rate ({win_rate:.0%}). Recommend increasing margin by {step:.1f}%.", n, win_rate, avg_wins, avg_losses

    return 0.0, f"Similar bids are in a stable zone (win rate {win_rate:.0%}). No margin change recommended.", n, win_rate, avg_wins, avg_losses


def apply_learning_to_compute_response(db: Session, bid: models.Bid, compute_response: Dict[str, Any]) -> Dict[str, Any]:
    base_margin = float(compute_response.get("base_margin_pct", 0.0))
    delta, reasoning, n, win_rate, avg_wins, avg_losses = recommend_margin_delta(db, bid, base_margin)

    learned = round(base_margin + delta, 2)
    compute_response["learning"] = {
        "scope": {
            "agency_name": bid.agency_name,
            "competition_level": _norm_competition(bid.competition_level),
            "contract_type": bid.contract_type,
        },
        "sample_size": n,
        "win_rate": win_rate,
        "avg_margin_wins": avg_wins,
        "avg_margin_losses": avg_losses,
        "recommended_margin_delta_pct": delta,
        "learned_margin_pct": learned,
        "reasoning": reasoning,
    }

    recs = compute_response.get("recommendations") or []
    recs.insert(0, {
        "type": "learning_margin_adjustment",
        "message": f"Learning suggests margin {learned:.2f}% (delta {delta:+.1f}%). {reasoning}",
        "sample_size": n,
        "win_rate": win_rate,
        "delta_pct": delta,
        "learned_margin_pct": learned,
    })
    compute_response["recommendations"] = recs
    return compute_response
