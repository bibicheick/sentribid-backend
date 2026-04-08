# backend/app/routers/discovery.py
"""
Discovery Router v0.7.0 — SAM.gov search, subcontract scout, auto-scan,
compliance matrix, pipeline, and war room.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db import get_db
from .. import models

logger = logging.getLogger("sentribid.discovery")
router = APIRouter(prefix="/discovery", tags=["Discovery"])


# ─── SAM.gov Live Search ─────────────────────────────────

@router.get("/sam/search")
def sam_search(
    keyword: str = Query("", description="Search keyword"),
    naics: str = Query("", description="NAICS code filter"),
    set_aside: str = Query("", description="Set-aside type"),
    agency: str = Query("", description="Agency/department name"),
    opp_type: str = Query("", description="o=solicitation, p=presol, k=combined"),
    posted_from: str = Query("", description="MM/DD/YYYY"),
    posted_to: str = Query("", description="MM/DD/YYYY"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: str = Depends(require_auth),
):
    """Search SAM.gov for live federal contract opportunities."""
    from ..sam_connector import search_opportunities
    return search_opportunities(
        keyword=keyword, naics_code=naics, set_aside=set_aside, agency=agency,
        opportunity_type=opp_type, posted_from=posted_from, posted_to=posted_to,
        limit=limit, offset=offset,
    )


@router.post("/sam/import")
def sam_import_opportunity(
    body: dict = Body(...),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Import a SAM.gov opportunity into SentriBiD."""
    sam_data = body.get("opportunity", {})
    if not sam_data:
        raise HTTPException(400, "No opportunity data provided")

    existing = db.query(models.Opportunity).filter(
        models.Opportunity.solicitation_number == sam_data.get("solicitation_number", "")
    ).first()
    if existing:
        return {"id": existing.id, "message": "Already imported", "opp_code": existing.opp_code}

    import uuid
    opp = models.Opportunity(
        opp_code=f"OP-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}",
        title=sam_data.get("title", "Untitled"),
        agency_name=sam_data.get("agency_name", ""),
        solicitation_number=sam_data.get("solicitation_number", ""),
        naics_code=sam_data.get("naics_code", ""),
        due_date=sam_data.get("due_date", ""),
        posted_date=sam_data.get("posted_date", ""),
        contact_name=sam_data.get("contact_name", ""),
        contact_email=sam_data.get("contact_email", ""),
        status="new",
        source="sam.gov",
        sam_notice_id=sam_data.get("sam_notice_id", ""),
    )

    for field in ["set_aside_type", "description"]:
        if hasattr(opp, field) and sam_data.get(field.replace("set_aside_type", "set_aside")):
            setattr(opp, field, sam_data.get(field.replace("set_aside_type", "set_aside"), ""))

    db.add(opp)
    db.commit()
    db.refresh(opp)

    return {"id": opp.id, "opp_code": opp.opp_code, "message": "Imported from SAM.gov"}


