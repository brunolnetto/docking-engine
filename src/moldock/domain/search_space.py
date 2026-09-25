from __future__ import annotations

from dataclasses import dataclass
import math

from .common import DomainValidationError, content_id


@dataclass(frozen=True, slots=True)
class DockingBox:
    center_x: float
    center_y: float
    center_z: float
    size_x: float
    size_y: float
    size_z: float

    def __post_init__(self) -> None:
        for axis, value in {
            "center_x": self.center_x,
            "center_y": self.center_y,
            "center_z": self.center_z,
        }.items():
            if not math.isfinite(value):
                raise DomainValidationError(f"{axis} must be finite")

        for axis, value in {
            "size_x": self.size_x,
            "size_y": self.size_y,
            "size_z": self.size_z,
        }.items():
            if not math.isfinite(value) or value <= 0:
                raise DomainValidationError(f"{axis} must be finite and > 0")

    @property
    def search_space_id(self) -> str:
        return content_id(
            "space",
            {
                "type": "box",
                "center": [self.center_x, self.center_y, self.center_z],
                "size": [self.size_x, self.size_y, self.size_z],
            },
        )
