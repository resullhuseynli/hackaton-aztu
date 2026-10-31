from enum import StrEnum


class Direction(StrEnum):
    FORWARD = "forward"
    BACKWARD = "backward"

    @property
    def opposite(self) -> "Direction":
        return Direction.BACKWARD if self is Direction.FORWARD else Direction.FORWARD


class BusStatus(StrEnum):
    IN_SERVICE = "in_service"
    LAYOVER = "layover"     # waiting at the terminal before the next trip


class DensityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class AlertType(StrEnum):
    EXTRA_BUS_NEEDED = "extra_bus_needed"


class ReportSource(StrEnum):
    PASSENGER = "passenger"
    SIMULATED = "simulated"
