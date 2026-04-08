from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


# =========================
# BIDS
# =========================

class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    bid_code = Column(String, unique=True, index=True)

    contract_title = Column(String, nullable=False)
    agency_name = Column(String, nullable=False)
    agency_type = Column(String, nullable=False)
    solicitation_number = Column(String, nullable=True)
    procurement_method = Column(String, nullable=True)
    contract_type = Column(String, nullable=False)

    delivery_distance_miles = Column(Float, nullable=False, default=0.0)
    deadline_date = Column(Date, nullable=False)
    urgency_level = Column(Integer, nullable=False, default=1)
    competition_level = Column(String, nullable=False)
    risk_level = Column(Integer, nullable=False, default=1)

    desired_profit_mode = Column(String, nullable=False, default="balanced")
    min_acceptable_profit = Column(Float, nullable=True)
    margin_override_pct = Column(Float, nullable=True)

    status = Column(String, nullable=False, default="draft")
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # AI Copilot analysis storage
    ai_risk_analysis = Column(Text, nullable=True)
    ai_profit_suggestions = Column(Text, nullable=True)
    ai_compliance_flags = Column(Text, nullable=True)
    ai_analyzed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    items = relationship("BidItem", back_populates="bid", cascade="all, delete-orphan")
    labor_lines = relationship("BidLaborLine", back_populates="bid", cascade="all, delete-orphan")
    transport = relationship("BidTransport", back_populates="bid", cascade="all, delete-orphan", uselist=False)
    overhead = relationship("BidOverhead", back_populates="bid", cascade="all, delete-orphan", uselist=False)
    equipment_lines = relationship("BidEquipmentLine", back_populates="bid", cascade="all, delete-orphan")
    versions = relationship("BidVersion", back_populates="bid", cascade="all, delete-orphan")
    outcome = relationship("BidOutcome", back_populates="bid", cascade="all, delete-orphan", uselist=False)
    attachments = relationship("BidAttachment", back_populates="bid", cascade="all, delete-orphan")


class BidItem(Base):
    __tablename__ = "bid_items"

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), index=True)
    catalog_item_id = Column(Integer, ForeignKey("catalog_items.id"), nullable=True, index=True)

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    quantity = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    supplier_name = Column(String, nullable=True)
    supplier_lead_time_days = Column(Integer, nullable=True)
    risk_flag = Column(Boolean, default=False)

    bid = relationship("Bid", back_populates="items")
    catalog_item = relationship("CatalogItem", back_populates="bid_items")


class BidLaborLine(Base):
    __tablename__ = "bid_labor_lines"

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), index=True)

    labor_type = Column(String, nullable=False)
    hourly_rate = Column(Float, nullable=False, default=0.0)
    hours = Column(Float, nullable=False, default=0.0)
    workers = Column(Integer, nullable=False, default=1)

    bid = relationship("Bid", back_populates="labor_lines")


class BidTransport(Base):
    __tablename__ = "bid_transport"

    bid_id = Column(Integer, ForeignKey("bids.id"), primary_key=True)

    transport_method = Column(String, nullable=False, default="truck")
    truck_rental_cost = Column(Float, nullable=True)
    fuel_cost = Column(Float, nullable=True)
    mileage_cost = Column(Float, nullable=True)
    toll_fees = Column(Float, nullable=True)
    driver_cost = Column(Float, nullable=True)
    trips = Column(Integer, nullable=False, default=1)
    delivery_complexity = Column(String, nullable=True)

    bid = relationship("Bid", back_populates="transport")


class BidOverhead(Base):
    __tablename__ = "bid_overhead"

    bid_id = Column(Integer, ForeignKey("bids.id"), primary_key=True)

    insurance_allocation = Column(Float, nullable=True)
    storage_cost = Column(Float, nullable=True)
    admin_time_cost = Column(Float, nullable=True)
    bonding_compliance_cost = Column(Float, nullable=True)
    misc_overhead = Column(Float, nullable=True)

    bid = relationship("Bid", back_populates="overhead")


