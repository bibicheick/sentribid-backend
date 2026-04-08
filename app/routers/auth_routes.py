# backend/app/routers/auth_routes.py
"""
User registration, login, profile management, capability statement upload.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import (
    hash_password, verify_password, create_access_token,
    require_auth, get_current_user_id,
)
from .. import models, schemas

logger = logging.getLogger("sentribid.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

UPLOAD_DIR = os.getenv("SENTRIBID_UPLOAD_DIR", "./uploads")


# ─── Register ─────────────────────────────────────────────

@router.post("/register")
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email is required")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not payload.full_name or not payload.full_name.strip():
        raise HTTPException(400, "Full name is required")

    # Check if email already exists
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    # Create user
    user = models.User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        company_name=(payload.company_name or "").strip() or None,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Create empty business profile
    profile = models.BusinessProfile(
        user_id=user.id,
        company_name=user.company_name,
    )
    db.add(profile)
    db.commit()
    db.refresh(user)

    # Generate token
    token = create_access_token(subject=user.email, user_id=user.id, role=user.role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "company_name": user.company_name,
            "role": user.role,
            "has_profile": True,
        },
    }


# ─── Login ────────────────────────────────────────────────

@router.post("/login")
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Login with email + password. Also supports legacy admin login."""
    email = (payload.email or "").strip().lower()

    # Legacy admin login support (username-based)
    admin_user = os.getenv("SENTRIBID_ADMIN_USER", "admin")
    admin_pass = os.getenv("SENTRIBID_ADMIN_PASS", "admin123")
    if email == admin_user and payload.password == admin_pass:
        # Check if admin user exists in DB, create if not
        admin = db.query(models.User).filter(models.User.email == "admin@sentribid.local").first()
        if not admin:
            admin = models.User(
                email="admin@sentribid.local",
                password_hash=hash_password(admin_pass),
                full_name="Admin",
                company_name="SentriBiD Admin",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.flush()
            profile = models.BusinessProfile(user_id=admin.id, company_name="SentriBiD Admin")
            db.add(profile)
            db.commit()
            db.refresh(admin)

        token = create_access_token(subject=admin.email, user_id=admin.id, role=admin.role)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": admin.id,
                "email": admin.email,
                "full_name": admin.full_name,
                "company_name": admin.company_name,
                "role": admin.role,
                "has_profile": bool(admin.profile),
            },
        }

    # Normal email/password login
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is deactivated")

    token = create_access_token(subject=user.email, user_id=user.id, role=user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "company_name": user.company_name,
            "role": user.role,
            "has_profile": bool(user.profile),
        },
    }


# ─── Current User ─────────────────────────────────────────

@router.get("/me")
def get_me(user_sub: str = Depends(require_auth), db: Session = Depends(get_db)):
    """Get current user info."""
    user = db.query(models.User).filter(models.User.email == user_sub).first()
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "company_name": user.company_name,
        "role": user.role,
        "has_profile": bool(user.profile),
    }


# ─── Business Profile ─────────────────────────────────────

@router.get("/profile")
def get_profile(user_sub: str = Depends(require_auth), db: Session = Depends(get_db)):
    """Get current user's business profile."""
    user = db.query(models.User).filter(models.User.email == user_sub).first()
    if not user:
        raise HTTPException(404, "User not found")

    profile = user.profile
    if not profile:
        raise HTTPException(404, "No business profile found. Please complete your profile setup.")

    return profile


@router.put("/profile")
def update_profile(
    payload: schemas.BusinessProfileUpdate,
    user_sub: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update current user's business profile."""
    user = db.query(models.User).filter(models.User.email == user_sub).first()
    if not user:
        raise HTTPException(404, "User not found")

    profile = user.profile
    if not profile:
        profile = models.BusinessProfile(user_id=user.id)
        db.add(profile)

    # Update simple fields
    simple_fields = [
        "company_name", "company_description", "duns_uei", "cage_code", "sam_registered",
        "address_street", "address_city", "address_state", "address_zip", "phone", "website",
        "company_size", "annual_revenue", "employee_count", "elevator_pitch",
    ]
    for field in simple_fields:
        val = getattr(payload, field, None)
        if val is not None:
            setattr(profile, field, val)

    # Update JSON fields (store as JSON strings)
    json_fields = [
        "naics_codes", "certifications", "set_aside_eligible", "contract_vehicles",
        "past_performance", "key_personnel", "core_competencies", "differentiators",
    ]
    for field in json_fields:
        val = getattr(payload, field, None)
        if val is not None:
            setattr(profile, field, json.dumps(val))

    # Also update company_name on the User record
    if payload.company_name:
        user.company_name = payload.company_name

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    return profile


# ─── Capability Statement Upload ──────────────────────────

@router.post("/profile/capability-statement")
async def upload_capability_statement(
    file: UploadFile = File(...),
    user_sub: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Upload a capability statement PDF/DOCX. Auto-extracts text for AI context."""
    user = db.query(models.User).filter(models.User.email == user_sub).first()
    if not user:
        raise HTTPException(404, "User not found")

    profile = user.profile
    if not profile:
        profile = models.BusinessProfile(user_id=user.id)
        db.add(profile)

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(400, "Please upload a PDF, DOCX, or TXT file")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 10MB limit")

    # Save file
    cap_dir = os.path.join(UPLOAD_DIR, "capability-statements")
    os.makedirs(cap_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(cap_dir, safe_name)
    with open(filepath, "wb") as f:
        f.write(content)

    # Extract text
    extracted = ""
    try:
        if ext == "pdf":
            try:
                import pdfplumber
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages[:20]:
                        extracted += (page.extract_text() or "") + "\n"
                        if len(extracted) > 8000:
                            break
            except Exception:
                pass
        elif ext in ("docx", "doc"):
            try:
                from docx import Document as DocxDocument
                doc = DocxDocument(filepath)
                for para in doc.paragraphs:
                    extracted += para.text + "\n"
                    if len(extracted) > 8000:
                        break
            except Exception:
                pass
        elif ext == "txt":
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                extracted = f.read(8000)
    except Exception:
        pass

    profile.capability_statement_path = filepath
    profile.capability_statement_text = extracted[:8000] if extracted.strip() else None
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "ok": True,
        "filename": file.filename,
        "has_extracted_text": bool(extracted.strip()),
        "text_length": len(extracted.strip()),
    }
