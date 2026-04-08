# backend/app/routers/copilot.py
"""Claude AI Bid Copilot — strategy analysis & interactive chat"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import require_auth
from .. import models
from ..claude_bid_copilot import analyze_bid_strategy, copilot_chat

logger = logging.getLogger("sentribid.copilot")
router = APIRouter(prefix="/copilot", tags=["copilot"])


def _get_bid_context(bid_id: int, db: Session, user_email: str):
    """Gather all context for a bid: bid data, opportunity, profile, history."""
    bid = db.query(models.Bid).filter(models.Bid.id == bid_id).first()
    if not bid:
        raise HTTPException(404, "Bid not found")

    bid_data = {
        "id": bid.id, "bid_code": bid.bid_code, "contract_title": bid.contract_title,
        "agency_name": bid.agency_name, "agency_type": bid.agency_type,
        "contract_type": bid.contract_type, "risk_level": bid.risk_level,
        "competition_level": bid.competition_level, "deadline_date": str(bid.deadline_date or ""),
        "status": bid.status, "notes": bid.notes or "",
        "desired_profit_mode": bid.desired_profit_mode,
    }

    # Find source opportunity
    opp_data = {}
    opps = db.query(models.Opportunity).filter(models.Opportunity.converted_bid_id == bid_id).all()
    if opps:
        opp = opps[0]
        opp_data = {
            "title": opp.title, "agency_name": opp.agency_name, "naics_code": opp.naics_code or "",
            "set_aside": opp.set_aside or "", "description": (opp.description or "")[:500],
            "estimated_value_low": opp.estimated_value_low or 0,
            "estimated_value_high": opp.estimated_value_high or 0,
            "ai_summary": opp.ai_summary or "", "ai_requirements": opp.ai_requirements or "",
            "ai_bid_strategy": opp.ai_bid_strategy or "", "ai_risk_flags": opp.ai_risk_flags or "",
            "ai_evaluation_factors": opp.ai_evaluation_factors or "",
            "ai_compliance_checklist": opp.ai_compliance_checklist or "",
        }

    # Get profile
    profile_data = {}
    user = db.query(models.User).filter(models.User.email == user_email).first()
    if user and user.profile:
        p = user.profile
        profile_data = {
            "company_name": p.company_name or "", "core_competencies": p.core_competencies or "",
            "certifications": p.certifications or "", "past_performance": p.past_performance or "",
            "differentiators": p.differentiators or "", "set_aside_eligible": p.set_aside_eligible or "",
            "annual_revenue": p.annual_revenue or "", "employee_count": p.employee_count or "",
            "capability_statement_text": (p.capability_statement_text or "")[:300],
        }

    # Historical bids
    history = []
    past_bids = db.query(models.Bid).filter(models.Bid.id != bid_id).order_by(models.Bid.created_at.desc()).limit(15).all()
    for pb in past_bids:
        history.append({
            "contract_title": pb.contract_title, "agency_name": pb.agency_name,
            "status": pb.status, "risk_level": pb.risk_level,
            "contract_type": pb.contract_type,
        })

    return bid_data, opp_data, profile_data, history


@router.post("/strategy/{bid_id}")
def get_bid_strategy(bid_id: int, user: str = Depends(require_auth), db: Session = Depends(get_db)):
    """Claude AI analyzes the bid and recommends optimal pricing strategy."""
    bid_data, opp_data, profile_data, history = _get_bid_context(bid_id, db, user)
    result = analyze_bid_strategy(bid_data, opp_data, profile_data, history)
    return result


@router.post("/chat/{bid_id}")
def chat_with_copilot(
    bid_id: int,
    body: dict = Body(...),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Interactive chat with Claude about this specific bid."""
    message = body.get("message", "")
    chat_history = body.get("history", [])
    if not message:
        raise HTTPException(400, "Message is required")

    bid_data, opp_data, profile_data, history = _get_bid_context(bid_id, db, user)
    response = copilot_chat(message, bid_data, opp_data, profile_data, chat_history, history)
    return {"response": response}
