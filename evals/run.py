"""Evaluation runner.

    uv run python -m evals.run                    # grade the latest recorded run (offline, no LLM)
    uv run python -m evals.run --grade FILE       # grade a specific recorded run (offline)
    uv run python -m evals.run --live             # run every case against the real LLM, record, grade
    uv run python -m evals.run --live --cases 01-midwest-winter-ranking,13-unsupported-hazard-earthquake

Grading never calls an LLM. ``--live`` uses the configured provider (.env) and the real public
data APIs, prints how many LLM calls to expect, and writes evals/runs/<timestamp>-<model>.json.
Exit code: 0 if no case FAILs, 1 otherwise.
"""

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evals.grader import FAIL, NOT_RUN, CaseGrade, grade_run, summarize

EVALS_DIR = Path(__file__).parent
CASES_FILE = EVALS_DIR / "cases.json"
RUNS_DIR = EVALS_DIR / "runs"


def load_cases(selected: Sequence[str] = ()) -> list[dict[str, Any]]:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    if selected:
        unknown = set(selected) - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in selected]
    return cases


def latest_run() -> Path:
    runs = sorted(RUNS_DIR.glob("*.json"))
    if not runs:
        raise SystemExit("No recorded runs in evals/runs/. Record one with --live.")
    return runs[-1]


def report(grades: Sequence[CaseGrade], run: dict[str, Any], source: str) -> str:
    meta = run.get("meta", {})
    lines = [
        f"# Evaluation report: {source}",
        "",
        f"Model: {meta.get('provider', '?')} / {meta.get('model', '?')} (effort {meta.get('effort', '?')}). "
        f"Recorded {meta.get('recorded_at', '?')}. {meta.get('note', '')}".rstrip(),
        "",
        "| Case | Focus | Verdict | Failed checks |",
        "|---|---|---|---|",
    ]
    for g in grades:
        failed = [
            f"T{i}: {c.name}" + (f" ({c.detail})" if c.detail else "") + ("" if c.level == "must" else " [should]")
            for i, t in enumerate(g.turns, 1)
            for c in t.checks
            if not c.passed
        ]
        partial = f" ({len(g.turns)}/{g.total_turns} turns)" if g.ran and len(g.turns) < g.total_turns else ""
        lines.append(f"| {g.case_id} | {g.focus} | **{g.verdict}**{partial} | {'<br>'.join(failed) or '-'} |")
    counts = summarize(grades)
    stats = meta.get("stats", {})
    lines += [
        "",
        f"**PASS {counts['PASS']} · PARTIAL {counts['PARTIAL']} · FAIL {counts['FAIL']}"
        + (f" · NOT RUN {counts[NOT_RUN]}" if counts[NOT_RUN] else "")
        + f"** of {len(grades)} cases.",
    ]
    if stats:
        lines += ["", "Run statistics: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in stats.items()) + "."]
    return "\n".join(lines)


def grade_file(path: Path, selected: Sequence[str]) -> int:
    run = json.loads(path.read_text(encoding="utf-8"))
    grades = grade_run(load_cases(selected), run)
    text = report(grades, run, path.name)
    print(text)
    path.with_suffix(".report.md").write_text(text + "\n", encoding="utf-8")
    return 1 if any(g.verdict == FAIL for g in grades) else 0


# --- live recording ----------------------------------------------------------------------


async def record_live(cases: Sequence[dict[str, Any]]) -> Path:
    from weather_risk.agents.core import LlmMessage, LlmProvider
    from weather_risk.container import _build_llm, build_container
    from weather_risk.infrastructure.config import Settings

    class Recording(LlmProvider):
        """Pass-through to the real provider; counts planning, repair and answer calls."""

        def __init__(self, inner: LlmProvider) -> None:
            self.inner, self.calls = inner, []

        async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
            planning = "PLANNING TASK" in system
            repair = "failed structured-output validation" in messages[-1].content
            self.calls.append("repair" if repair else "plan" if planning else "answer")
            return await self.inner.complete(system, messages)

    class BlankRetries(logging.Handler):
        def __init__(self) -> None:
            super().__init__(logging.INFO)
            self.count = 0

        def emit(self, record: logging.LogRecord) -> None:
            self.count += "Retrying LLM request after a blank response" in record.getMessage()

    settings = Settings(conversation={"store": "memory"})  # eval chats never enter the app database
    inner, client = _build_llm(settings)
    recorder = Recording(inner)
    container = build_container(settings, llm_provider=recorder)
    blanks = BlankRetries()
    llm_logger = logging.getLogger("weather_risk.infrastructure.llm")
    llm_logger.setLevel(logging.INFO)
    llm_logger.addHandler(blanks)

    recorded: list[dict[str, Any]] = []
    try:
        for case in cases:
            session_id = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"
            turns = []
            for spec in case["turns"]:
                before = len(recorder.calls)
                started = time.perf_counter()
                turn: dict[str, Any] = {"user": spec["user"], "session_id": session_id}
                try:
                    response = await container.chat_runtime.run(session_id, spec["user"], uuid.uuid4().hex)
                except Exception as exc:  # recorded and graded, never retried
                    turn["error"] = f"{type(exc).__name__}: {exc}"
                else:
                    turn["answer"] = response.answer
                    turn["warnings"] = list(response.warnings)
                    turn["actions"] = [
                        {
                            "capability": a.capability,
                            "arguments": _jsonable(a.arguments),
                            "status": a.status.value,
                            "duration_ms": a.duration_ms,
                            "error": a.error,
                        }
                        for a in response.actions_performed
                    ]
                    turn["results"] = [
                        {"capability": o.capability, "arguments": _jsonable(o.arguments), "data": _jsonable(o.data or {})}
                        for o in response.results
                    ]
                calls = recorder.calls[before:]
                turn["planning_rounds"] = calls.count("plan")
                turn["llm_calls"] = len(calls)
                turn["elapsed_s"] = round(time.perf_counter() - started, 1)
                turns.append(turn)
                status = turn.get("error") or "ok"
                print(f"  {case['id']}: {status} | {[a['capability'] for a in turn.get('actions', [])]}", flush=True)
            recorded.append({"id": case["id"], "turns": turns})
    finally:
        await container.aclose()
        if client is not None:
            await client.close()

    meta = {
        "provider": settings.llm.provider,
        "model": settings.llm.resolved_model,
        "effort": settings.llm.effort,
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "stats": {
            "planning_calls": recorder.calls.count("plan"),
            "answer_calls": recorder.calls.count("answer"),
            "structured_repairs": recorder.calls.count("repair"),
            "blank_response_retries": blanks.count,
        },
    }
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"{stamp}-{settings.llm.resolved_model}.json"
    path.write_text(json.dumps({"meta": meta, "cases": recorded}, indent=2), encoding="utf-8")
    return path


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(dict(value), default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="run the cases against the real LLM (costs LLM calls)")
    parser.add_argument("--grade", type=Path, help="recorded run to grade (default: the latest in evals/runs)")
    parser.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    args = parser.parse_args(argv)
    selected = [c for c in args.cases.split(",") if c]

    if args.live:
        cases = load_cases(selected)
        turns = sum(len(c["turns"]) for c in cases)
        print(f"Live run: {len(cases)} case(s), {turns} turn(s), about {2 * turns}-{3 * turns} LLM calls.")
        path = asyncio.run(record_live(cases))
        print(f"Recorded {path}\n")
        return grade_file(path, selected)
    return grade_file(args.grade or latest_run(), selected)


if __name__ == "__main__":
    sys.exit(main())
