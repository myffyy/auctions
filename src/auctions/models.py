from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auctions.database import Base


class AuctionStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class LotStatus(StrEnum):
    AVAILABLE = "available"
    SOLD = "sold"


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lots: Mapped[list[Lot]] = relationship(back_populates="seller")


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sales: Mapped[list[Sale]] = relationship(back_populates="buyer")


class Auction(Base):
    __tablename__ = "auctions"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="dates"),
        CheckConstraint("status IN ('planned', 'active', 'completed')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=AuctionStatus.PLANNED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lots: Mapped[list[Lot]] = relationship(back_populates="auction")


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        CheckConstraint("starting_price > 0", name="starting_price_positive"),
        CheckConstraint("status IN ('available', 'sold')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="RESTRICT"), index=True
    )
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    starting_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default=LotStatus.AVAILABLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    auction: Mapped[Auction] = relationship(back_populates="lots")
    seller: Mapped[Seller] = relationship(back_populates="lots")
    sale: Mapped[Sale | None] = relationship(back_populates="lot", uselist=False)


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (CheckConstraint("final_price > 0", name="final_price_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="RESTRICT"), unique=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id", ondelete="RESTRICT"), index=True)
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lot: Mapped[Lot] = relationship(back_populates="sale")
    buyer: Mapped[Buyer] = relationship(back_populates="sales")
    revenue: Mapped[Revenue] = relationship(back_populates="sale", uselist=False)


class Revenue(Base):
    __tablename__ = "revenues"
    __table_args__ = (
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 100",
            name="commission_rate_range",
        ),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), unique=True)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sale: Mapped[Sale] = relationship(back_populates="revenue")
