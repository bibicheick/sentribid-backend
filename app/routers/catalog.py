from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db, engine, Base
from .. import models, schemas
from ..services.catalog_intel import get_latest_price, suggest_price
from ..services.catalog_import import (
    import_csv_bytes,
    import_xlsx_bytes,
    apply_price_updates_from_xlsx_bytes,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _ensure_tables():
    Base.metadata.create_all(bind=engine)


def _days_old(dt: Optional[datetime]) -> int:
    if not dt:
        return 999999
    now = datetime.now(timezone.utc)
    # Make it tz-aware if not already
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - dt).total_seconds() // 86400))


# ----------------------------
# Vendors
# ----------------------------

@router.post("/vendors", response_model=schemas.VendorOut)
def create_vendor(payload: schemas.VendorCreate, db: Session = Depends(get_db)):
    _ensure_tables()

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(400, "Vendor name is required")

    existing = db.query(models.Vendor).filter(models.Vendor.name == name).first()
    if existing:
        raise HTTPException(400, "Vendor already exists")

    v = models.Vendor(**payload.model_dump())
    v.name = name

    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.get("/vendors", response_model=List[schemas.VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    return db.query(models.Vendor).order_by(models.Vendor.name.asc()).all()


# ----------------------------
# Catalog Items
# ----------------------------

@router.post("/items", response_model=schemas.CatalogItemOut)
def create_item(payload: schemas.CatalogItemCreate, db: Session = Depends(get_db)):
    _ensure_tables()

    vendor = db.query(models.Vendor).filter(models.Vendor.id == payload.vendor_id).first()
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    item = models.CatalogItem(
        vendor_id=payload.vendor_id,
        name=payload.name,
        description=payload.description,
        sku=payload.sku,
        category=(payload.category or None),
        unit=payload.unit,
        unit_price=payload.unit_price,
        lead_time_days=payload.lead_time_days,
        min_order_qty=payload.min_order_qty,
        is_active=payload.is_active,
        last_updated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return schemas.CatalogItemOut(
        id=item.id,
        vendor_id=item.vendor_id,
        vendor_name=vendor.name,
        name=item.name,
        description=item.description,
        sku=item.sku,
        category=item.category,
        unit=item.unit,
        unit_price=float(item.unit_price or 0),
        lead_time_days=item.lead_time_days,
        min_order_qty=item.min_order_qty,
        is_active=bool(item.is_active),
        last_updated_at=item.last_updated_at,
    )


@router.get("/items", response_model=List[schemas.CatalogItemOut])
def list_items(
    vendor_id: Optional[int] = None,
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.CatalogItem, models.Vendor)
        .join(models.Vendor, models.CatalogItem.vendor_id == models.Vendor.id)
    )

    if vendor_id is not None:
        q = q.filter(models.CatalogItem.vendor_id == vendor_id)
    if category:
        q = q.filter(models.CatalogItem.category == category)
    if active_only:
        q = q.filter(models.CatalogItem.is_active == True)  # noqa: E712

    rows = q.order_by(models.CatalogItem.name.asc()).all()

    out: List[schemas.CatalogItemOut] = []
    for item, vendor in rows:
        out.append(
            schemas.CatalogItemOut(
                id=item.id,
                vendor_id=item.vendor_id,
                vendor_name=vendor.name,
                name=item.name,
                description=item.description,
                sku=item.sku,
                category=item.category,
                unit=item.unit,
                unit_price=float(item.unit_price or 0),
                lead_time_days=item.lead_time_days,
                min_order_qty=item.min_order_qty,
                is_active=bool(item.is_active),
                last_updated_at=item.last_updated_at,
            )
        )
    return out


@router.get("/search", response_model=List[schemas.CatalogItemOut])
def search_items(q: str, active_only: bool = True, db: Session = Depends(get_db)):
    q = (q or "").strip()
    if not q:
        return []

    query = (
        db.query(models.CatalogItem, models.Vendor)
        .join(models.Vendor, models.CatalogItem.vendor_id == models.Vendor.id)
    )

    like = f"%{q}%"
    query = query.filter(
        or_(
            models.CatalogItem.name.ilike(like),
            models.CatalogItem.sku.ilike(like),
            models.CatalogItem.category.ilike(like),
            models.Vendor.name.ilike(like),
        )
    )
    if active_only:
        query = query.filter(models.CatalogItem.is_active == True)  # noqa: E712

    rows = query.order_by(models.CatalogItem.name.asc()).limit(50).all()

    out: List[schemas.CatalogItemOut] = []
    for item, vendor in rows:
        out.append(
            schemas.CatalogItemOut(
                id=item.id,
                vendor_id=item.vendor_id,
                vendor_name=vendor.name,
                name=item.name,
                description=item.description,
                sku=item.sku,
                category=item.category,
                unit=item.unit,
                unit_price=float(item.unit_price or 0),
                lead_time_days=item.lead_time_days,
                min_order_qty=item.min_order_qty,
                is_active=bool(item.is_active),
                last_updated_at=item.last_updated_at,
            )
        )
    return out


# ----------------------------
# Pricing History + AI
# ----------------------------

@router.post("/items/{catalog_item_id}/price", response_model=schemas.CatalogPriceHistoryOut)
def update_price(catalog_item_id: int, payload: schemas.CatalogPriceUpdate, db: Session = Depends(get_db)):
    _ensure_tables()

    item = db.query(models.CatalogItem).filter(models.CatalogItem.id == catalog_item_id).first()
    if not item:
        raise HTTPException(404, "Catalog item not found")

    item.unit_price = float(payload.price)
    item.last_updated_at = datetime.now(timezone.utc)

    h = models.CatalogPriceHistory(
        catalog_item_id=catalog_item_id,
        price=float(payload.price),
        source=payload.source,
        note=payload.note,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.get("/items/{catalog_item_id}/history", response_model=List[schemas.CatalogPriceHistoryOut])
def get_price_history(catalog_item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.CatalogItem).filter(models.CatalogItem.id == catalog_item_id).first()
    if not item:
        raise HTTPException(404, "Catalog item not found")

    rows = (
        db.query(models.CatalogPriceHistory)
        .filter(models.CatalogPriceHistory.catalog_item_id == catalog_item_id)
        .order_by(models.CatalogPriceHistory.recorded_at.desc())
        .limit(50)
        .all()
    )
    return rows


@router.get("/insights/stale", response_model=List[schemas.StaleItemOut])
def stale_prices(days: int = 30, db: Session = Depends(get_db)):
    rows = (
        db.query(models.CatalogItem, models.Vendor)
        .join(models.Vendor, models.CatalogItem.vendor_id == models.Vendor.id)
        .filter(models.CatalogItem.is_active == True)  # noqa: E712
        .all()
    )

    out: List[schemas.StaleItemOut] = []
    for item, vendor in rows:
        age = _days_old(item.last_updated_at)
        if age >= days:
            out.append(
                schemas.StaleItemOut(
                    catalog_item_id=item.id,
                    vendor_name=vendor.name,
                    name=item.name,
                    unit_price=float(item.unit_price or 0),
                    last_updated_at=item.last_updated_at,
                    age_days=age,
                )
            )
    out.sort(key=lambda x: x.age_days, reverse=True)
    return out


@router.get("/insights/suggest", response_model=schemas.PriceSuggestionOut)
def suggest(catalog_item_id: int, target: str = "balanced", db: Session = Depends(get_db)):
    item = db.query(models.CatalogItem).filter(models.CatalogItem.id == catalog_item_id).first()
    if not item:
        raise HTTPException(404, "Catalog item not found")

    vendor = db.query(models.Vendor).filter(models.Vendor.id == item.vendor_id).first()
    vendor_name = vendor.name if vendor else "Unknown"

    suggested, reasoning = suggest_price(db, catalog_item_id=catalog_item_id, target=target)

    return schemas.PriceSuggestionOut(
        catalog_item_id=item.id,
        vendor_name=vendor_name,
        name=item.name,
        current_price=float(item.unit_price or 0),
        suggested_price=float(suggested),
        target=target,
        reasoning=reasoning,
    )


# ----------------------------
# Quote (uses freshest price)
# ----------------------------

@router.get("/quote", response_model=schemas.QuoteOut)
def quote(name: str, qty: float = 1.0, db: Session = Depends(get_db)):
    if qty <= 0:
        raise HTTPException(400, "qty must be > 0")

    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "name is required")

    like = f"%{name}%"
    rows = (
        db.query(models.CatalogItem, models.Vendor)
        .join(models.Vendor, models.CatalogItem.vendor_id == models.Vendor.id)
        .filter(models.CatalogItem.is_active == True)  # noqa: E712
        .filter(or_(models.CatalogItem.name.ilike(like), models.CatalogItem.sku.ilike(like)))
        .all()
    )

    if not rows:
        raise HTTPException(404, "No matching active catalog items found")

    scored = []
    for item, vendor in rows:
        latest_price, age_days = get_latest_price(db, item.id)
        lead = item.lead_time_days if item.lead_time_days is not None else 999999
        scored.append((float(latest_price), lead, age_days, item, vendor))

    # pick lowest price, then fastest lead time
    scored.sort(key=lambda x: (x[0], x[1]))
    latest_price, lead, age_days, best_item, best_vendor = scored[0]

    line_total = round(float(latest_price) * float(qty), 2)

    return schemas.QuoteOut(
        catalog_item_id=best_item.id,
        vendor_id=best_vendor.id,
        vendor_name=best_vendor.name,
        name=best_item.name,
        unit=best_item.unit,
        unit_price=float(latest_price),
        quantity=float(qty),
        line_total=line_total,
        lead_time_days=best_item.lead_time_days,
        price_age_days=age_days,
    )


# ----------------------------
# Import: CSV / Excel (Auto-merge)
# ----------------------------

@router.post("/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    default_vendor: Optional[str] = Form(None),
    default_category: Optional[str] = Form(None),
    source: str = Form("csv_import"),
    note: Optional[str] = Form(None),
    log_history_on_same_price: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV and auto-merge into catalog:
    - Create vendor if missing
    - Create item if missing
    - Update item fields if present
    - If price changes => log price history
    """
    _ensure_tables()

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    content = await file.read()
    summary = import_csv_bytes(
        db=db,
        content=content,
        source=source,
        note=note,
        default_vendor=default_vendor,
        default_category=default_category,
        log_history_on_same_price=log_history_on_same_price,
    )
    return {"ok": True, "filename": file.filename, "summary": summary.__dict__}


@router.post("/import/excel")
async def import_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    default_vendor: Optional[str] = Form(None),
    default_category: Optional[str] = Form(None),
    source: str = Form("excel_import"),
    note: Optional[str] = Form(None),
    log_history_on_same_price: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Upload an Excel (.xlsx) and auto-merge into catalog.
    Uses first sheet by default, or provide sheet_name.
    """
    _ensure_tables()

    if not (file.filename.lower().endswith(".xlsx") or file.filename.lower().endswith(".xlsm")):
        raise HTTPException(400, "Please upload a .xlsx or .xlsm file")

    content = await file.read()
    summary = import_xlsx_bytes(
        db=db,
        content=content,
        sheet_name=sheet_name,
        source=source,
        note=note,
        default_vendor=default_vendor,
        default_category=default_category,
        log_history_on_same_price=log_history_on_same_price,
    )
    return {"ok": True, "filename": file.filename, "sheet_name": sheet_name, "summary": summary.__dict__}


# ----------------------------
# Updates: Excel Template (Auto-merge price updates)
# ----------------------------

@router.post("/updates/excel")
async def apply_updates_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    source: str = Form("excel_price_update"),
    note: Optional[str] = Form(None),
    log_history_on_same_price: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Upload the SentriBiD Excel template and apply price updates to existing items.

    Matching priority:
    1) catalog_item_id (best)
    2) sku (fallback)
    """
    _ensure_tables()

    if not (file.filename.lower().endswith(".xlsx") or file.filename.lower().endswith(".xlsm")):
        raise HTTPException(400, "Please upload a .xlsx or .xlsm file")

    content = await file.read()
    summary = apply_price_updates_from_xlsx_bytes(
        db=db,
        content=content,
        sheet_name=sheet_name,
        source=source,
        note=note,
        default_vendor=None,
        log_history_on_same_price=log_history_on_same_price,
    )
    return {"ok": True, "filename": file.filename, "sheet_name": sheet_name, "summary": summary.__dict__}


# ----------------------------
# Import: Excel PRICE_UPDATES sheet only (compat endpoint)
# ----------------------------

@router.post("/import/excel-price-updates")
async def import_excel_price_updates(
    file: UploadFile = File(...),
    sheet_name: str = Form("PRICE_UPDATES"),
    default_vendor: Optional[str] = Form(None),
    source: str = Form("excel_price_updates"),
    note: Optional[str] = Form(None),
    log_history_on_same_price: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Upload an Excel and apply ONLY the PRICE_UPDATES sheet:
    - Finds existing catalog items
    - Updates unit_price (if changed)
    - Logs CatalogPriceHistory
    """
    _ensure_tables()

    if not (file.filename.lower().endswith(".xlsx") or file.filename.lower().endswith(".xlsm")):
        raise HTTPException(400, "Please upload a .xlsx or .xlsm file")

    content = await file.read()
    summary = apply_price_updates_from_xlsx_bytes(
        db=db,
        content=content,
        sheet_name=sheet_name,
        source=source,
        note=note,
        default_vendor=default_vendor,
        log_history_on_same_price=log_history_on_same_price,
    )
    return {"ok": True, "filename": file.filename, "sheet_name": sheet_name, "summary": summary.__dict__}
