"""Score the team's versioned five-dimensional questionnaire on the server."""

import json
from collections import Counter
from fractions import Fraction
from math import floor
from pathlib import Path


BANK = json.loads(Path(__file__).with_name("question-bank.json").read_text(encoding="utf-8"))
VERSION = BANK["questionnaire_version"]
DIMENSIONS = {"FC": "财务承载力", "RA": "风险意愿", "KE": "认知与经验", "BD": "行为纪律", "OC": "目标与约束"}
WEIGHTS = dict(zip(DIMENSIONS, (35, 25, 15, 10, 15)))
QUESTIONS = {question["id"]: question for question in BANK["questions"]}
RISK_THRESHOLDS = (24, 44, 64, 79, 100)


class QuestionnaireError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def public_bank():
    return {"questionnaire_version": VERSION, "dimensions": DIMENSIONS, "questions": [
        {**item, "options": [{"key": row["key"], "text": row["text"]} for row in item["options"]]}
        for item in QUESTIONS.values()
    ]}


def _parse_answers(entries):
    if not isinstance(entries, list) or len(entries) > len(QUESTIONS):
        raise QuestionnaireError("invalid_answers", "Supply the questionnaire answer list")
    submitted, item_scores = {}, {}
    for row in entries:
        qid = row.get("qid") if isinstance(row, dict) else None
        if not isinstance(qid, str) or qid not in QUESTIONS or qid in submitted:
            raise QuestionnaireError("invalid_question", "Each question ID must appear at most once")
        question = QUESTIONS[qid]
        selected = row.get("value")
        keys = selected if question["multiple"] else [selected]
        key_scores = {option["key"]: option["score"] for option in question["options"]}
        if (not isinstance(keys, list) or not 1 <= len(keys) <= len(key_scores)
                or any(not isinstance(key, str) or key not in key_scores for key in keys)
                or len(set(keys)) != len(keys)):
            raise QuestionnaireError("invalid_option", f"Invalid selection for {qid}")
        submitted[qid] = selected if not question["multiple"] else tuple(sorted(keys))
        item_scores[qid] = max(key_scores[key] for key in keys)
    missing = QUESTIONS.keys() - submitted.keys()
    if missing:
        raise QuestionnaireError("incomplete", "Missing responses: " + ", ".join(sorted(missing)))
    return submitted, item_scores


def _quality_flags_and_confidence(answers, scores, raw_quality):
    if not isinstance(raw_quality, dict):
        raise QuestionnaireError("invalid_quality", "Quality signals must be an object")
    changes = raw_quality.get("answer_changes", 0)
    median = raw_quality.get("median_item_seconds")
    if type(changes) is not int or changes < 0:
        raise QuestionnaireError("invalid_quality", "answer_changes must be a nonnegative integer")
    if median is not None and (type(median) not in (int, float) or not 0 <= median <= 86400):
        raise QuestionnaireError("invalid_quality", "median_item_seconds is outside the supported range")
    ordered = [answers[qid] for qid in QUESTIONS]
    # The source defines straight-lining by consecutive identical selections.
    straight = sum(a == b for a, b in zip(ordered, ordered[1:])) * 5 > (len(ordered) - 1) * 4
    too_fast = median is not None and median < 3
    conflicts = sum((
        abs(scores["RA2"] - scores["RA6"]) >= 3,
        scores["RA3"] >= 4 and scores["BD2"] <= 2,
        scores["FC2"] >= 4 and scores["FC5"] <= 2,
        scores["OC2"] >= 4 and scores["OC3"] <= 2,
    ))
    flags = []
    if straight or too_fast:
        flags.append("LOW_ENGAGEMENT")
    if conflicts:
        flags.append("CONSISTENCY_WARNING")
    confidence = 100 - 15 * straight - 10 * too_fast - 10 * conflicts - 2 * min(changes, 3)
    return flags, max(0, confidence) / 100


def assess(payload):
    if payload.get("questionnaire_version") != VERSION:
        raise QuestionnaireError("questionnaire_version_mismatch", "Reload the current questionnaire")
    consent = payload.get("consent")
    if not isinstance(consent, dict) or consent.get("assessment") is not True or consent.get("ai_processing") is not True:
        raise QuestionnaireError("consent_required", "Confirm that the derived scores may be used for assessment and AI")
    answers, scores = _parse_answers(payload.get("answers"))

    totals = Counter()
    for qid, score in scores.items():
        totals[qid[:2]] += score
    normalized = {key: Fraction((totals[key] - 6) * 100, 24) for key in DIMENSIONS}
    base = sum(normalized[key] * weight / 100 for key, weight in WEIGHTS.items())
    cap = min(100, normalized["FC"] + 20)
    flagged_caps = {
        "LIQUIDITY_BUFFER_LOW": (scores["FC5"] <= 2, 64),
        "NEAR_TERM_LARGE_EXPENSE": (answers["FC6"] == "A", 55),
        "LEVERAGE_USE": (scores["OC5"] <= 2, 44),
        "SHORT_HORIZON": (answers["OC2"] == "A" or answers["OC3"] == "A", 44),
        "KNOWLEDGE_GAP": (normalized["KE"] < 25, 64),
        "BEHAVIOR_RISK": (normalized["BD"] < 30, 64),
    }
    flags = []
    for code, (active, ceiling) in flagged_caps.items():
        if active:
            flags.append(code)
            cap = min(cap, ceiling)
    if normalized["RA"] - normalized["FC"] >= 20:
        flags.append("CAPACITY_WILLINGNESS_GAP")
    if scores["BD3"] <= 2:
        flags.append("OVERCONFIDENCE")
    context = payload.get("context", {})
    if not isinstance(context, dict):
        raise QuestionnaireError("invalid_context", "Optional context must be an object")
    expected_return = context.get("expected_return_pct")
    if expected_return is not None:
        if type(expected_return) not in (int, float) or not 0 <= expected_return <= 100:
            raise QuestionnaireError("invalid_context", "expected_return_pct must be between 0 and 100")
        if expected_return > 12 and normalized["FC"] < 40:
            flags.append("RETURN_EXPECTATION_GAP")
    quality_flags, confidence = _quality_flags_and_confidence(answers, scores, payload.get("quality_signals", {}))
    flags.extend(quality_flags)
    if confidence < 0.5:
        raise QuestionnaireError("provisional", "Please review and complete a new assessment")
    rai = floor(min(base, cap) + Fraction(1, 2))
    level = next(i for i, maximum in enumerate(RISK_THRESHOLDS, 1) if rai <= maximum)
    wealth_band = {"A": "low", "B": "low", "C": "medium", "D": "high", "E": "high"}[answers["FC2"]]
    return {
        "questionnaire_version": VERSION,
        "source": "questionnaire",
        "dimensions": {"wealth_band": wealth_band},
        "assessment": {"dimensions": {key: round(float(value), 2) for key, value in normalized.items()},
                       "rai": rai, "risk_level": f"C{level}", "product_cap": f"R{level}",
                       "flags": flags, "confidence": confidence},
    }
