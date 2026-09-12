from datetime import UTC, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from auctions.models import AuctionStatus, LotStatus


class ApiModel(BaseModel):
    """Общие правила проверки схем API."""

    model_config = ConfigDict(str_strip_whitespace=True)


class SellerCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class SellerRead(SellerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class BuyerCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class BuyerRead(BuyerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class AuctionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        """Потребовать часовой пояс и привести время к UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("дата и время должны содержать часовой пояс")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Проверить порядок дат аукциона."""

        if self.ends_at <= self.starts_at:
            raise ValueError("дата окончания должна быть позже даты начала")
        return self


class AuctionRead(AuctionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: AuctionStatus
    created_at: datetime


class LotCreate(ApiModel):
    auction_id: int = Field(gt=0)
    seller_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    starting_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class LotRead(LotCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: LotStatus
    created_at: datetime
