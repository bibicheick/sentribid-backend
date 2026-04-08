from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# ─── Opportunity ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    company_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class BusinessProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    company_description: Optional[str] = None
    duns_uei: Optional[str] = None
    cage_code: Optional[str] = None
    sam_registered: Optional[bool] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    address_zip: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    naics_codes: Optional[Any] = None
    certifications: Optional[Any] = None
    set_aside_eligible: Optional[Any] = None
    contract_vehicles: Optional[Any] = None
    company_size: Optional[str] = None
    annual_revenue: Optional[str] = None
    employee_count: Optional[str] = None
    past_performance: Optional[Any] = None
    key_personnel: Optional[Any] = None
    core_competencies: Optional[Any] = None
    differentiators: Optional[Any] = None
    elevator_pitch: Optional[str] = None


class OpportunityCreate(BaseModel):
    title: str
    agency_name: str = ""
    agency_type: str = ""
    description: str = ""
    naics_code: str = ""
    psc_code: str = ""
    set_aside: str = ""
    estimated_value_low: Optional[float] = None
    estimated_value_high: Optional[float] = None
    location_city: str = ""
    location_state: str = ""
    posted_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    source_type: str = "manual"
    source_url: str = ""
    solicitation_number: str = ""
    contract_type: str = ""


class ProfileUpdate(BaseModel):
    company_name: str = ""
    company_description: str = ""
    elevator_pitch: str = ""
    duns_uei: str = ""
    cage_code: str = ""
    website: str = ""
    naics_codes: str = ""
    certifications: str = ""
    set_aside_eligible: str = ""
    contract_vehicles: str = ""
    core_competencies: str = ""
    differentiators: str = ""
    past_performance: str = ""
    key_personnel: str = ""
    capability_statement_text: str = ""
    company_size: str = ""
    annual_revenue: str = ""
    employee_count: str = ""


# ============================================================
# BIDS
# ============================================================

class BidCreate(BaseModel):
    contract_title: str
    agency_name: str
    agency_type: str
    solicitation_number: Optional[str] = None
    procurement_method: Optional[str] = None
    contract_type: str

    delivery_distance_miles: float = Field(default=0.0, ge=0)
    deadline_date: date
    urgency_level: int = Field(default=1, ge=1, le=5)
    competition_level: str
    risk_level: int = Field(default=1, ge=1, le=5)

    desired_profit_mode: str = "balanced"
    min_acceptable_profit: Optional[float] = Field(default=None, ge=0)
    margin_override_pct: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


class BidOut(BaseModel):
    id: int
    bid_code: str
    contract_title: str
    agency_name: str
    agency_type: str
    solicitation_number: Optional[str] = None
    procurement_method: Optional[str] = None
    contract_type: str
    delivery_distance_miles: float
    deadline_date: date
    urgency_level: int
    competition_level: str
    risk_level: int
    desired_profit_mode: str
    min_acceptable_profit: Optional[float] = None
    margin_override_pct: Optional[float] = None
    status: str
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    quantity: float = Field(gt=0)
    unit_cost: float = Field(ge=0)
    supplier_name: Optional[str] = None
    supplier_lead_time_days: Optional[int] = Field(default=None, ge=0)
    risk_flag: bool = False
    catalog_item_id: Optional[int] = None


class ItemFromCatalogCreate(BaseModel):
    quantity: float = Field(gt=0)


class LaborCreate(BaseModel):
    labor_type: str
    hourly_rate: float = Field(ge=0)
    hours: float = Field(ge=0)
    workers: int = Field(default=1, ge=1)


class TransportUpsert(BaseModel):
    transport_method: str = "truck"
    truck_rental_cost: Optional[float] = Field(default=None, ge=0)
    fuel_cost: Optional[float] = Field(default=None, ge=0)
    mileage_cost: Optional[float] = Field(default=None, ge=0)
    toll_fees: Optional[float] = Field(default=None, ge=0)
    driver_cost: Optional[float] = Field(default=None, ge=0)
    trips: int = Field(default=1, ge=1)
    delivery_complexity: Optional[str] = None


class OverheadUpsert(BaseModel):
    insurance_allocation: Optional[float] = Field(default=None, ge=0)
    storage_cost: Optional[float] = Field(default=None, ge=0)
    admin_time_cost: Optional[float] = Field(default=None, ge=0)
    bonding_compliance_cost: Optional[float] = Field(default=None, ge=0)
    misc_overhead: Optional[float] = Field(default=None, ge=0)


class EquipmentCreate(BaseModel):
    equipment_name: str
    rental_cost: float = Field(ge=0)
    rental_days: int = Field(default=1, ge=1)
    operator_required: bool = False
    operator_cost: Optional[float] = Field(default=None, ge=0)


class ApproveRequest(BaseModel):
    selected_mode: str
    approved_by: str = "internal"
    assumptions_notes: Optional[str] = None


