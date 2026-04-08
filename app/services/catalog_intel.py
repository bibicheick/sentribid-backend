from __future__ import annotations
from typing import List, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from .. import models


def _days_old(dt: datetime | None) -> int:
    if not dt:
        return 999999
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # treat naive as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - dt).total_seconds() // 86400))


def get_latest_price(db: Session, catalog_item_id: int) -> Tuple[float, int]:
    """
    Returns (latest_price, age_days). If history exists, use latest history price,
    else use CatalogItem.unit_price.
    """
    item = db.query(models.CatalogItem).filter(models.CatalogItem.id == catalog_item_id).first()
    if not item:
        raise ValueError("Catalog item not found")

    h = (
        db.query(models.CatalogPriceHistory)
        .filter(models.CatalogPriceHistory.catalog_item_id == catalog_item_id)
        .order_by(models.CatalogPriceHistory.recorded_at.desc())
        .first()
    )
    if h:
        return float(h.price), _days_old(h.recorded_at)
    return float(item.unit_price or 0.0), _days_old(item.last_updated_at)


def suggest_price(db: Session, catalog_item_id: int, target: str = "balanced") -> Tuple[float, List[str]]:
    """
    Lightweight "AI" (rule-based intelligence):
    - Look at last N prices (history)
    - Use median-ish anchor
    - Apply target multiplier (win vs profit)
    """
    item = db.query(models.CatalogItem).filter(models.CatalogItem.id == catalog_item_id).first()
    if not item:
        raise ValueError("Catalog item not found")

    target = (target or "balanced").lower()
    reasoning: List[str] = []

    # pull recent history
    history = (
        db.query(models.CatalogPriceHistory)
        .filter(models.CatalogPriceHistory.catalog_item_id == catalog_item_id)
        .order_by(models.CatalogPriceHistory.recorded_at.desc())
        .limit(10)
        .all()
    )

    current = float(item.unit_price or 0.0)
    reasoning.append(f"Current stored price: {current:.2f}")

    if not history:
        # no history: simple target lift
        if target == "conservative":
            suggested = current * 1.03
            reasoning.append("No price history yet → small +3% (conservative).")
        elif target == "aggressive":
            suggested = current * 1.10
            reasoning.append("No price history yet → +10% (aggressive profit focus).")
        else:
            suggested = current * 1.06
            reasoning.append("No price history yet → +6% (balanced).")
        return round(suggested, 2), reasoning

    prices = [float(h.price or 0.0) for h in history if h.price is not None]
    prices = [p for p in prices if p > 0]
    if not prices:
        suggested = current
        reasoning.append("History exists but prices are invalid → keep current.")
        return round(suggested, 2), reasoning

    prices_sorted = sorted(prices)
    mid = len(prices_sorted) // 2
    median = prices_sorted[mid] if len(prices_sorted) % 2 == 1 else (prices_sorted[mid - 1] + prices_sorted[mid]) / 2.0

    reasoning.append(f"Median of last {len(prices_sorted)} recorded prices: {median:.2f}")

    # target multipliers
    if target == "conservative":
        mult = 1.02
        reasoning.append("Target=conservative → small uplift for win chance.")
    elif target == "aggressive":
        mult = 1.10
        reasoning.append("Target=aggressive → higher uplift for profit.")
    else:
        mult = 1.06
        reasoning.append("Target=balanced → moderate uplift (win + profit).")

    suggested = median * mult

    # stale guardrail: if last update old, add a small extra buffer
    age = _days_old(item.last_updated_at)
    if age >= 30:
        suggested *= 1.02
        reasoning.append(f"Price is stale ({age} days) → add +2% buffer.")

    # never suggest below last recorded min (protect margin)
    min_hist = min(prices_sorted)
    if suggested < min_hist:
        suggested = min_hist
        reasoning.append("Guardrail: raised to historical minimum price.")

    return round(suggested, 2), reasoning
