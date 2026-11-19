"""Normalize questionnaire scores and persist the latest profile per user."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Literal, cast


Level = Literal["low", "medium", "high"]
RiskLevel = Literal["C1", "C2", "C3", "C4", "C5"]
Route = Literal["clarify", "education", "advisory"]
LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}
DIMENSION_NAMES = ("risk_willingness", "risk_capacity", "wealth_band", "knowledge_level")
REQUIRED_DIMENSIONS = ("risk_willingness", "risk_capacity", "knowledge_level")
METADATA_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
ASSESSMENT_DIMENSIONS = ("FC", "RA", "KE", "BD", "OC")
RISK_THRESHOLDS = ((24, "C1"), (44, "C2"), (64, "C3"), (79, "C4"), (100, "C5"))
EDUCATION_KE_THRESHOLD = 45


class ProfileValidationError(ValueError):
    """The user identifier or questionnaire contains an invalid value."""


@dataclass(frozen=True)
class Assessment:
    dimensions: dict[str, int | float]
    rai: int
    risk_level: RiskLevel
    product_cap: str
    allocation_range: dict[str, int | float] | None
    flags: tuple[str, ...]
    prohibitions: tuple[str, ...]
    confidence: int | float | None = None

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        result["prohibitions"] = list(self.prohibitions)
        if self.confidence is None:
            result.pop("confidence")
        return result


@dataclass(frozen=True)
class Profile:
    user_id: str
    risk_willingness: Level | None
    risk_capacity: Level | None
    wealth_band: Level | None
    knowledge_level: Level | None
    risk_ceiling: Level | RiskLevel | None
    route: Route
    reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]
    questionnaire_version: str
    source: str
    updated_at: str
    assessment: Assessment | None = None

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        result["missing_fields"] = list(self.missing_fields)
        if self.assessment is None:
            result.pop("assessment")
        else:
            result["assessment"] = self.assessment.as_dict()
        return result


def _validate_user_id(user_id: str) -> None:
    if (
        not isinstance(user_id, str)
        or not 1 <= len(user_id) <= 128
        or user_id != user_id.strip()
        or not user_id.isprintable()
    ):
        raise ProfileValidationError("user_id must contain 1 to 128 printable characters")


def _read_level(dimensions: Mapping[str, object], name: str) -> Level | None:
    value = dimensions.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or value not in LEVEL_ORDER:
        raise ProfileValidationError(f"{name} must be low, medium, high, or null")
    return cast(Level, value)


def _read_metadata(questionnaire: Mapping[str, object], name: str, default: str) -> str:
    value = questionnaire.get(name)
    if value is None:
        return default
    if not isinstance(value, str) or not METADATA_TOKEN.fullmatch(value):
        raise ProfileValidationError(f"{name} must be a token of up to 64 characters")
    return value


def _read_score(value: object, name: str) -> int | float:
    if type(value) not in (int, float) or not 0 <= value <= 100 or not math.isfinite(value):
        raise ProfileValidationError(f"{name} must be a number from 0 to 100")
    return value


def _read_codes(assessment: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = assessment.get(name, [])
    if not isinstance(value, list) or len(value) > 16 or any(
        not isinstance(code, str) or not METADATA_TOKEN.fullmatch(code) for code in value
    ):
        raise ProfileValidationError(f"{name} must contain up to 16 codes of at most 64 characters")
    return tuple(dict.fromkeys(value))


def _read_assessment(value: object) -> Assessment:
    if not isinstance(value, Mapping):
        raise ProfileValidationError("assessment must be an object")
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise ProfileValidationError("assessment must contain a dimensions object")
    scores = {name: _read_score(dimensions.get(name), f"assessment.dimensions.{name}")
              for name in ASSESSMENT_DIMENSIONS}
    rai = value.get("rai")
    if type(rai) is not int or not 0 <= rai <= 100:
        raise ProfileValidationError("assessment.rai must be an integer from 0 to 100")
    if rai > math.floor(scores["FC"] + 20.5):
        raise ProfileValidationError("assessment.rai exceeds the financial-capacity ceiling")
    risk_level = next(level for maximum, level in RISK_THRESHOLDS if rai <= maximum)
    product_cap = f"R{risk_level[1]}"
    if value.get("risk_level") != risk_level or value.get("product_cap") != product_cap:
        raise ProfileValidationError("assessment risk_level and product_cap must agree with rai")

    allocation = value.get("allocation_range")
    if allocation is not None:
        if not isinstance(allocation, Mapping):
            raise ProfileValidationError("allocation_range must be an object or null")
        minimum = _read_score(allocation.get("min_pct"), "allocation_range.min_pct")
        maximum = _read_score(allocation.get("max_pct"), "allocation_range.max_pct")
        if minimum > maximum:
            raise ProfileValidationError("allocation_range.min_pct must not exceed max_pct")
        allocation = {"min_pct": minimum, "max_pct": maximum}

    confidence = value.get("confidence")
    if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 1):
        raise ProfileValidationError("assessment.confidence must be between 0 and 1")
    return Assessment(scores, rai, cast(RiskLevel, risk_level), product_cap, allocation,
                      _read_codes(value, "flags"), _read_codes(value, "prohibitions"), confidence)


def normalize_profile(user_id: str, questionnaire: Mapping[str, object]) -> Profile:
    """Read allowlisted, pre-scored dimensions from an upstream questionnaire."""
    _validate_user_id(user_id)
    if not isinstance(questionnaire, Mapping):
        raise ProfileValidationError("questionnaire must be an object")
    dimensions = questionnaire.get("dimensions")
    if dimensions is None:
        dimensions = {}
    if not isinstance(dimensions, Mapping):
        raise ProfileValidationError("dimensions must be an object or null")

    if "assessment" in questionnaire:
        assessment = _read_assessment(questionnaire["assessment"])
        if "LEVERAGE_USE" in assessment.flags:
            route, reason = "clarify", "review_leverage_use"
        elif assessment.confidence is not None and assessment.confidence < 0.7:
            route, reason = "clarify", "review_assessment_confidence"
        elif assessment.dimensions["KE"] < EDUCATION_KE_THRESHOLD:
            route, reason = "education", "education_for_low_ke"
        else:
            route, reason = "advisory", "ke_allows_advisory"
        return Profile(
            user_id=user_id,
            risk_willingness=None,
            risk_capacity=None,
            wealth_band=_read_level(dimensions, "wealth_band"),
            knowledge_level=None,
            risk_ceiling=assessment.risk_level,
            route=route,
            reasons=("assessment_risk_level_verified", reason),
            missing_fields=(),
            questionnaire_version=_read_metadata(questionnaire, "questionnaire_version", "1.0.0"),
            source=_read_metadata(questionnaire, "source", "questionnaire"),
            updated_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            assessment=assessment,
        )

    levels = {name: _read_level(dimensions, name) for name in DIMENSION_NAMES}
    willingness = levels["risk_willingness"]
    capacity = levels["risk_capacity"]
    knowledge = levels["knowledge_level"]
    risk_ceiling = None
    reasons = []
    if willingness is not None and capacity is not None:
        risk_ceiling = min(willingness, capacity, key=LEVEL_ORDER.__getitem__)
        if willingness == capacity:
            reasons.append("risk_dimensions_aligned")
        elif risk_ceiling == capacity:
            reasons.append("risk_capacity_limits_ceiling")
        else:
            reasons.append("risk_willingness_limits_ceiling")

    missing_fields = tuple(name for name in DIMENSION_NAMES if levels[name] is None)
    missing_required = [name for name in REQUIRED_DIMENSIONS if levels[name] is None]
    route: Route
    if missing_required:
        route = "clarify"
        reasons.extend(f"missing_{name}" for name in missing_required)
    elif knowledge == "low":
        route = "education"
        reasons.append("education_for_low_knowledge")
    else:
        route = "advisory"
        reasons.append("knowledge_allows_advisory")

    return Profile(
        user_id=user_id,
        risk_willingness=willingness,
        risk_capacity=capacity,
        wealth_band=levels["wealth_band"],
        knowledge_level=knowledge,
        risk_ceiling=risk_ceiling,
        route=route,
        reasons=tuple(reasons),
        missing_fields=missing_fields,
        questionnaire_version=_read_metadata(questionnaire, "questionnaire_version", "unspecified"),
        source=_read_metadata(questionnaire, "source", "questionnaire"),
        updated_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    )


class ProfileStore:
    """A file-backed SQLite store with a separate connection for each operation."""

    def __init__(self, db_path: str | Path) -> None:
        if str(db_path) == ":memory:":
            raise ValueError("ProfileStore requires a SQLite file path")
        self.db_path = Path(db_path).resolve()
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS profiles ("
                "user_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL)"
            )

    def upsert(self, user_id: str, questionnaire: Mapping[str, object]) -> Profile:
        profile = normalize_profile(user_id, questionnaire)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute(
                "INSERT INTO profiles (user_id, profile_json) VALUES (?, ?) "
                "ON CONFLICT (user_id) DO UPDATE SET profile_json = excluded.profile_json",
                (user_id, json.dumps(profile.as_dict(), ensure_ascii=False)),
            )
        return profile

    def get(self, user_id: str) -> Profile | None:
        _validate_user_id(user_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        record = json.loads(row[0])
        record["reasons"] = tuple(record["reasons"])
        record["missing_fields"] = tuple(record["missing_fields"])
        assessment = record.get("assessment")
        if assessment is not None:
            assessment["flags"] = tuple(assessment["flags"])
            assessment["prohibitions"] = tuple(assessment["prohibitions"])
            record["assessment"] = Assessment(**assessment)
        return Profile(**record)
