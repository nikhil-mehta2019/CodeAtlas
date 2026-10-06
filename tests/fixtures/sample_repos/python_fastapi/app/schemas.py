from enum import Enum

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    age: int = Field(default=0, ge=0, le=120)
