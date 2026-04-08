# backend/app/routers/profile.py
"""Business Profile management for SentriBiD v0.7.0"""
import os, logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import require_auth
from .. import models, schemas

logger = logging.getLogger("sentribid.profile")

# redirect_slashes=False lets us define both "" and "/" without 307 redirects
router = APIRouter(prefix="/profile", tags=["profile"], redirect_slashes=False)


def _get_or_create_profile(db, user_email):
    """Get or create a business profile for the user."""
    user = db.query(models.User).filter(models.User.email == user_email).first()
    if not user:
        user = db.query(models.User).filter(models.User.full_name == user_email).first()
    if not user:
        return None
    if not hasattr(models, "BusinessProfile"):
        return None
    if not user.profile:
        profile = models.BusinessProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return user.profile


def _profile_to_dict(p):
    fields = [
        "company_name", "company_description", "elevator_pitch", "duns_uei",
        "cage_code", "website", "naics_codes", "certifications", "set_aside_eligible",
        "contract_vehicles", "core_competencies", "differentiators", "past_performance",
        "key_personnel", "capability_statement_text", "company_size", "annual_revenue",
        "employee_count",
    ]
    return {f: getattr(p, f, "") or "" for f in fields}


@router.get("")
@router.get("/")
def get_profile(user: str = Depends(require_auth), db: Session = Depends(get_db)):
    """Get the current user's business profile."""
    p = _get_or_create_profile(db, user)
    if not p:
        return _profile_to_dict(None) if not p else {}
    db.commit()
    return _profile_to_dict(p)


@router.put("")
@router.put("/")
def update_profile(
    payload: schemas.ProfileUpdate,
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update the current user's business profile."""
    p = _get_or_create_profile(db, user)
    if not p:
        raise HTTPException(400, "Profile not available. Register an account first.")
    for field in payload.model_fields:
        setattr(p, field, getattr(payload, field))
    db.commit()
    return {"ok": True, "message": "Profile updated"}


@router.post("/capability-statement")
async def upload_capability_statement(
    file: UploadFile = File(...),
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Upload a capability statement PDF/DOCX/TXT and extract text."""
    p = _get_or_create_profile(db, user)
    if not p:
        raise HTTPException(400, "Profile not available. Register an account first.")
    content = await file.read()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    text = ""
    if ext == "pdf":
        try:
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages[:20]:
                    text += (page.extract_text() or "") + "\n"
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
    elif ext in ("docx", "doc"):
        try:
            from docx import Document as DocxDocument
            import io
            doc = DocxDocument(io.BytesIO(content))
            text = "\n".join(para.text for para in doc.paragraphs)
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}")
    elif ext == "txt":
        text = content.decode("utf-8", errors="replace")
    p.capability_statement_text = text[:5000]
    db.commit()
    return {"ok": True, "extracted_length": len(text), "message": "Capability statement uploaded"}
