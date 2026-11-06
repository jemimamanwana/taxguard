from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Taxpayer(Base):
    __tablename__ = "taxpayers"
    tin: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(80), index=True)
    registration_date: Mapped[str] = mapped_column(String(10))
    size_band: Mapped[str] = mapped_column(String(10))
    group_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    is_foreign: Mapped[bool] = mapped_column(Boolean, default=False)
    jurisdiction: Mapped[str] = mapped_column(String(60))
    low_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="")
    town: Mapped[str] = mapped_column(String(40), default="")


class Group(Base):
    __tablename__ = "groups"
    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_tin: Mapped[str] = mapped_column(String(16))
    sister_tin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hub_tin: Mapped[str | None] = mapped_column(String(16), nullable=True)


class VatReturn(Base):
    __tablename__ = "vat_returns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tin: Mapped[str] = mapped_column(String(16), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    standard_sales: Mapped[float] = mapped_column(Float)
    zero_rated_sales: Mapped[float] = mapped_column(Float)
    output_vat: Mapped[float] = mapped_column(Float)
    input_vat: Mapped[float] = mapped_column(Float)
    capital_purchases: Mapped[float] = mapped_column(Float)
    imported_services: Mapped[float] = mapped_column(Float)
    reverse_charge_vat: Mapped[float] = mapped_column(Float)
    net_vat: Mapped[float] = mapped_column(Float)
    refund_claimed: Mapped[float] = mapped_column(Float)
    filed_on: Mapped[str] = mapped_column(String(10))


class Claim(Base):
    __tablename__ = "claims"
    claim_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tin: Mapped[str] = mapped_column(String(16), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    refund_claimed: Mapped[float] = mapped_column(Float)
    input_vat_claimed: Mapped[float] = mapped_column(Float)
    submitted_on: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), index=True)  # pending/approved/adjusted/docs_requested/escalated
    assigned_officer: Mapped[str | None] = mapped_column(String(40), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lane: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="batch")  # batch / portal


class Invoice(Base):
    __tablename__ = "invoices"
    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    supplier_tin: Mapped[str] = mapped_column(String(16), index=True)
    buyer_tin: Mapped[str] = mapped_column(String(16), index=True)
    invoice_no: Mapped[str] = mapped_column(String(40), index=True)
    invoice_date: Mapped[str] = mapped_column(String(10))
    period_claimed: Mapped[str] = mapped_column(String(7))
    net: Mapped[float] = mapped_column(Float)
    vat: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="LSL")
    kind: Mapped[str] = mapped_column(String(16), default="goods")
    image_file: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extractor: Mapped[str | None] = mapped_column(String(30), nullable=True)
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checks: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SupplierListing(Base):
    __tablename__ = "supplier_listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_tin: Mapped[str] = mapped_column(String(16), index=True)
    invoice_no: Mapped[str] = mapped_column(String(40), index=True)
    buyer_tin: Mapped[str] = mapped_column(String(16))
    invoice_date: Mapped[str] = mapped_column(String(10))
    period: Mapped[str] = mapped_column(String(7))
    vat: Mapped[float] = mapped_column(Float)


class RelatedPartyTxn(Base):
    __tablename__ = "related_party_txns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payer_tin: Mapped[str] = mapped_column(String(16), index=True)
    payee_tin: Mapped[str] = mapped_column(String(16), index=True)
    year: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)


class Financial(Base):
    __tablename__ = "financials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tin: Mapped[str] = mapped_column(String(16), index=True)
    year: Mapped[int] = mapped_column(Integer)
    turnover: Mapped[float] = mapped_column(Float)
    gross_margin: Mapped[float] = mapped_column(Float)
    gross_profit: Mapped[float] = mapped_column(Float)
    net_profit: Mapped[float] = mapped_column(Float)
    losses_carried_forward: Mapped[float] = mapped_column(Float)


class ExpatEngagement(Base):
    __tablename__ = "expat_engagements"
    person_ref: Mapped[str] = mapped_column(String(16), primary_key=True)
    engaging_tin: Mapped[str] = mapped_column(String(16))
    paying_tin: Mapped[str] = mapped_column(String(16))
    months: Mapped[int] = mapped_column(Integer)
    reports_to_local_mgmt: Mapped[int] = mapped_column(Integer)
    fixed_hours: Mapped[int] = mapped_column(Integer)
    uses_company_tools: Mapped[int] = mapped_column(Integer)
    declared_as: Mapped[str] = mapped_column(String(20))


class User(Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(40), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(24))  # refund_auditor, risk_analyst, special_sectors, taxpayer, admin
    password_hash: Mapped[str] = mapped_column(String(128))
    tin: Mapped[str | None] = mapped_column(String(16), nullable=True)  # taxpayer accounts


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(Integer, ForeignKey("claims.claim_id"), index=True)
    username: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(24))  # approve / request_documents / escalate
    comment: Mapped[str] = mapped_column(Text)
    requested_docs: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_lane: Mapped[str | None] = mapped_column(String(16), nullable=True)
    followed_recommendation: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FlagReview(Base):
    """Officer disposition of an individual flag (reviewed / not applicable / information required)."""
    __tablename__ = "flag_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    username: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
