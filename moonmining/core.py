import datetime as dt
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import List

from . import helpers


@dataclass
class CalculatedExtraction:
    """An extraction calculated from moon mining notifications."""

    class Status(IntEnum):
        STARTED = auto()
        CANCELED = auto()
        READY = auto()
        COMPLETED = auto()
        UNDEFINED = auto()

    refinery_id: int
    status: Status
    auto_fracture_at: dt.datetime = None
    canceled_at: dt.datetime = None
    canceled_by: int = None
    chunk_arrival_at: dt.datetime = None
    fractured_at: dt.datetime = None
    fractured_by: int = None
    products: List["CalculatedExtractionProduct"] = None
    started_at: dt.datetime = None
    started_by: int = None

    def __post_init__(self):
        self.refinery_id = int(self.refinery_id)
        self.status = self.Status(self.status)
        if self.started_at:
            self.started_at = helpers.round_seconds(self.started_at)
        if self.chunk_arrival_at:
            self.chunk_arrival_at = helpers.round_seconds(self.chunk_arrival_at)
        if self.auto_fracture_at:
            self.auto_fracture_at = helpers.round_seconds(self.auto_fracture_at)

    @property
    def duration(self) -> dt.timedelta:
        if self.chunk_arrival_at and self.started_at:
            return self.chunk_arrival_at - self.started_at
        raise ValueError("chunk_arrival_at and/or started_at not defined")

    def total_volume(self) -> float:
        if not self.products:
            return 0
        total = 0.0
        for product in self.products:
            total += product.volume
        return total

    def moon_products_estimated(
        self, volume_per_day: float
    ) -> List["CalculatedMoonProduct"]:
        """List of products with estimated amounts."""
        duration_in_days = self.duration.total_seconds() / (60 * 60 * 24)
        if duration_in_days <= 0:
            raise ValueError("Can not estimate products without duration.")
        max_volume = duration_in_days * volume_per_day
        correction_factor = max(1, self.total_volume() / max_volume)
        products = [
            CalculatedMoonProduct(
                ore_type_id=product.ore_type_id,
                amount=product.calculated_share(duration_in_days, volume_per_day)
                / correction_factor,
            )
            for product in self.products
        ]
        return products


@dataclass
class CalculatedExtractionProduct:
    """Product of an extraction calculated from moon mining notifications."""

    ore_type_id: int
    volume: float

    def __post_init__(self):
        self.ore_type_id = int(self.ore_type_id)

    def calculated_share(self, duration_in_days: float, volume_per_day: float) -> float:
        """Calculate share of these moon products"""
        return self.volume / (duration_in_days * volume_per_day)

    @classmethod
    def create_list_from_dict(cls, ores: dict) -> List["CalculatedExtractionProduct"]:
        return [cls(ore_type_id, volume) for ore_type_id, volume in ores.items()]


@dataclass
class CalculatedMoonProduct:
    """Product of an extraction calculated from moon mining notifications."""

    ore_type_id: int
    amount: float

    def __post_init__(self):
        self.ore_type_id = int(self.ore_type_id)
