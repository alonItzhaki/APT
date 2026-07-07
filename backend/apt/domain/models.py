from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Source = Literal["yad2", "facebook"]
Channel = Literal["telegram", "email"]


class Location(BaseModel):
    city: str
    neighborhood: str | None = None


class AlertFilters(BaseModel):
    locations: list[Location] = Field(default_factory=list)
    min_price: int | None = None
    max_price: int | None = None
    min_rooms: float | None = None
    max_rooms: float | None = None
    min_size_sqm: int | None = None
    min_floor: int | None = None
    max_floor: int | None = None
    require_mamad: bool = False
    require_elevator: bool = False
    entry_by: date | None = None


class Listing(BaseModel):
    source: Source
    source_id: str
    url: str
    city: str
    price: int | None = None
    neighborhood: str | None = None
    street: str | None = None
    rooms: float | None = None
    size_sqm: int | None = None
    floor: int | None = None
    has_mamad: bool | None = None
    has_elevator: bool | None = None
    entry_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    photo_urls: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"


class Alert(BaseModel):
    id: int
    user_id: int
    name: str
    filters: AlertFilters
    channels: list[Channel]
    active: bool = True


class User(BaseModel):
    id: int
    google_sub: str
    email: str
    telegram_chat_id: int | None = None
