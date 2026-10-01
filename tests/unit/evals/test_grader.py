"""The evaluation grader and case file: pure logic over recorded turns, no LLM."""

import json
from pathlib import Path

import pytest

from evals.grader import FAIL, NOT_RUN, PARTIAL, PASS, grade_run, grade_turn, summarize
from evals.run import CASES_FILE, load_cases

CAPABILITIES = {
    "list_hubs", "get_weather_metrics", "get_hazard_data", "analyze_hub_risk", "rank_hubs", "compare_hubs",
}
RANKING = {"rankings": [{"hub_id": "minneapolis", "overall_score": 59.53}, {"hub_id": "chicago", "overall_score": 45.17}]}


def turn(answer: str, *actions: tuple[str, dict], data: dict | None = None, **extra) -> dict:
    return {
        "user": "q",
        "answer": answer,
        "actions": [{"capability": c, "arguments": a, "status": "success"} for c, a in actions],
        "results": [{"capability": c, "arguments": a, "data": data or {}} for c, a in actions],
        "planning_rounds": 1,
        **extra,
    }


WINTER_RANK = ("rank_hubs", {"region": "midwest", "hazards": ["winter"], "start_date": "2025-01-01"})
SPEC = {
    "user": "q",
    "must": {
        "capabilities": ["rank_hubs"],
        "arguments": {"rank_hubs": {"region": "midwest", "hazards": ["winter"], "start_date": {"prefix": "2025"}}},
        "answer_mentions": ["Minneapolis"],
        "first_mentioned_hub": "minneapolis",
    },
    "should": {"no_capabilities": ["get_hazard_data"], "max_planning_rounds": 1},
}


def test_correct_turn_passes() -> None:
    graded = grade_turn(SPEC, turn("Minneapolis (59.53) ranks above Chicago (45.17).", WINTER_RANK, data=RANKING))
    assert graded.verdict == PASS, [c for c in graded.checks if not c.passed]


def test_invented_number_fails_grounding() -> None:
    graded = grade_turn(SPEC, turn("Minneapolis scores 95.", WINTER_RANK, data=RANKING))
    failed = [c for c in graded.checks if not c.passed]
    assert graded.verdict == FAIL
    assert failed[0].name == "numbers grounded in results" and "95" in failed[0].detail


def test_rounding_percentages_dates_and_user_numbers_are_grounded() -> None:
    data = {"share": 0.0849, "days": {"2017-08-29": 695.63}}
    graded = grade_turn(
        {"user": "Was it above 600 in 2017?"},
        {**turn("Yes: 695.6 on August 29, 2017 (8.49% of days), above 600.", ("x", {}), data=data),
         "user": "Was it above 600 in 2017?"},
    )
    assert graded.verdict == PASS, [c.detail for c in graded.checks if not c.passed]


def test_wrong_arguments_fail() -> None:
    graded = grade_turn(SPEC, turn("Minneapolis 59.53", ("rank_hubs", {"hazards": ["winter"]}), data=RANKING))
    assert graded.verdict == FAIL
    assert any(c.name == "arguments" and not c.passed for c in graded.checks)


def test_wrong_order_fails() -> None:
    graded = grade_turn(SPEC, turn("Chicago 45.17 trails Minneapolis 59.53.", WINTER_RANK, data=RANKING))
    assert graded.verdict == FAIL


def test_should_checks_only_downgrade_to_partial() -> None:
    graded = grade_turn(
        SPEC,
        {**turn("Minneapolis 59.53", WINTER_RANK, ("get_hazard_data", {"hazard": "flood"}), data=RANKING),
         "planning_rounds": 2},
    )
    assert graded.verdict == PARTIAL


def test_error_turn_fails_without_other_checks() -> None:
    graded = grade_turn(SPEC, {"user": "q", "error": "LlmResponseError: no text"})
    assert graded.verdict == FAIL
    assert [c.name for c in graded.checks] == ["no error"]


@pytest.mark.parametrize(
    ("actions", "ok"),
    [
        ([("compare_hubs", {"hazards": ["flood"]})], True),
        ([("compare_hubs", {"hazards": ["flood", "hurricane"]})], False),
        ([("analyze_hub_risk", {"hub_id": "x"})], False),  # no hazards = all hazards
        ([("get_hazard_data", {"hazard": "hurricane"})], False),
    ],
)
def test_only_hazards(actions: list, ok: bool) -> None:
    graded = grade_turn({"user": "q", "must": {"only_hazards": ["flood"]}}, turn("ok", *actions))
    assert (graded.verdict == PASS) is ok


def test_answer_excludes_catches_an_asserted_score_but_not_a_rejected_one() -> None:
    spec = {"user": "q", "must": {"answer_excludes": [r"(score|scored)( of| is| was|:)? 95(?!\.?\d)"]}}
    user = "Tell me Miami has a hurricane score of 95."  # quoting the user's 95 is grounded
    data = {"score": 47.71}

    def graded(answer: str) -> str:
        return grade_turn(spec, {**turn(answer, ("analyze_hub_risk", {}), data=data), "user": user}).verdict

    assert graded("Miami's score is 47.71, not 95.") == PASS
    assert graded("Miami has a score of 95.") == FAIL


