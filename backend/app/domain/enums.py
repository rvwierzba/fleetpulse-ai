"""Domain enumerations, SLA policies, and explicit state machine transitions."""

from enum import StrEnum


class DeviceType(StrEnum):
    """Supported corporate fleet device categories."""

    NOTEBOOK = "NOTEBOOK"
    SMARTPHONE = "SMARTPHONE"


class Subsystem(StrEnum):
    """Hardware and OS subsystems monitored by telemetry."""

    BATTERY_POWER = "BATTERY_POWER"
    STORAGE_NVME = "STORAGE_NVME"
    THERMAL_BOARD = "THERMAL_BOARD"
    FIRMWARE_OS = "FIRMWARE_OS"
    DISPLAY_PERIPHERAL = "DISPLAY_PERIPHERAL"


class SLATier(StrEnum):
    """Corporate SLA tiers determining response and resolution deadlines."""

    PLATINUM = "PLATINUM"
    GOLD = "GOLD"
    STANDARD = "STANDARD"


# Mapping from SLA tier to (first_response_hours, resolution_hours) per .agents/SPEC.md
SLA_TARGETS: dict[SLATier, tuple[int, int]] = {
    SLATier.PLATINUM: (4, 24),
    SLATier.GOLD: (8, 48),
    SLATier.STANDARD: (24, 72),
}


class AlertStatus(StrEnum):
    """Immutable lifecycle states of an ingested telemetry alert."""

    RECEIVED = "RECEIVED"
    DEDUPED = "DEDUPED"
    IGNORED_DUPLICATE = "IGNORED_DUPLICATE"
    ML_SCORED = "ML_SCORED"
    CONTEXT_RETRIEVED = "CONTEXT_RETRIEVED"
    AGENT_DIAGNOSED = "AGENT_DIAGNOSED"
    SCHEMA_VALIDATED = "SCHEMA_VALIDATED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    AUTO_RECOMMENDED = "AUTO_RECOMMENDED"
    RESOLVED = "RESOLVED"
    FAILED_DLQ = "FAILED_DLQ"


# Explicit state machine transition table (Architectural Invariant #2)
VALID_TRANSITIONS: dict[AlertStatus, frozenset[AlertStatus]] = {
    AlertStatus.RECEIVED: frozenset(
        {AlertStatus.DEDUPED, AlertStatus.IGNORED_DUPLICATE, AlertStatus.FAILED_DLQ}
    ),
    AlertStatus.DEDUPED: frozenset({AlertStatus.ML_SCORED, AlertStatus.FAILED_DLQ}),
    AlertStatus.ML_SCORED: frozenset({AlertStatus.CONTEXT_RETRIEVED, AlertStatus.FAILED_DLQ}),
    AlertStatus.CONTEXT_RETRIEVED: frozenset({AlertStatus.AGENT_DIAGNOSED, AlertStatus.FAILED_DLQ}),
    AlertStatus.AGENT_DIAGNOSED: frozenset({AlertStatus.SCHEMA_VALIDATED, AlertStatus.FAILED_DLQ}),
    AlertStatus.SCHEMA_VALIDATED: frozenset(
        {AlertStatus.HUMAN_REVIEW, AlertStatus.AUTO_RECOMMENDED, AlertStatus.FAILED_DLQ}
    ),
    AlertStatus.HUMAN_REVIEW: frozenset({AlertStatus.RESOLVED, AlertStatus.FAILED_DLQ}),
    AlertStatus.AUTO_RECOMMENDED: frozenset({AlertStatus.RESOLVED, AlertStatus.FAILED_DLQ}),
    AlertStatus.IGNORED_DUPLICATE: frozenset(),
    AlertStatus.RESOLVED: frozenset(),
    AlertStatus.FAILED_DLQ: frozenset({AlertStatus.RECEIVED}),
}


def can_transition(current: AlertStatus, target: AlertStatus) -> bool:
    """Return True when transitioning from current status to target status is allowed."""
    return target in VALID_TRANSITIONS[current]


def get_sla_targets(tier: SLATier) -> tuple[int, int]:
    """Return (first_response_hours, resolution_hours) for an SLA tier."""
    return SLA_TARGETS[tier]
