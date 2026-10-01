"""Grades a recorded evaluation run against evals/cases.json. Pure functions, no I/O, no LLM.

A recorded turn looks like:
    {"user": str, "session_id": str, "error": str | None, "answer": str,
     "actions": [{"capability", "arguments", "status"}],
     "results": [{"capability", "arguments", "data"}],
     "planning_rounds": int, "llm_calls": int}

Every turn is also checked automatically for:
- no error (the API would have returned 5xx otherwise);
- grounding: every number in the answer must appear in that turn's capability results (or in
  the user's own message). Small rounding is accepted; nothing else is.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

PASS, PARTIAL, FAIL, NOT_RUN = "PASS", "PARTIAL", "FAIL", "NOT RUN"

HUB_NAMES = {
    "chicago": "Chicago",
    "dallas": "Dallas",
    "denver": "Denver",
    "houston": "Houston",
    "miami": "Miami",
    "minneapolis": "Minneapolis",
}
SCORING_CAPABILITIES = ("analyze_hub_risk", "rank_hubs", "compare_hubs")
HAZARD_WORDS = {
    "winter": r"\b(winter|snow\w*|cold)\b",
    "flood": r"\b(flood\w*|river|heavy rain\w*|precipitation)\b",
    "hurricane": r"\b(hurricane\w*|tropical|cyclone\w*|storms?)\b",
    "heat": r"\b(heat|hot)\b",
}
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


@dataclass(frozen=True)
class Check:
    name: str
    level: str  # "must" | "should"
    passed: bool
    detail: str = ""


@dataclass
class TurnGrade:
    user: str
    checks: list[Check] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return _verdict(self.checks)


@dataclass
class CaseGrade:
    case_id: str
    focus: str
    turns: list[TurnGrade]
    ran: bool = True
    total_turns: int = 0
    """Turns the case defines; a partial run (e.g. a regression subset) grades fewer."""

    @property
    def verdict(self) -> str:
        if not self.ran:
            return NOT_RUN
        return _verdict([c for t in self.turns for c in t.checks])


def grade_run(cases: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> list[CaseGrade]:
    recorded = {c["id"]: c for c in run.get("cases", [])}
    grades = []
    for case in cases:
        record = recorded.get(case["id"])
        if record is None:
            grades.append(CaseGrade(case["id"], case["focus"], [], ran=False))
            continue
        recorded_turns = record["turns"][: len(case["turns"])]
        turns = [grade_turn(spec, turn) for spec, turn in zip(case["turns"], recorded_turns, strict=False)]
        grades.append(CaseGrade(case["id"], case["focus"], turns, total_turns=len(case["turns"])))
    return grades


def grade_turn(spec: Mapping[str, Any], turn: Mapping[str, Any]) -> TurnGrade:
    grade = TurnGrade(spec["user"])
    error = turn.get("error")
    grade.checks.append(Check("no error", "must", not error, error or ""))
    if error:
        return grade
    grade.checks.append(_grounding(turn))
    for level in ("must", "should"):
        for name, expected in spec.get(level, {}).items():
            grade.checks.append(_CHECKS[name](level, expected, turn))
    return grade


def summarize(grades: Iterable[CaseGrade]) -> dict[str, int]:
    counts = {PASS: 0, PARTIAL: 0, FAIL: 0, NOT_RUN: 0}
    for g in grades:
        counts[g.verdict] += 1
    return counts


# --- checks ------------------------------------------------------------------------------


def _capabilities(level: str, expected: list[str], turn: Mapping[str, Any]) -> Check:
    called = _executed(turn)
    missing = [c for c in expected if c not in called]
    return Check("calls " + ", ".join(expected), level, not missing, _called_detail(called, missing))


def _any_capability(level: str, expected: list[str], turn: Mapping[str, Any]) -> Check:
    called = _executed(turn)
    ok = any(c in called for c in expected)
    return Check("calls one of " + ", ".join(expected), level, ok, f"called: {sorted(called) or 'nothing'}")


def _no_capabilities(level: str, forbidden: list[str], turn: Mapping[str, Any]) -> Check:
    called = _executed(turn)
    extra = sorted(c for c in forbidden if c in called)
    return Check("does not call " + ", ".join(forbidden), level, not extra, f"called: {extra}" if extra else "")


def _arguments(level: str, expected: Mapping[str, Mapping[str, Any]], turn: Mapping[str, Any]) -> Check:
    problems = []
    for capability, wanted in expected.items():
        calls = [a["arguments"] for a in turn.get("actions", []) if a["capability"] == capability]
        if not calls:
            problems.append(f"{capability} not called")
        elif not any(_arguments_match(args, wanted) for args in calls):
            problems.append(f"{capability} arguments {calls} do not match {dict(wanted)}")
    return Check("arguments", level, not problems, "; ".join(problems))


def _only_hazards(level: str, allowed: list[str], turn: Mapping[str, Any]) -> Check:
    problems = []
    for action in turn.get("actions", []):
        args, capability = action["arguments"], action["capability"]
        if capability in SCORING_CAPABILITIES:
            hazards = args.get("hazards")
            if not hazards:
                problems.append(f"{capability} scores all hazards")
            elif set(hazards) - set(allowed):
                problems.append(f"{capability} hazards {hazards}")
        elif capability == "get_hazard_data" and args.get("hazard") not in allowed:
            problems.append(f"get_hazard_data hazard {args.get('hazard')}")
    return Check("only hazards " + ", ".join(allowed), level, not problems, "; ".join(problems))


def _answer_mentions(level: str, patterns: list[str], turn: Mapping[str, Any]) -> Check:
    answer = turn.get("answer", "")
    missing = [p for p in patterns if not re.search(p, answer, re.IGNORECASE)]
    return Check("answer mentions " + " / ".join(patterns), level, not missing, f"missing: {missing}" if missing else "")


def _answer_excludes(level: str, patterns: list[str], turn: Mapping[str, Any]) -> Check:
    answer = turn.get("answer", "")
    found = [p for p in patterns if re.search(p, answer, re.IGNORECASE)]
    return Check("answer avoids " + " / ".join(patterns), level, not found, f"found: {found}" if found else "")


def _first_mentioned_hub(level: str, hub_id: str, turn: Mapping[str, Any]) -> Check:
    answer = turn.get("answer", "")
    positions = {h: answer.find(name) for h, name in HUB_NAMES.items() if name in answer}
    first = min(positions, key=positions.__getitem__) if positions else None
    return Check(f"names {HUB_NAMES[hub_id]} first", level, first == hub_id, f"first named: {first}")


def _names_top_ranked_hub_first(level: str, expected: bool, turn: Mapping[str, Any]) -> Check:
    """The first hub named in the answer is #1 in this turn's deterministic ranking."""
    rankings = [
        r["data"].get("rankings") for r in turn.get("results", []) if r["capability"] == "rank_hubs"
    ]
    if not rankings or not rankings[0]:
        return Check("names the top-ranked hub first", level, False, "no rank_hubs result")
    top = rankings[0][0]["hub_id"]
    answer = turn.get("answer", "")
    positions = {h: answer.find(name) for h, name in HUB_NAMES.items() if name in answer}
    first = min(positions, key=positions.__getitem__) if positions else None
    return Check("names the top-ranked hub first", level, first == top, f"ranking #1: {top}; first named: {first}")


