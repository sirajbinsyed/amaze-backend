from typing import Optional, Any, List
from pydantic import BaseModel

class LeadCreate(BaseModel):
    customer_name: str
    contact: Optional[str] = None
    details: Optional[str] = None
    measurements: Optional[dict] = None
    photos: Optional[list] = None
    delivery_date: Optional[str] = None  # ISO date

class LeadUpdate(BaseModel):
    customer_name: Optional[str] = None
    contact: Optional[str] = None
    details: Optional[str] = None
    measurements: Optional[dict] = None
    photos: Optional[list] = None
    delivery_date: Optional[str] = None
    status: Optional[str] = None  # 'lead' | 'confirmed'

class LeadPublic(BaseModel):
    id: int
    customer_name: str
    contact: Optional[str] = None
    status: str
    created_by: int
