from app.db import SessionLocal
from app import models

def main():
    db = SessionLocal()

    deleted = (
        db.query(models.Bid)
        .filter(
            (models.Bid.contract_title == "string") |
            (models.Bid.agency_name == "string")
        )
        .delete(synchronize_session=False)
    )

    db.commit()
    db.close()

    print(f"✅ Deleted {deleted} dummy bid(s).")

if __name__ == "__main__":
    main()
