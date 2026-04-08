from typing import Dict, Any, Optional


def generate_justification(
    bid,
    totals: Dict[str, Any],
    assumptions_notes: Optional[str] = None
) -> str:
    """
    Generates a human-readable pricing justification suitable for:
    - internal approval
    - government procurement review
    - exported PDF / DOCX
    """

    parts: list[str] = []

    # Base pricing logic
    parts.append(
        "Pricing is based on verified supplier costs, required quantities, and current market conditions."
    )

    # Transportation
    parts.append(
        "Transportation costs reflect delivery distance, number of trips, fuel usage, equipment rental, "
        "and any delivery complexity required to meet contract requirements."
    )

    # Labor
    parts.append(
        "Labor costs include loading, unloading, driving, and administrative handling as applicable, "
        "calculated using standard hourly rates and estimated effort."
    )

    # Equipment
    equipment_total = float(totals.get("equipment_total", 0) or 0)
    if equipment_total > 0:
        parts.append(
            "Equipment rental and operator costs are included where required to ensure safe handling "
            "and timely execution of the scope of work."
        )

    # Overhead + risk
    parts.append(
        "Administrative overhead and a risk mitigation buffer are included to account for operational uncertainty, "
        "compliance requirements, and execution risk."
    )

    # Urgency impact
    urgency_level = int(getattr(bid, "urgency_level", 1) or 1)
    if urgency_level >= 4:
        parts.append(
            "Accelerated delivery requirements increased logistical coordination, labor scheduling, "
            "and operational intensity."
        )

    # Competition awareness (soft language, safe for gov review)
    competition = (getattr(bid, "competition_level", "") or "").lower()
    if competition == "high":
        parts.append(
            "Pricing reflects a competitive procurement environment while maintaining acceptable risk and performance margins."
        )

    # Assumptions / manual notes
    if assumptions_notes:
        parts.append(f"Assumptions / Notes: {assumptions_notes}")

    return " ".join(parts)