def _hub_evidence(level: str, hub_ids: list[str], turn: Mapping[str, Any]) -> Check:
    """Each hub's full deterministic assessment is in this turn's results (from
    analyze_hub_risk, or inside a rank_hubs / compare_hubs result)."""
    missing = [h for h in hub_ids if _assessment(turn, h) is None]
    return Check("assessment in results for " + ", ".join(hub_ids), level, not missing, f"missing: {missing}" if missing else "")


def _quotes_hub_values(level: str, expected: Mapping[str, Any], turn: Mapping[str, Any]) -> Check:
    """The answer quotes at least ``min`` values (overall/hazard scores, contributions, factor
    values) from that hub's own assessment, so the grounded numbers belong to the right hub."""
    hub_id, minimum = expected["hub_id"], expected.get("min", 1)
    assessment = _assessment(turn, hub_id)
    name = f"quotes {minimum}+ of {HUB_NAMES.get(hub_id, hub_id)}'s values"
    if assessment is None:
        return Check(name, level, False, f"no assessment for {hub_id}")
    values: list[float] = []
    for hazard in assessment.get("hazards", []):
        values += [hazard.get("score"), hazard.get("contribution_to_overall")]
        for factor in hazard.get("factors", []):
            values.append(factor.get("raw_value"))
    values = [float(v) for v in [assessment.get("overall_score"), *values] if isinstance(v, (int, float))]
    tokens = _NUMBER.findall(turn.get("answer", ""))
    quoted = {t for t in tokens if float(t) != 0 and _matches(t, values)}
    return Check(name, level, len(quoted) >= minimum, f"matched: {sorted(quoted)}")


