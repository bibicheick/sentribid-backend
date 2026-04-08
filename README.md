# SentriBiD (Internal) — Backend

## Quick start (Windows PowerShell)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open:
- API docs: http://127.0.0.1:8000/docs

## What’s included
- FastAPI backend
- SQLite database (local)
- Pricing engine (true cost → risk buffer → margin → 3 bid modes)
- Approval/versioning
- Export endpoints:
  - CSV ✅
  - DOCX ✅ (basic generator)
  - PDF ✅ (basic generator)
  - Template-driven exports (Phase 2): copy templates into `app/templates/`