class BidEquipmentLine(Base):
    __tablename__ = "bid_equipment_lines"

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), index=True)

    equipment_name = Column(String, nullable=False)
    rental_cost = Column(Float, nullable=False, default=0.0)
    rental_days = Column(Integer, nullable=False, default=1)
    operator_required = Column(Boolean, default=False)
    operator_cost = Column(Float, nullable=True)

    bid = relationship("Bid", back_populates="equipment_lines")


class BidVersion(Base):
    __tablename__ = "bid_versions"

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), index=True)

    version_no = Column(Integer, nullable=False)
    selected_mode = Column(String, nullable=False)
    totals_json = Column(Text, nullable=False)
    justification_text = Column(Text, nullable=False, default="")

    created_at = Column(DateTime, default=utcnow)
    created_by = Column(String, nullable=True)

    bid = relationship("Bid", back_populates="versions")


class BidAttachment(Base):
    __tablename__ = "bid_attachments"

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), index=True, nullable=False)

    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    category = Column(String, nullable=False, default="general")
    description = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)

    uploaded_at = Column(DateTime, default=utcnow)
    uploaded_by = Column(String, nullable=True)

    bid = relationship("Bid", back_populates="attachments")


# =========================
# LEARNING (Outcome tracking)
# =========================

class BidOutcome(Base):
    __tablename__ = "bid_outcomes"
    __table_args__ = (
        UniqueConstraint("bid_id", name="uq_bid_outcomes_bid_id"),
        Index("ix_bid_outcomes_outcome", "outcome"),
        Index("ix_bid_outcomes_agency", "agency_name"),
        Index("ix_bid_outcomes_competition", "competition_level"),
    )

    id = Column(Integer, primary_key=True)
    bid_id = Column(Integer, ForeignKey("bids.id"), nullable=False, index=True)

    agency_name = Column(String, nullable=False)
    agency_type = Column(String, nullable=False)
    competition_level = Column(String, nullable=False)
    contract_type = Column(String, nullable=False)

    selected_mode = Column(String, nullable=True)
    submitted_total = Column(Float, nullable=True)
    submitted_margin_pct = Column(Float, nullable=True)

    outcome = Column(String, nullable=False)
    loss_reason = Column(String, nullable=True)
    competitor_price = Column(Float, nullable=True)
    award_amount = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    bid = relationship("Bid", back_populates="outcome")


# =========================
# CATALOG
# =========================

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    website = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)

    items = relationship("CatalogItem", back_populates="vendor", cascade="all, delete-orphan")


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), index=True, nullable=False)

    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    sku = Column(String, index=True, nullable=True)
    category = Column(String, index=True, nullable=True)

    unit = Column(String, nullable=False, default="each")
    unit_price = Column(Float, nullable=False, default=0.0)
    lead_time_days = Column(Integer, nullable=True)
    min_order_qty = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)

    last_updated_at = Column(DateTime, default=utcnow)

    vendor = relationship("Vendor", back_populates="items")
    history = relationship("CatalogPriceHistory", back_populates="item", cascade="all, delete-orphan")
    bid_items = relationship("BidItem", back_populates="catalog_item")


class CatalogPriceHistory(Base):
    __tablename__ = "catalog_price_history"

    id = Column(Integer, primary_key=True)
    catalog_item_id = Column(Integer, ForeignKey("catalog_items.id"), index=True, nullable=False)

    price = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="manual")
    note = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=utcnow, index=True)

    item = relationship("CatalogItem", back_populates="history")


# =========================
# OPPORTUNITIES (Discovery Module)
# =========================