class ComputeResponse(BaseModel):
    totals: Dict[str, Any]
    base_margin_pct: float
    recommendations: List[Dict[str, Any]]
    drift_warnings: List[Dict[str, Any]] = Field(default_factory=list)


class OutcomeResponse(BaseModel):
    totals: Dict[str, Any]
    base_margin_pct: float
    recommendations: List[Dict[str, Any]]
    selected: Dict[str, Any]
    drift_warnings: List[Dict[str, Any]] = Field(default_factory=list)


class OutcomeCreate(BaseModel):
    outcome: str = Field(default="pending", description="won/lost/no_bid/pending")
    submitted_price: Optional[float] = Field(default=None, ge=0)
    awarded_price: Optional[float] = Field(default=None, ge=0)
    competitor_count: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


class OutcomeOut(BaseModel):
    id: int
    bid_id: int
    outcome: str
    submitted_price: Optional[float] = None
    awarded_price: Optional[float] = None
    competitor_count: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LearningSummaryOut(BaseModel):
    bid_id: int
    outcome_count: int = 0
    win_rate: Optional[float] = None
    notes: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class OutcomeQuickCreate(BaseModel):
    outcome: str
    loss_reason: Optional[str] = None
    competitor_price: Optional[float] = None
    award_amount: Optional[float] = None
    notes: Optional[str] = None


# ============================================================
# AI COPILOT SCHEMAS
# ============================================================

class CopilotRiskItem(BaseModel):
    category: str
    severity: str  # low / medium / high / critical
    title: str
    detail: str
    recommendation: str


class CopilotRiskAnalysis(BaseModel):
    overall_risk_score: int  # 1-100
    risk_grade: str  # A/B/C/D/F
    items: List[CopilotRiskItem]
    summary: str


class CopilotProfitSuggestion(BaseModel):
    strategy: str
    description: str
    estimated_impact_pct: float
    confidence: str  # low / medium / high
    priority: int  # 1 = highest


class CopilotProfitAnalysis(BaseModel):
    current_margin_assessment: str
    suggestions: List[CopilotProfitSuggestion]
    optimal_mode: str
    summary: str


class CopilotComplianceFlag(BaseModel):
    rule: str
    status: str  # pass / warning / fail
    detail: str
    action_required: str


class CopilotComplianceAnalysis(BaseModel):
    overall_status: str  # compliant / needs_review / non_compliant
    flags: List[CopilotComplianceFlag]
    summary: str


class CopilotFullAnalysis(BaseModel):
    bid_id: int
    bid_code: str
    risk: CopilotRiskAnalysis
    profit: CopilotProfitAnalysis
    compliance: CopilotComplianceAnalysis
    executive_summary: str
    analyzed_at: str


class CopilotChatRequest(BaseModel):
    message: str
    context: Optional[str] = None


class CopilotChatResponse(BaseModel):
    reply: str
    suggestions: List[str] = Field(default_factory=list)


class CopilotPortfolioInsight(BaseModel):
    total_bids: int
    draft_count: int
    approved_count: int
    avg_risk: float
    high_risk_bids: List[Dict[str, Any]]
    recommendations: List[str]
    summary: str


# ============================================================
# CATALOG
# ============================================================

class VendorCreate(BaseModel):
    name: str
    website: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class VendorOut(BaseModel):
    id: int
    name: str
    website: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class CatalogItemCreate(BaseModel):
    vendor_id: int
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: str = "each"
    unit_price: float = Field(default=0, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=0)
    min_order_qty: Optional[float] = Field(default=None, ge=0)
    is_active: bool = True


class CatalogItemOut(BaseModel):
    id: int
    vendor_id: int
    vendor_name: str
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: str
    unit_price: float
    lead_time_days: Optional[int] = None
    min_order_qty: Optional[float] = None
    is_active: bool
    last_updated_at: Optional[datetime] = None


class CatalogPriceUpdate(BaseModel):
    price: float = Field(gt=0)
    source: str = "manual"
    note: Optional[str] = None


class CatalogPriceHistoryOut(BaseModel):
    id: int
    catalog_item_id: int
    price: float
    source: str
    note: Optional[str] = None
    recorded_at: datetime

    class Config:
        from_attributes = True


class StaleItemOut(BaseModel):
    catalog_item_id: int
    vendor_name: str
    name: str
    unit_price: float
    last_updated_at: Optional[datetime] = None
    age_days: int


class PriceSuggestionOut(BaseModel):
    catalog_item_id: int
    vendor_name: str
    name: str
    current_price: float
    suggested_price: float
    target: str
    reasoning: str


class QuoteOut(BaseModel):
    catalog_item_id: int
    vendor_id: int
    vendor_name: str
    name: str
    unit: str
    unit_price: float
    quantity: float
    line_total: float
    lead_time_days: Optional[int] = None
    price_age_days: int