def _names_dominant_hazard_first(level: str, hub_id: str, turn: Mapping[str, Any]) -> Check:
    """The first hazard the answer names is the one contributing most to the hub's score."""
    name = f"names {HUB_NAMES.get(hub_id, hub_id)}'s dominant hazard first"
    assessment = _assessment(turn, hub_id)
    if assessment is None or not assessment.get("hazards"):
        return Check(name, level, False, f"no assessment for {hub_id}")
    dominant = max(assessment["hazards"], key=lambda h: h.get("contribution_to_overall") or 0)["hazard"]
    answer = turn.get("answer", "").lower()
    found = {h: m.start() for h in HAZARD_WORDS if (m := re.search(HAZARD_WORDS[h], answer))}
    first = min(found, key=found.__getitem__) if found else None
    return Check(name, level, first == dominant, f"dominant: {dominant}; first named: {first}")


def _max_planning_rounds(level: str, limit: int, turn: Mapping[str, Any]) -> Check:
    rounds = turn.get("planning_rounds", 0)
    return Check(f"at most {limit} planning round(s)", level, rounds <= limit, f"rounds: {rounds}")


_CHECKS = {
    "capabilities": _capabilities,
    "any_capability": _any_capability,
    "no_capabilities": _no_capabilities,
    "arguments": _arguments,
    "only_hazards": _only_hazards,
    "answer_mentions": _answer_mentions,
    "answer_excludes": _answer_excludes,
    "first_mentioned_hub": _first_mentioned_hub,
    "max_planning_rounds": _max_planning_rounds,
    "names_top_ranked_hub_first": _names_top_ranked_hub_first,
    "hub_evidence": _hub_evidence,
    "quotes_hub_values": _quotes_hub_values,
    "names_dominant_hazard_first": _names_dominant_hazard_first,
}


# --- grounding ---------------------------------------------------------------------------


def _grounding(turn: Mapping[str, Any]) -> Check:
    values: list[float] = []
    for result in turn.get("results", []):
        _collect_numbers(result.get("data"), values)
        _collect_numbers(result.get("arguments"), values)
    _collect_numbers(turn.get("user", ""), values)
    answer = turn.get("answer", "")
    unmatched = [n for n in _NUMBER.findall(answer) if not _matches(n, values)]
    detail = f"numbers not found in results: {unmatched}" if unmatched else ""
    return Check("numbers grounded in results", "must", not unmatched, detail)


def _collect_numbers(value: Any, out: list[float]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _collect_numbers(str(key), out)
            _collect_numbers(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_numbers(item, out)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        for year, month, day in _ISO_DATE.findall(value):
            out.extend((float(year), float(month), float(day)))
        out.extend(float(n) for n in _NUMBER.findall(_ISO_DATE.sub(" ", value)))


def _matches(token: str, values: Sequence[float]) -> bool:
    number = abs(float(token))
    decimals = len(token.split(".")[1]) if "." in token else 0
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return any(
        abs(abs(v) - number) <= tolerance or abs(abs(v) * 100 - number) <= tolerance
        for v in values
    )


# --- helpers -----------------------------------------------------------------------------


def _assessment(turn: Mapping[str, Any], hub_id: str) -> Mapping[str, Any] | None:
    for result in turn.get("results", []):
        data = result.get("data") or {}
        candidates = [data] if result["capability"] == "analyze_hub_risk" else data.get("assessments", [])
        for assessment in candidates:
            if assessment.get("hub_id") == hub_id and assessment.get("hazards"):
                return assessment
    return None


def _executed(turn: Mapping[str, Any]) -> set[str]:
    return {a["capability"] for a in turn.get("actions", []) if a.get("status") == "success"}


def _called_detail(called: set[str], missing: list[str]) -> str:
    return f"missing: {missing}; called: {sorted(called) or 'nothing'}" if missing else ""


def _arguments_match(actual: Mapping[str, Any], wanted: Mapping[str, Any]) -> bool:
    for key, expected in wanted.items():
        value = actual.get(key)
        if isinstance(expected, Mapping) and "prefix" in expected:
            if not str(value or "").startswith(expected["prefix"]):
                return False
        elif isinstance(expected, list):
            if not isinstance(value, list) or sorted(map(str, value)) != sorted(map(str, expected)):
                return False
        elif value != expected:
            return False
    return True


def _verdict(checks: Sequence[Check]) -> str:
    if any(not c.passed and c.level == "must" for c in checks):
        return FAIL
    if any(not c.passed for c in checks):
        return PARTIAL
    return PASS