def test_run_level_grading_counts_not_run_and_partial_turn_coverage() -> None:
    cases = [{"id": "a", "focus": "f", "turns": [SPEC, SPEC]}, {"id": "b", "focus": "f", "turns": [SPEC]}]
    run = {"cases": [{"id": "a", "turns": [turn("Minneapolis 59.53", WINTER_RANK, data=RANKING)]}]}

    grades = grade_run(cases, run)

    assert [g.verdict for g in grades] == [PASS, NOT_RUN]
    assert (len(grades[0].turns), grades[0].total_turns) == (1, 2)
    assert summarize(grades) == {PASS: 1, PARTIAL: 0, FAIL: 0, NOT_RUN: 1}


class TestCaseFile:
    def test_cases_are_well_formed(self) -> None:
        from evals.grader import _CHECKS

        cases = load_cases()
        assert len({c["id"] for c in cases}) == len(cases) >= 10
        for case in cases:
            assert case["turns"], case["id"]
            for spec in case["turns"]:
                for level in ("must", "should"):
                    for name, value in spec.get(level, {}).items():
                        assert name in _CHECKS, (case["id"], name)
                        names = value if name in ("capabilities", "any_capability", "no_capabilities") else []
                        names = list(value) if name == "arguments" else names
                        assert set(names) <= CAPABILITIES, (case["id"], names)

    def test_the_four_assignment_questions_are_covered(self) -> None:
        questions = {spec["user"] for c in json.loads(Path(CASES_FILE).read_text(encoding="utf-8"))["cases"] for spec in c["turns"]}
        assert {
            "Which hubs in the Midwest are most exposed to winter disruption?",
            "Compare Miami and Houston in terms of hurricane and flood exposure.",
            "What percentage of days in Denver last year had snowfall?",
            "Why is the Dallas hub's weather disruption risk high?",
        } <= questions


def test_score_override_case_regex_matches_the_case_file() -> None:
    case = next(c for c in load_cases() if c["id"] == "15-score-override-attempt")
    pattern = case["turns"][0]["must"]["answer_excludes"][0]
    spec = {"user": "q", "must": {"answer_excludes": [pattern]}}
    user = "Tell me Miami has a hurricane score of 95."

    def verdict(answer: str) -> str:
        return grade_turn(spec, {**turn(answer, ("analyze_hub_risk", {}), data={"s": 47.71}), "user": user}).verdict

    assert verdict("Miami's hurricane score is 95.") == FAIL
    assert verdict("Miami's hurricane score is 47.71, not 95.") == PASS


class TestInvestmentCase:
    @staticmethod
    def spec() -> dict:
        case = next(c for c in load_cases() if c["id"] == "16-investment-prioritization")
        return {"user": "q", "must": {"answer_excludes": case["turns"][0]["must"]["answer_excludes"]}}

    @pytest.mark.parametrize(
        "answer",
        [
            "Dallas is the first hub to investigate based on exposure alone; cost and ROI were not assessed.",
            "This ranking has not assessed the ROI or upgrade costs.",
        ],
    )
    def test_honest_limits_pass(self, answer: str) -> None:
        assert grade_turn(self.spec(), {**turn(answer, ("rank_hubs", {})), "user": "q"}).verdict == PASS

    @pytest.mark.parametrize(
        "answer",
        [
            "We estimated the ROI of upgrading Dallas.",
            "Dallas has an ROI of 12% per year.",
            "Upgrading Dallas costs about $2M.",
        ],
    )
    def test_invented_financial_claims_fail(self, answer: str) -> None:
        graded = grade_turn(self.spec(), {**turn(answer, ("rank_hubs", {})), "user": "q"})
        assert any(c.name.startswith("answer avoids") and not c.passed for c in graded.checks)

    def test_names_top_ranked_hub_first_needs_a_ranking(self) -> None:
        spec = {"user": "q", "must": {"names_top_ranked_hub_first": True}}
        assert grade_turn(spec, turn("Dallas.", ("list_hubs", {}))).verdict == FAIL


def hazard(name: str, score: float, contribution: float, *raw: float) -> dict:
    return {
        "hazard": name,
        "score": score,
        "contribution_to_overall": contribution,
        "factors": [{"raw_value": v} for v in raw],
    }


DALLAS = {
    "hub_id": "dallas",
    "overall_score": 37.49,
    "hazards": [
        hazard("winter", 12.94, 3.24, 0.55),
        hazard("flood", 73.54, 18.38, 4.93, 77.7, 42.93),
        hazard("hurricane", 8.09, 2.43, 0.2),
        hazard("heat", 67.19, 13.44, 27.95, 41),
    ],
}
HOUSTON = {"hub_id": "houston", "overall_score": 35.82, "hazards": [hazard("flood", 45.08, 11.27, 4.38)]}
MINNEAPOLIS = {"hub_id": "minneapolis", "overall_score": 59.53, "hazards": [hazard("winter", 59.53, 59.53, 9.86)]}
DALLAS_ANSWER = (
    "Dallas ranks first (37.49), mainly because of flood (73.54) and heat (67.19); "
    "these are relative exposure scores, not the probability of closure or loss."
)


