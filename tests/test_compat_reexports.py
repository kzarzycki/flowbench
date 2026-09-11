"""The one-release compat shims (E02 S02.2).

`flowbench.runner.driver` and `flowbench.runner.loop` keep every name their
callers import today — the sibling scenarios repo imports `OmnigentDriver` and
`TurnResult` from the first. They re-export names and nothing else: a shim has
no `asyncio`, so a test still patching `flowbench.runner.driver.asyncio.sleep`
must fail loudly rather than silently stop patching the code under test.
"""

import ast
import importlib
from pathlib import Path

import pytest

import flowbench.driver
import flowbench.loop
import flowbench.runner.driver
import flowbench.runner.loop

_DRIVER_NAMES = ("AgentDriver", "OmnigentDriver", "TurnResult", "TurnStatus")
_LOOP_NAMES = ("run_agent_session", "render_tail", "prime_prompt", "relay_prompt", "_is_done")


@pytest.mark.parametrize("name", _DRIVER_NAMES)
def test_runner_driver_reexports_are_the_same_objects(name):
    assert getattr(flowbench.runner.driver, name) is getattr(flowbench.driver, name)


def test_runner_driver_reexports_page_size():
    from flowbench.driver.omnigent import _PAGE

    assert flowbench.runner.driver._PAGE is _PAGE


@pytest.mark.parametrize("name", _LOOP_NAMES)
def test_runner_loop_reexports_are_the_same_objects(name):
    assert getattr(flowbench.runner.loop, name) is getattr(flowbench.loop, name)


def test_downstream_import_forms_still_work():
    """Verbatim from the scenarios repo: scripts/codex_review.py:23 and
    tests/test_codex_review.py:7."""
    from flowbench.runner.driver import OmnigentDriver, TurnResult

    assert (OmnigentDriver, TurnResult) == (
        flowbench.driver.OmnigentDriver,
        flowbench.driver.TurnResult,
    )


@pytest.mark.parametrize("mod", ["flowbench.runner.driver", "flowbench.runner.loop"])
def test_shims_are_import_only(mod):
    """No def, no class, no side effect — only a docstring, imports, __all__."""
    src = Path(importlib.import_module(mod).__file__).read_text()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # module docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Assign) and [t.id for t in node.targets] == ["__all__"]:
            continue
        raise AssertionError(f"{mod} has a non-import top-level {type(node).__name__}")


@pytest.mark.parametrize("mod", [flowbench.runner.driver, flowbench.runner.loop])
def test_shims_do_not_carry_module_internals(mod):
    """Patch targets must name the canonical module (decisions #11)."""
    assert not hasattr(mod, "asyncio")
