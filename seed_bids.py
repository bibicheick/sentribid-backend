# seed_bids.py
from datetime import date, timedelta
from app.db import SessionLocal, engine, Base
from app import models

def ensure_tables():
    Base.metadata.create_all(bind=engine)

def delete_dummy_bids(db):
    # Remove the typical "string" demo rows
    q = db.query(models.Bid).filter(
        (models.Bid.contract_title == "string") |
        (models.Bid.agency_name == "string") |
        (models.Bid.bid_code.like("%0001%"))
    )
    count = q.count()
    q.delete(synchronize_session=False)
    return count

def add_bid(db, **kwargs):
    bid = models.Bid(**kwargs)
    db.add(bid)
    db.commit()
    db.refresh(bid)
    return bid

def main():
    ensure_tables()

    db = SessionLocal()
    try:
        deleted = delete_dummy_bids(db)

        today = date.today()

        # --- Seed bids (realistic) ---
        seeds = [
            dict(
                bid_code="SB-2026-0002",
                contract_title="Boise X-9 Printer Paper Supply (50 Boxes)",
                agency_name="Virginia Department of Health",
                agency_type="state",
                solicitation_number="RFQ-VA-2026-011",
                procurement_method="rfq",
                contract_type="supply",
                delivery_distance_miles=100.0,
                deadline_date=today + timedelta(days=10),
                urgency_level=3,
                competition_level="medium",
                risk_level=2,
                desired_profit_mode="balanced",
                min_acceptable_profit=250.0,
                margin_override_pct=None,
                notes="Include truck rental + fuel + unload. Optional forklift if dock unavailable.",
                status="draft",
                approved_at=None,
                approved_by=None,
            ),
            dict(
                bid_code="SB-2026-0003",
                contract_title="IT Equipment Logistics Support (Delivery + Setup)",
                agency_name="FEMA Region III",
                agency_type="federal",
                solicitation_number="FEMA-R3-LOG-2026-02",
                procurement_method="rfq",
                contract_type="service",
                delivery_distance_miles=62.0,
                deadline_date=today + timedelta(days=18),
                urgency_level=2,
                competition_level="high",
                risk_level=3,
                desired_profit_mode="conservative",
                min_acceptable_profit=500.0,
                margin_override_pct=8.5,
                notes="Higher competition; keep margin tight but safe.",
                status="draft",
                approved_at=None,
                approved_by=None,
            ),
            dict(
                bid_code="SB-2026-0004",
                contract_title="Network Refresh: Switches + Racks + Labor",
                agency_name="Department of Defense (DOD)",
                agency_type="federal",
                solicitation_number="DOD-NET-REFRESH-26-07",
                procurement_method="rfp",
                contract_type="mixed",
                delivery_distance_miles=22.0,
                deadline_date=today + timedelta(days=30),
                urgency_level=4,
                competition_level="medium",
                risk_level=4,
                desired_profit_mode="aggressive",
                min_acceptable_profit=10000.0,
                margin_override_pct=15.0,
                notes="Include labor, equipment rental, and compliance overhead.",
                status="draft",
                approved_at=None,
                approved_by=None,
            ),
        ]

        created = 0
        existing_codes = {b.bid_code for b in db.query(models.Bid.bid_code).all()}

        for s in seeds:
            if s["bid_code"] in existing_codes:
                continue
            add_bid(db, **s)
            created += 1

        print(f"✅ Deleted {deleted} dummy bid(s).")
        print(f"✅ Created {created} seed bid(s).")

    finally:
        db.close()

if __name__ == "__main__":
    main()
