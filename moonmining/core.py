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
    started_by: int = None

    def __post_init__(self):
        self.refinery_id = int(self.refinery_id)
        self.status = self.Status(self.status)
        if self.chunk_arrival_at:
            self.chunk_arrival_at = helpers.round_seconds(self.chunk_arrival_at)
        if self.auto_fracture_at:
            self.auto_fracture_at = helpers.round_seconds(self.auto_fracture_at)


@dataclass
class CalculatedExtractionProduct:
    """Product of an extraction calculated from moon mining notifications."""

    ore_type_id: int
    volume: float

    def __post_init__(self):
        self.ore_type_id = int(self.ore_type_id)

    @classmethod
    def create_list_from_dict(cls, ores: dict) -> List["CalculatedExtractionProduct"]:
        return [cls(ore_type_id, volume) for ore_type_id, volume in ores.items()]
