from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Stock(str, Enum):
    IN_STOCK = "Confirmed in stock"
    LIMITED = "Limited stock"
    OUT = "Out of stock"
    UNKNOWN = "Inventory status unknown"

    @property
    def available(self) -> bool:
        return self in (Stock.IN_STOCK, Stock.LIMITED)


@dataclass
class Hit:
    """One product at one physical store."""

    retailer: str
    store_id: str
    store_name: str
    address: str
    product_id: str
    product_name: str
    price: float | None
    status: Stock
    url: str
    quantity: int | None = None
    distance_mi: float | None = None
    lat: float | None = None
    lon: float | None = None
    availability_note: str = "In-store pickup available"

    @property
    def key(self) -> str:
        return f"{self.retailer}|{self.store_id}|{self.product_id}"