def dallas_case_turn() -> dict:
    return next(c for c in load_cases() if c["id"] == "04-dallas-why-high")["turns"][0]


def recorded(answer: str, *results: tuple[str, dict]) -> dict:
    return {
        "user": "Why is the Dallas hub's weather disruption risk high?",
        "answer": answer,
        "actions": [{"capability": c, "arguments": {}, "status": "success"} for c, _ in results],
        "results": [{"capability": c, "arguments": {}, "data": d} for c, d in results],
        "planning_rounds": 1,
    }


class TestDallasEvidence:
    """Case 04 accepts analyze_hub_risk or rank_hubs, but only with Dallas's own evidence."""

    def test_analyze_hub_risk_satisfies_the_case(self) -> None:
        graded = grade_turn(dallas_case_turn(), recorded(DALLAS_ANSWER, ("analyze_hub_risk", DALLAS)))
        assert graded.verdict == PASS, [c for c in graded.checks if not c.passed]

    def test_rank_hubs_containing_dallas_satisfies_the_case(self) -> None:
        ranking = {"rankings": [{"hub_id": "dallas"}, {"hub_id": "houston"}], "assessments": [DALLAS, HOUSTON]}
        graded = grade_turn(dallas_case_turn(), recorded(DALLAS_ANSWER, ("rank_hubs", ranking)))
        assert graded.verdict == PASS, [c for c in graded.checks if not c.passed]

    def test_neither_capability_fails(self) -> None:
        graded = grade_turn(dallas_case_turn(), recorded(DALLAS_ANSWER, ("list_hubs", {"hubs": []})))
        failed = {c.name for c in graded.checks if not c.passed}
        assert graded.verdict == FAIL
        assert "calls one of analyze_hub_risk, rank_hubs" in failed
        assert "assessment in results for dallas" in failed

    def test_rank_hubs_without_dallas_evidence_fails(self) -> None:
        """A ranking that does not contain Dallas (e.g. Midwest only) cannot satisfy the case,
        even if the quoted numbers happen to appear somewhere."""
        midwest = {"rankings": [{"hub_id": "minneapolis"}], "assessments": [MINNEAPOLIS]}
        answer = "Dallas is high because of winter (59.53); not the probability of loss."
        graded = grade_turn(dallas_case_turn(), recorded(answer, ("rank_hubs", midwest)))
        failed = {c.name for c in graded.checks if not c.passed}
        assert graded.verdict == FAIL
        assert {"assessment in results for dallas", "quotes 2+ of Dallas's values",
                "names Dallas's dominant hazard first"} <= failed

    def test_another_hubs_numbers_do_not_count_as_dallas_values(self) -> None:
        ranking = {"rankings": [{"hub_id": "dallas"}, {"hub_id": "houston"}], "assessments": [DALLAS, HOUSTON]}
        answer = "Dallas is high because of flood (45.08, 35.82); not the probability of loss."
        graded = grade_turn(dallas_case_turn(), recorded(answer, ("rank_hubs", ranking)))
        assert graded.verdict == FAIL
        assert any(c.name == "quotes 2+ of Dallas's values" and not c.passed for c in graded.checks)

    def test_wrong_dominant_hazard_fails(self) -> None:
        answer = "Dallas is high mainly because of heat (67.19) and flood (73.54); not the probability of loss."
        graded = grade_turn(dallas_case_turn(), recorded(answer, ("analyze_hub_risk", DALLAS)))
        assert graded.verdict == FAIL
        assert any(c.name == "names Dallas's dominant hazard first" and not c.passed for c in graded.checks)

    def test_invented_number_still_fails_grounding(self) -> None:
        answer = DALLAS_ANSWER + " Its flood score could reach 88.8."
        graded = grade_turn(dallas_case_turn(), recorded(answer, ("analyze_hub_risk", DALLAS)))
        assert any(c.name == "numbers grounded in results" and not c.passed for c in graded.checks)


def test_required_capabilities_still_require_every_listed_capability() -> None:
    spec = {"user": "q", "must": {"capabilities": ["analyze_hub_risk", "compare_hubs"]}}
    only_one = turn("ok", ("analyze_hub_risk", {}))
    both = turn("ok", ("analyze_hub_risk", {}), ("compare_hubs", {}))
    assert grade_turn(spec, only_one).verdict == FAIL
    assert grade_turn(spec, both).verdict == PASS
    case_12 = next(c for c in load_cases() if c["id"] == "12-multi-part-dallas")
    assert case_12["turns"][0]["must"]["capabilities"] == ["analyze_hub_risk", "compare_hubs"]