@router.post("/sam/auto-match")
def sam_auto_match(
    body: dict = Body(default={}),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Search SAM.gov and auto-score against user's business profile using Claude AI."""
    from ..sam_connector import search_opportunities, score_opportunity_fit

    keyword = body.get("keyword", "")
    naics = body.get("naics", "")
    limit = body.get("limit", 15)

    u = db.query(models.User).filter(models.User.email == user).first()
    if not u or not u.profile:
        raise HTTPException(400, "Complete your Business Profile first for AI matching.")

    profile_text = _build_profile_text(u.profile)

    if not keyword and not naics:
        if u.profile.naics_codes:
            try:
                codes = json.loads(u.profile.naics_codes) if isinstance(u.profile.naics_codes, str) else u.profile.naics_codes
                if isinstance(codes, list) and codes:
                    naics = codes[0]
            except Exception:
                pass

    search_result = search_opportunities(keyword=keyword, naics_code=naics, limit=limit)
    if search_result.get("error"):
        return search_result

    scored = []
    for opp in search_result.get("opportunities", []):
        score = score_opportunity_fit(opp, profile_text)
        opp["fit_score"] = score.get("fit_score", 0)
        opp["recommendation"] = score.get("recommendation", "UNKNOWN")
        opp["match_reasons"] = score.get("match_reasons", [])
        opp["gaps"] = score.get("gaps", [])
        opp["suggested_action"] = score.get("suggested_action", "")
        scored.append(opp)

    scored.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
    return {"total": search_result.get("total", 0), "opportunities": scored, "cached": search_result.get("cached", False)}


# ─── NEW v0.7.0: Auto-Scan (profile-based SAM.gov search) ──

@router.post("/auto-scan")
def auto_scan(
    body: dict = Body(default={}),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Auto-Scan: Reads the user's profile (NAICS codes, certifications, keywords)
    and runs smart SAM.gov searches, returning AI-scored results.
    """
    u = db.query(models.User).filter(models.User.email == user).first()
    if not u or not u.profile:
        raise HTTPException(400, "Complete your Business Profile first to use Auto-Scan.")

    p = u.profile
    profile_text = _build_profile_text(p)

    # Build search queries from profile
    naics_list = []
    if p.naics_codes:
        raw = p.naics_codes
        try:
            parsed = json.loads(raw) if raw.strip().startswith("[") else [c.strip() for c in raw.split(",") if c.strip()]
            naics_list = parsed[:5]
        except Exception:
            naics_list = [c.strip() for c in raw.split(",") if c.strip()][:5]

    keywords = []
    if p.core_competencies:
        keywords = [w.strip() for w in p.core_competencies.split(",")[:3] if w.strip()]

    limit_per = body.get("limit", 10)

    all_opps = []
    seen_ids = set()

    from ..sam_connector import search_opportunities, score_opportunity_fit

    # Search by each NAICS code
    for naics in naics_list[:3]:
        try:
            result = search_opportunities(naics_code=naics, limit=limit_per)
            for opp in result.get("opportunities", []):
                oid = opp.get("solicitation_number") or opp.get("title")
                if oid not in seen_ids:
                    seen_ids.add(oid)
                    score = score_opportunity_fit(opp, profile_text)
                    opp["fit_score"] = score.get("fit_score", 0)
                    opp["recommendation"] = score.get("recommendation", "UNKNOWN")
                    opp["match_reasons"] = score.get("match_reasons", [])
                    opp["gaps"] = score.get("gaps", [])
                    opp["suggested_action"] = score.get("suggested_action", "")
                    opp["matched_by"] = f"NAICS {naics}"
                    all_opps.append(opp)
        except Exception as e:
            logger.warning(f"Auto-scan NAICS {naics} failed: {e}")

    # Search by keywords
    for kw in keywords[:2]:
        try:
            result = search_opportunities(keyword=kw, limit=limit_per)
            for opp in result.get("opportunities", []):
                oid = opp.get("solicitation_number") or opp.get("title")
                if oid not in seen_ids:
                    seen_ids.add(oid)
                    score = score_opportunity_fit(opp, profile_text)
                    opp["fit_score"] = score.get("fit_score", 0)
                    opp["recommendation"] = score.get("recommendation", "UNKNOWN")
                    opp["match_reasons"] = score.get("match_reasons", [])
                    opp["gaps"] = score.get("gaps", [])
                    opp["suggested_action"] = score.get("suggested_action", "")
                    opp["matched_by"] = f"Keyword: {kw}"
                    all_opps.append(opp)
        except Exception as e:
            logger.warning(f"Auto-scan keyword '{kw}' failed: {e}")

    all_opps.sort(key=lambda x: x.get("fit_score", 0), reverse=True)

    return {
        "total": len(all_opps),
        "opportunities": all_opps,
        "search_criteria": {
            "naics_codes": naics_list[:3],
            "keywords": keywords[:2],
        },
    }


# ─── NEW v0.7.0: Subcontract Scout ──────────────────────

@router.get("/subcontract-scout")
def subcontract_scout(
    days: int = Query(90, ge=7, le=365, description="Look back N days"),
    limit: int = Query(15, ge=1, le=50),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Subcontract Scout: Scan USAspending.gov for companies that recently won
    prime contracts matching the user's NAICS codes. Generates AI teaming pitches.
    """
    u = db.query(models.User).filter(models.User.email == user).first()
    if not u or not u.profile:
        raise HTTPException(400, "Complete your Business Profile first to use Subcontract Scout.")

    p = u.profile
    profile_text = _build_profile_text(p)

    naics_list = []
    if p.naics_codes:
        raw = p.naics_codes
        try:
            parsed = json.loads(raw) if raw.strip().startswith("[") else [c.strip() for c in raw.split(",") if c.strip()]
            naics_list = parsed[:5]
        except Exception:
            naics_list = [c.strip() for c in raw.split(",") if c.strip()][:5]

    if not naics_list:
        raise HTTPException(400, "Add NAICS codes to your profile to find matching prime awards.")

    from ..sam_connector import search_awards

    all_awards = []
    seen = set()

    for naics in naics_list[:3]:
        try:
            result = search_awards(naics_code=naics, limit=limit)
            for award in result.get("awards", []):
                key = award.get("contract_id") or f"{award.get('recipient', '')}-{award.get('amount', 0)}"
                if key not in seen:
                    seen.add(key)
                    all_awards.append(award)
        except Exception as e:
            logger.warning(f"Subcontract scout NAICS {naics} failed: {e}")

    all_awards.sort(key=lambda x: x.get("amount", 0), reverse=True)
    awards_to_return = all_awards[:limit]

    # Generate AI teaming pitches for top results
    pitches = []
    if awards_to_return:
        try:
            from ..claude_ai import call_claude
            for award in awards_to_return[:5]:
                prompt = f"""Generate a short teaming pitch email (3-4 sentences) for a small business
wanting to subcontract on this prime award:

PRIME CONTRACTOR: {award.get('recipient', 'Unknown')}
CONTRACT: {award.get('description', award.get('title', 'N/A'))}
AGENCY: {award.get('agency', 'N/A')}
AWARD AMOUNT: ${award.get('amount', 0):,.0f}
NAICS: {award.get('naics', 'N/A')}

OUR COMPANY:
{profile_text[:1500]}

Write a professional, concise teaming pitch. Return JSON:
{{"pitch_subject": "Email subject line", "pitch_body": "The email body", "key_selling_points": ["point1", "point2"]}}"""

                result = call_claude(
                    prompt,
                    system_instruction="You are an expert government subcontracting business developer. Write compelling teaming pitches. Return valid JSON only.",
                    json_mode=True,
                    max_tokens=800,
                )
                if result:
                    try:
                        cleaned = result.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                            if cleaned.endswith("```"):
                                cleaned = cleaned[:-3]
                        pitch = json.loads(cleaned)
                        pitch["award_recipient"] = award.get("recipient", "Unknown")
                        pitches.append(pitch)
                    except Exception:
                        pitches.append({
                            "award_recipient": award.get("recipient", "Unknown"),
                            "pitch_body": result[:500],
                            "pitch_subject": f"Teaming Opportunity — {award.get('description', 'Contract')[:60]}",
                        })
        except Exception as e:
            logger.warning(f"AI pitch generation failed: {e}")

    return {
        "total": len(awards_to_return),
        "awards": awards_to_return,
        "pitches": pitches,
        "search_criteria": {"naics_codes": naics_list[:3], "days_back": days},
    }


# ─── USAspending Awards Intelligence ─────────────────────

@router.get("/awards/search")
def search_historical_awards(
    keyword: str = Query(""),
    naics: str = Query(""),
    agency: str = Query(""),
    limit: int = Query(10, ge=1, le=50),
    user: str = Depends(require_auth),
):
    """Search USAspending.gov for historical contract awards."""
    from ..sam_connector import search_awards
    return search_awards(keyword=keyword, naics_code=naics, agency=agency, limit=limit)


# ─── RFP Shredder ────────────────────────────────────────

@router.post("/shred/{opp_id}")
def shred_rfp_endpoint(
    opp_id: int,
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Shred an RFP — extract all requirements, criteria, deadlines using Claude AI."""
    from ..compliance_engine import shred_rfp

    opp = db.query(models.Opportunity).filter(models.Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    doc_text = ""
    for att in opp.attachments:
        if att.extracted_text:
            doc_text += att.extracted_text + "\n\n"

    if not doc_text.strip():
        raise HTTPException(400, "No documents found. Upload an RFP first.")

    result = shred_rfp(doc_text, opportunity_title=opp.title)

    if hasattr(opp, 'shredded_rfp'):
        opp.shredded_rfp = json.dumps(result)
        db.commit()

    return result


# ─── Compliance Matrix ────────────────────────────────────

@router.post("/compliance-matrix/{opp_id}")
def generate_compliance_matrix_endpoint(
    opp_id: int,
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Generate a compliance matrix using Claude AI."""
    from ..compliance_engine import generate_compliance_matrix

    opp = db.query(models.Opportunity).filter(models.Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    shredded_data = getattr(opp, 'shredded_rfp', None)
    if not shredded_data:
        raise HTTPException(400, "Shred the RFP first.")

    shredded = json.loads(shredded_data)

    u = db.query(models.User).filter(models.User.email == user).first()
    profile_text = _build_profile_text(u.profile) if (u and u.profile) else "No profile"

    result = generate_compliance_matrix(shredded, profile_text)

    if hasattr(opp, 'compliance_matrix'):
        opp.compliance_matrix = json.dumps(result)
        db.commit()

    return result


# ─── Proposal Review ─────────────────────────────────────

@router.post("/review-proposal/{opp_id}")
def review_proposal_endpoint(
    opp_id: int,
    body: dict = Body(...),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Claude AI reviews a proposal draft against RFP requirements."""
    from ..compliance_engine import review_proposal_against_rfp

    opp = db.query(models.Opportunity).filter(models.Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    proposal_text = body.get("proposal_text", "")
    if not proposal_text:
        raise HTTPException(400, "Provide proposal_text")

    shredded = json.loads(opp.shredded_rfp) if getattr(opp, 'shredded_rfp', None) else {}
    matrix = json.loads(opp.compliance_matrix) if getattr(opp, 'compliance_matrix', None) else None

    return review_proposal_against_rfp(proposal_text, shredded, matrix)


# ─── War Room (Win Predictor) ────────────────────────────

@router.post("/war-room/{opp_id}")
def war_room_endpoint(
    opp_id: int,
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Run the AI War Room — complete competitive analysis powered by Claude."""
    from ..win_predictor import run_war_room
    from ..sam_connector import search_awards

    opp = db.query(models.Opportunity).filter(models.Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    opp_context = f"Title: {opp.title}\nAgency: {opp.agency_name}\nSolicitation: {opp.solicitation_number}\nNAICS: {opp.naics_code}\nDue: {opp.due_date}\n"
    for att in opp.attachments:
        if att.extracted_text:
            opp_context += f"\nDocument: {att.original_filename}\n{att.extracted_text[:3000]}"
    if opp.ai_summary:
        opp_context += f"\nAI Summary: {opp.ai_summary[:1000]}"

    u = db.query(models.User).filter(models.User.email == user).first()
    profile_text = _build_profile_text(u.profile) if (u and u.profile) else "No profile"

    historical = []
    search_term = opp.naics_code or (opp.title.split()[0] if opp.title else "")
    if search_term:
        try:
            award_result = search_awards(keyword=search_term, naics_code=opp.naics_code or "", agency=opp.agency_name or "", limit=10)
            historical = award_result.get("awards", [])
        except Exception:
            pass

    shredded = json.loads(opp.shredded_rfp) if getattr(opp, 'shredded_rfp', None) else None

    result = run_war_room(opp_context, profile_text, historical, shredded)

    if hasattr(opp, 'war_room_analysis'):
        opp.war_room_analysis = json.dumps(result)
        db.commit()

    return result


# ─── Pipeline ────────────────────────────────────────────

@router.put("/pipeline/{opp_id}")
def update_pipeline_stage(
    opp_id: int,
    body: dict = Body(...),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update opportunity pipeline stage."""
    opp = db.query(models.Opportunity).filter(models.Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    valid_stages = ["identified", "qualified", "capture", "proposal", "submitted", "won", "lost"]
    stage = body.get("stage", "")
    if stage and stage not in valid_stages:
        raise HTTPException(400, f"Invalid stage. Use: {valid_stages}")

    if stage and hasattr(opp, 'pipeline_stage'):
        opp.pipeline_stage = stage
    if "notes" in body and hasattr(opp, 'capture_notes'):
        opp.capture_notes = body["notes"]
    if "assigned_to" in body and hasattr(opp, 'assigned_to'):
        opp.assigned_to = body["assigned_to"]
    if "priority" in body and hasattr(opp, 'priority'):
        opp.priority = body["priority"]

    db.commit()
    return {"id": opp.id, "pipeline_stage": getattr(opp, 'pipeline_stage', 'identified'), "message": "Updated"}


@router.get("/pipeline")
def get_pipeline(
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Get all opportunities organized by pipeline stage."""
    opps = db.query(models.Opportunity).order_by(models.Opportunity.created_at.desc()).all()

    pipeline = {"identified": [], "qualified": [], "capture": [], "proposal": [], "submitted": [], "won": [], "lost": []}

    for opp in opps:
        stage = getattr(opp, 'pipeline_stage', None) or "identified"
        card = {
            "id": opp.id, "opp_code": opp.opp_code, "title": opp.title,
            "agency_name": opp.agency_name, "naics_code": opp.naics_code,
            "due_date": str(opp.due_date) if opp.due_date else None,
            "status": opp.status, "pipeline_stage": stage,
            "priority": getattr(opp, 'priority', 'medium'),
            "assigned_to": getattr(opp, 'assigned_to', None),
            "fit_score": opp.ai_confidence_score,
            "has_analysis": bool(opp.ai_summary),
            "has_shredded_rfp": bool(getattr(opp, 'shredded_rfp', None)),
            "has_war_room": bool(getattr(opp, 'war_room_analysis', None)),
            "converted_bid_id": opp.converted_bid_id,
            "source": getattr(opp, 'source', 'manual'),
        }
        pipeline.get(stage, pipeline["identified"]).append(card)

    stats = {stage: len(cards) for stage, cards in pipeline.items()}
    stats["total"] = len(opps)

    return {"pipeline": pipeline, "stats": stats}


# ─── Helper ──────────────────────────────────────────────

def _build_profile_text(profile) -> str:
    if not profile:
        return "No profile available"
    parts = []
    for field in ["company_name", "company_description", "elevator_pitch", "naics_codes",
                   "certifications", "set_aside_eligible", "core_competencies",
                   "differentiators", "past_performance", "key_personnel",
                   "annual_revenue", "employee_count", "capability_statement_text"]:
        val = getattr(profile, field, None)
        if val:
            parts.append(f"{field.replace('_', ' ').title()}: {str(val)[:1500]}")
    return "\n".join(parts)