class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    opp_code = Column(String, unique=True, index=True)

    title = Column(String, nullable=False)
    agency_name = Column(String, nullable=False)
    agency_type = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    naics_code = Column(String, nullable=True)
    naics_description = Column(String, nullable=True)
    psc_code = Column(String, nullable=True)
    set_aside = Column(String, nullable=True)

    estimated_value_low = Column(Float, nullable=True)
    estimated_value_high = Column(Float, nullable=True)
    location_city = Column(String, nullable=True)
    location_state = Column(String, nullable=True)

    posted_date = Column(Date, nullable=True)
    due_date = Column(DateTime, nullable=True)

    source_type = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    source_id = Column(String, nullable=True)
    solicitation_number = Column(String, nullable=True)
    contract_type = Column(String, nullable=True)

    status = Column(String, nullable=False, default="new")

    # Fit scoring
    fit_score = Column(Float, nullable=True)
    fit_reasoning = Column(Text, nullable=True)

    # AI analysis fields
    ai_summary = Column(Text, nullable=True)
    ai_requirements = Column(Text, nullable=True)
    ai_evaluation_factors = Column(Text, nullable=True)
    ai_risk_flags = Column(Text, nullable=True)
    ai_compliance_checklist = Column(Text, nullable=True)
    ai_bid_strategy = Column(Text, nullable=True)
    ai_bid_recommendation = Column(String, nullable=True)
    ai_confidence_score = Column(Float, nullable=True)
    ai_analyzed_at = Column(DateTime, nullable=True)

    converted_bid_id = Column(Integer, ForeignKey("bids.id"), nullable=True)

    # ─── Discovery & Pipeline Fields (NEW) ────────────────
    source = Column(String, default="manual")               # manual / sam.gov / upload
    sam_notice_id = Column(String, nullable=True)            # SAM.gov notice ID
    set_aside_type = Column(String, nullable=True)           # Set-aside from SAM.gov
    contact_name = Column(String, nullable=True)             # POC name
    contact_email = Column(String, nullable=True)            # POC email
    pipeline_stage = Column(String, default="identified")    # identified/qualified/capture/proposal/submitted/won/lost
    priority = Column(String, default="medium")              # low/medium/high/critical
    assigned_to = Column(String, nullable=True)              # User email
    capture_notes = Column(Text, nullable=True)              # Capture plan notes

    # ─── AI Analysis Storage (NEW) ────────────────────────
    shredded_rfp = Column(Text, nullable=True)               # JSON: full RFP shred results
    compliance_matrix = Column(Text, nullable=True)          # JSON: compliance matrix
    war_room_analysis = Column(Text, nullable=True)          # JSON: war room results

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    attachments = relationship("OpportunityAttachment", back_populates="opportunity", cascade="all, delete-orphan")


class OpportunityAttachment(Base):
    __tablename__ = "opportunity_attachments"

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), index=True)

    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    category = Column(String, nullable=True, default="solicitation")
    extracted_text = Column(Text, nullable=True)
    original_filename = Column(String, nullable=True)

    uploaded_at = Column(DateTime, default=utcnow)

    opportunity = relationship("Opportunity", back_populates="attachments")


# =========================
# USERS & BUSINESS PROFILES
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="user")
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    profile = relationship("BusinessProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)

    # Company Info
    company_name = Column(String, nullable=True)
    company_description = Column(Text, nullable=True)
    duns_uei = Column(String, nullable=True)
    cage_code = Column(String, nullable=True)
    sam_registered = Column(Boolean, default=False)

    # Contact
    address_street = Column(String, nullable=True)
    address_city = Column(String, nullable=True)
    address_state = Column(String, nullable=True)
    address_zip = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)

    # Certifications & Capabilities
    naics_codes = Column(Text, nullable=True)
    certifications = Column(Text, nullable=True)
    set_aside_eligible = Column(Text, nullable=True)
    contract_vehicles = Column(Text, nullable=True)
    company_size = Column(String, nullable=True)
    annual_revenue = Column(String, nullable=True)
    employee_count = Column(String, nullable=True)

    # Past Performance
    past_performance = Column(Text, nullable=True)
    key_personnel = Column(Text, nullable=True)

    # Capability Statement
    capability_statement_path = Column(String, nullable=True)
    capability_statement_text = Column(Text, nullable=True)
    elevator_pitch = Column(Text, nullable=True)

    # Differentiators
    core_competencies = Column(Text, nullable=True)
    differentiators = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="profile")
