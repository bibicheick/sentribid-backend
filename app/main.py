# backend/app/main.py
"""SentriBiD v0.7.0 — Gov Bid Intelligence API"""
from dotenv import load_dotenv
load_dotenv()

import os, sys, logging, secrets
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .routers import bids
from .auth import create_access_token, require_auth
from .db import engine, Base, SessionLocal
from . import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentribid")

# Create tables on startup
Base.metadata.create_all(bind=engine)


# Migrate: add AI columns if missing (SQLite only)
def _migrate_add_columns():
    import sqlalchemy
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.connect() as conn:
        inspector = sqlalchemy.inspect(engine)
        if "bids" in inspector.get_table_names():
            existing = {col["name"] for col in inspector.get_columns("bids")}
            new_cols = {
                "ai_risk_analysis": "TEXT",
                "ai_profit_suggestions": "TEXT",
                "ai_compliance_flags": "TEXT",
                "ai_analyzed_at": "DATETIME",
            }
            for col_name, col_type in new_cols.items():
                if col_name not in existing:
                    conn.execute(sqlalchemy.text(f"ALTER TABLE bids ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"  Added column bids.{col_name}")
        conn.commit()

try:
    _migrate_add_columns()
except Exception as e:
    logger.warning(f"  Migration note: {e}")


# ─── App ──────────────────────────────────────────────────
app = FastAPI(title="SentriBiD API", version="0.7.0")

# CORS — allow frontend domain (Railway) or localhost
_allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "sentribid-api", "version": app.version}


# ─── Auth Models ──────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str

class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: str = ""
    company_name: str = ""

class ResetPasswordIn(BaseModel):
    email: str


# ─── Auth: Login ──────────────────────────────────────────
@app.post("/auth/login")
def login(payload: LoginIn):
    from passlib.hash import bcrypt
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == payload.username).first()
        if user and bcrypt.verify(payload.password, user.password_hash):
            token = create_access_token(user.email)
            return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        logger.warning(f"DB user check error: {e}")
    finally:
        db.close()
    # Fallback to env admin
    admin_user = os.getenv("SENTRIBID_ADMIN_USER", "admin")
    admin_pass = os.getenv("SENTRIBID_ADMIN_PASS", "admin123")
    if payload.username == admin_user and payload.password == admin_pass:
        token = create_access_token(payload.username)
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid credentials")


# ─── Auth: Register ───────────────────────────────────────
@app.post("/auth/register")
def register(payload: RegisterIn):
    from passlib.hash import bcrypt
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing:
            raise HTTPException(400, "Email already registered")
        user = models.User(
            email=payload.email,
            password_hash=bcrypt.hash(payload.password),
            full_name=payload.full_name,
            company_name=payload.company_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        try:
            profile = models.BusinessProfile(user_id=user.id, company_name=payload.company_name)
            db.add(profile)
            db.commit()
            logger.info(f"Created user + profile: {user.email}")
        except Exception as e:
            logger.warning(f"Profile creation note: {e}")
        # Auto-login: return token so frontend can redirect immediately
        token = create_access_token(user.email)
        return {
            "ok": True,
            "user_id": user.id,
            "email": user.email,
            "access_token": token,
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(500, f"Registration failed: {str(e)}")
    finally:
        db.close()


# ─── Auth: Current User Info ──────────────────────────────
@app.get("/auth/me")
def get_current_user(user_sub: str = Depends(require_auth)):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == user_sub).first()
        if not user:
            return {"email": user_sub, "full_name": user_sub, "company_name": ""}
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name or user.email,
            "company_name": user.company_name or "",
            "role": user.role,
        }
    finally:
        db.close()


# ─── Auth: Password Reset (standalone — show temp password) ──
@app.post("/auth/reset-password")
def reset_password(payload: ResetPasswordIn):
    from passlib.hash import bcrypt
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == payload.email).first()
        if not user:
            raise HTTPException(404, "No account found with that email")
        temp_pw = secrets.token_urlsafe(10)
        user.password_hash = bcrypt.hash(temp_pw)
        db.commit()
        return {
            "ok": True,
            "temporary_password": temp_pw,
            "message": "Password has been reset. Use the temporary password below to log in, then change it in your profile.",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Password reset error: {e}")
        raise HTTPException(500, f"Reset failed: {str(e)}")
    finally:
        db.close()


# ─── Register Routers ─────────────────────────────────────
app.include_router(bids.router)

try:
    from .routers.opportunities import router as opportunities_router
    app.include_router(opportunities_router)
    logger.info("Opportunities router loaded")
except Exception as e:
    logger.warning(f"Opportunities router not loaded: {e}")

try:
    from .routers.discovery import router as discovery_router
    app.include_router(discovery_router)
    logger.info("Discovery router loaded")
except Exception as e:
    logger.warning(f"Discovery router not loaded: {e}")

try:
    from .routers.profile import router as profile_router
    app.include_router(profile_router)
    logger.info("Profile router loaded")
except Exception as e:
    logger.warning(f"Profile router not loaded: {e}")

try:
    from .routers.copilot import router as copilot_router
    app.include_router(copilot_router)
    logger.info("Copilot router loaded")
except Exception as e:
    logger.warning(f"Copilot router not loaded: {e}")


# ─── Frontend Serving (standalone mode) or API root ───────
_is_frozen = getattr(sys, 'frozen', False)
_frontend_served = False

if _is_frozen:
    import pathlib
    from starlette.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    _exe_dir = pathlib.Path(sys.executable).parent
    _frontend_dir = _exe_dir / "frontend-dist"

    if _frontend_dir.exists():
        _assets_dir = _frontend_dir / "assets"
        if _assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")

        _index_html = str(_frontend_dir / "index.html")
        _frontend_served = True
        logger.info(f"Frontend served from: {_frontend_dir}")

        _API_PREFIXES = (
            "bids", "opportunities", "auth", "health", "docs",
            "openapi.json", "copilot", "discovery", "profile",
        )

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve frontend SPA — catch all non-API routes."""
            if full_path and full_path.split("/")[0] in _API_PREFIXES:
                raise HTTPException(404, "Not found")
            file_path = _frontend_dir / full_path
            if full_path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(_index_html)
    else:
        logger.warning(f"frontend-dist not found at {_frontend_dir}")

if not _frontend_served:
    @app.get("/")
    def api_root():
        return {"name": "SentriBiD API", "version": app.version, "docs": "/docs"}
