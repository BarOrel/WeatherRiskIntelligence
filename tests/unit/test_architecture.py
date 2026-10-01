"""Guards the dependency rule: inner layers must not import outer layers or frameworks."""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "weather_risk"

FRAMEWORKS = ("fastapi", "pydantic", "pydantic_settings", "httpx", "httpx2", "starlette")
LLM_VENDORS = ("anthropic", "openai")

FORBIDDEN_IMPORTS = {
    "domain": (
        *FRAMEWORKS,
        *LLM_VENDORS,
        "weather_risk.application",
        "weather_risk.agents",
        "weather_risk.infrastructure",
        "weather_risk.presentation",
        "weather_risk.container",
    ),
    "application": (
        *FRAMEWORKS,
        *LLM_VENDORS,
        "weather_risk.agents",
        "weather_risk.infrastructure",
        "weather_risk.presentation",
        "weather_risk.container",
    ),
    # The agent layer may use Pydantic (LLM I/O schemas) but no vendor SDK, HTTP or web framework.
    "agents": (
        "fastapi",
        "starlette",
        "httpx",
        "httpx2",
        *LLM_VENDORS,
        "weather_risk.infrastructure",
        "weather_risk.presentation",
        "weather_risk.container",
    ),
}


def test_generic_agent_core_is_not_weather_specific() -> None:
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in (PACKAGE_ROOT / "agents" / "core").rglob("*.py")
        for module in _imported_modules(path)
        if module.startswith("weather_risk.agents.weather_risk")
        or module.startswith("weather_risk.domain")
    ]

    assert not violations, "\n".join(violations)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_IMPORTS))
def test_layer_does_not_depend_on_outer_layers(layer: str) -> None:
    forbidden = FORBIDDEN_IMPORTS[layer]
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in (PACKAGE_ROOT / layer).rglob("*.py")
        for module in _imported_modules(path)
        if any(module == f or module.startswith(f"{f}.") for f in forbidden)
    ]

    assert not violations, "\n".join(violations)


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_caching_is_an_infrastructure_concern(layer: str) -> None:
    """Cache abstractions, implementations and decorators belong to infrastructure only."""
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} defines {node.name}"
        for path in (PACKAGE_ROOT / layer).rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and "cache" in node.name.lower()
    ]

    assert not violations, "\n".join(violations)


def test_use_cases_do_not_depend_on_each_other() -> None:
    """Each use case is an independent vertical slice; shared logic lives outside the slices
    (domain risk engine, HubRiskAssessor, focused services)."""
    use_cases = PACKAGE_ROOT / "application" / "use_cases"
    violations = [
        f"{path.name} imports {module}"
        for path in use_cases.glob("*.py")
        if path.name != "__init__.py"
        for module in _imported_modules(path)
        if module.startswith("weather_risk.application.use_cases")
    ]

    assert not violations, "\n".join(violations)


AGENTS = PACKAGE_ROOT / "agents"
LLM_AND_CONVERSATION = (
    "weather_risk.agents.core.llm",
    "weather_risk.agents.core.structured",
    "weather_risk.agents.core.reasoning",
    "weather_risk.agents.core.conversation",
    "weather_risk.agents.core.runtime",
    "weather_risk.infrastructure",
)


def _violations(paths: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in paths
        for module in _imported_modules(path)
        if any(module == f or module.startswith(f"{f}.") for f in forbidden)
    ]


def test_agents_execute_plans_without_llm_or_conversation_access() -> None:
    """Agent + plan execution + the weather agent never touch the LLM or chat history; the
    ChatRuntime owns that lifecycle."""
    paths = [
        AGENTS / "core" / "agent.py",
        AGENTS / "core" / "execution.py",
        AGENTS / "core" / "capabilities.py",
        AGENTS / "core" / "plan.py",
        *(AGENTS / "weather_risk").rglob("*.py"),
    ]
    paths = [p for p in paths if p.name != "__init__.py"]

    violations = _violations(paths, LLM_AND_CONVERSATION)

    assert not violations, "\n".join(violations)


def test_reasoning_cannot_reach_business_logic_or_execution() -> None:
    """The ReasoningEngine talks to the LLM only: no use cases, providers, domain scoring or
    capability execution."""
    violations = _violations(
        [AGENTS / "core" / "reasoning.py", AGENTS / "core" / "structured.py"],
        (
            "weather_risk.application",
            "weather_risk.domain",
            "weather_risk.agents.core.execution",
            "weather_risk.agents.core.runtime",
            "weather_risk.agents.weather_risk",
        ),
    )

    assert not violations, "\n".join(violations)
