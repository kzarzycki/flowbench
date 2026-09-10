"""A case is a folder: the `Case` contract, `case.py` discovery, the script hooks."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from flowbench.case import Case, load_case, scenarios_root
from flowbench.settings import Settings

CASE_PY = """\
from flowbench.case import Case


class {cls}(Case):
    deliverable = {deliverable!r}
"""


def _case_py(folder: Path, cls: str, deliverable: str | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "case.py"
    path.write_text(CASE_PY.format(cls=cls, deliverable=deliverable))
    return path


def _tree(root: Path) -> Path:
    """`<root>/scenarios/demo/cases/thing` — a case folder with real ancestors."""
    case_dir = root / "scenarios" / "demo" / "cases" / "thing"
    case_dir.mkdir(parents=True)
    return case_dir


async def test_defaults_and_identity(tmp_path):
    case_dir = _tree(tmp_path)
    case = Case(case_dir / ".." / "thing")

    assert case.case_dir == case_dir.resolve()
    assert case.name == "thing"
    assert case.judge_path == case_dir.resolve() / "judge.md"
    assert case.deliverable is None
    assert case.max_turns == 80
    assert case.deadline_s == 1800.0
    assert case.has_score_override() is False
    assert await case.score({"name": "plain"}, tmp_path, {}) is None


def test_load_case_without_case_py_is_plain(tmp_path):
    case_dir = _tree(tmp_path)

    case = load_case(case_dir)

    assert type(case).__name__ == "Case"
    assert case.deliverable is None
    assert case.has_score_override() is False


def test_load_case_finds_case_py_in_the_folder(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(case_dir, "InTheFolder", "out.md")

    case = load_case(case_dir)

    assert type(case).__name__ == "InTheFolder"
    assert case.deliverable == "out.md"
    assert case.case_dir == case_dir.resolve()


def test_load_case_walks_up_to_the_scenarios_root(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(case_dir.parents[1], "Shared", "port/")  # scenarios/demo/case.py
    for variant in ("tier-smoke", "tier-core"):
        (case_dir / variant).mkdir()

    for variant in ("tier-smoke", "tier-core"):
        case = load_case(case_dir / variant)
        assert type(case).__name__ == "Shared"
        assert case.deliverable == "port/"
        assert case.name == variant


def test_nearest_case_py_wins_over_an_ancestor(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(case_dir.parents[1], "Ancestor", "ancestor.md")
    _case_py(case_dir, "Nearest", "nearest.md")

    case = load_case(case_dir)

    assert type(case).__name__ == "Nearest"
    assert case.deliverable == "nearest.md"


def test_a_case_py_directly_in_the_scenarios_dir_is_found(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(tmp_path / "scenarios", "AtTheRoot", "root.md")

    case = load_case(case_dir)

    assert type(case).__name__ == "AtTheRoot"
    assert case.deliverable == "root.md"


def test_load_case_stops_at_the_scenarios_root(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(tmp_path, "AboveTheRoot", "nope.md")  # one level above scenarios/

    assert scenarios_root(case_dir) == (tmp_path / "scenarios").resolve()
    assert type(load_case(case_dir)).__name__ == "Case"


def test_load_case_without_a_scenarios_ancestor_stops_at_the_filesystem_root(tmp_path):
    case_dir = tmp_path / "loose" / "thing"
    case_dir.mkdir(parents=True)

    assert scenarios_root(case_dir) == Path(case_dir.resolve().anchor)
    assert type(load_case(case_dir)).__name__ == "Case"


def test_case_py_must_define_exactly_one_subclass(tmp_path):
    none_dir = _tree(tmp_path / "none")
    (none_dir / "case.py").write_text("from flowbench.case import Case\n\nX = 1\n")
    two_dir = _tree(tmp_path / "two")
    (two_dir / "case.py").write_text(
        CASE_PY.format(cls="First", deliverable="a.md")
        + "\n\nclass Second(Case):\n    deliverable = 'b.md'\n"
    )

    with pytest.raises(ValueError, match=str(none_dir / "case.py")) as zero:
        load_case(none_dir)
    with pytest.raises(ValueError, match=str(two_dir / "case.py")) as many:
        load_case(two_dir)

    assert "found 0" in str(zero.value)
    assert "found 2" in str(many.value)


def test_case_py_imports_siblings_by_package_path(tmp_path, monkeypatch):
    # Package caching would mask a regression: start with no `scenarios` modules.
    for key in [k for k in sys.modules if k == "scenarios" or k.startswith("scenarios.")]:
        monkeypatch.delitem(sys.modules, key)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "__init__.py").touch()
    for pkg, cls in (("alpha", "AlphaCase"), ("beta", "BetaCase")):
        folder = tmp_path / "scenarios" / pkg
        folder.mkdir()
        (folder / "__init__.py").touch()
        (folder / "helper.py").write_text(f'DELIVERABLE = "{pkg}.md"\n')
        (folder / "case.py").write_text(
            textwrap.dedent(f"""\
                from flowbench.case import Case
                from scenarios.{pkg}.helper import DELIVERABLE


                class {cls}(Case):
                    deliverable = DELIVERABLE
                """)
        )

    alpha = load_case(tmp_path / "scenarios" / "alpha")
    beta = load_case(tmp_path / "scenarios" / "beta")

    assert type(alpha).__name__ == "AlphaCase"
    assert type(beta).__name__ == "BetaCase"
    assert (alpha.deliverable, beta.deliverable) == ("alpha.md", "beta.md")


async def test_scripts_run_with_flow_env_and_case_cwd(tmp_path, monkeypatch):
    case_dir = _tree(tmp_path)
    for hook in ("setup", "teardown"):
        (case_dir / f"{hook}.sh").write_text(
            textwrap.dedent(f"""\
                set -euo pipefail
                {{
                  printf 'flow=%s\\n' "$FLOW_NAME"
                  printf 'dir=%s\\n' "$FLOW_DIR"
                  printf 'cwd=%s\\n' "$PWD"
                  printf 'marker=%s\\n' "${{CASE_TEST_MARKER:-unset}}"
                }} > "$FLOW_DIR/{hook}-out.txt"
                """)
        )
    monkeypatch.setenv("CASE_TEST_MARKER", "inherited")
    monkeypatch.chdir(tmp_path)
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    case = load_case(case_dir)

    await case.setup({"name": "plain"}, Path("flow"))  # relative: FLOW_DIR must be absolute
    await case.teardown({"name": "plain"}, Path("flow"))

    for hook in ("setup", "teardown"):
        assert (flow_dir / f"{hook}-out.txt").read_text() == (
            f"flow=plain\ndir={flow_dir.resolve()}\ncwd={case_dir.resolve()}\nmarker=inherited\n"
        )


async def test_default_setup_teardown_are_noops_without_scripts(tmp_path):
    case_dir = _tree(tmp_path)
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    case = load_case(case_dir)

    assert await case.setup({"name": "plain"}, flow_dir) is None
    assert await case.teardown({"name": "plain"}, flow_dir) is None
    assert list(flow_dir.iterdir()) == []


async def test_failing_script_raises(tmp_path):
    case_dir = _tree(tmp_path)
    (case_dir / "setup.sh").write_text("exit 3\n")
    case = load_case(case_dir)

    with pytest.raises(subprocess.CalledProcessError) as exc:
        await case.setup({"name": "plain"}, tmp_path)

    assert exc.value.returncode == 3


def test_find_deliverable_file_dir_nested_missing(tmp_path):
    flow_dir = tmp_path / "flow"
    (flow_dir / "nested" / "deep").mkdir(parents=True)
    (flow_dir / "plan.md").write_text("top\n")
    (flow_dir / "port").mkdir()
    (flow_dir / "nested" / "deep" / "buried.md").write_text("buried\n")

    def case_for(deliverable):
        return type("Declared", (Case,), {"deliverable": deliverable})(tmp_path / "case")

    assert case_for("plan.md").find_deliverable(flow_dir) == flow_dir / "plan.md"
    assert case_for("port").find_deliverable(flow_dir) == flow_dir / "port"
    assert case_for("buried.md").find_deliverable(flow_dir) == (
        flow_dir / "nested" / "deep" / "buried.md"
    )
    assert case_for("absent.md").find_deliverable(flow_dir) is None
    assert Case(tmp_path / "case").find_deliverable(flow_dir) is None


def test_settings_are_carried(tmp_path):
    case_dir = _tree(tmp_path)
    _case_py(case_dir, "Declared", "out.md")
    settings = Settings(sim_model="haiku")

    assert Case(case_dir).settings.sim_model == Settings().sim_model
    assert Case(case_dir, settings).settings is settings
    assert load_case(case_dir, settings).settings is settings
    assert load_case(case_dir).settings.sim_model == Settings().sim_model


def test_the_fixture_case_declares_plan_md():
    case = load_case(Path(__file__).parent / "fixtures" / "feature_flag_service")

    assert case.name == "feature_flag_service"
    assert case.deliverable == "plan.md"
    assert case.validate() == ["superpowers", "plain"]
    assert case.judge_path.is_file()


def test_find_deliverable_picks_the_shallowest_nested_match_then_lexically(tmp_path):
    """Two nested copies is the normal case, not the exotic one: a subagent working
    dir holds one and the real deliverable is elsewhere. `rglob` yields in
    `os.scandir` order, so an unordered pick makes the recorded deliverable_path
    (and therefore the report and the canonical copy) filesystem-dependent."""

    class C(Case):
        deliverable = "plan.md"

    flow = tmp_path / "flow"
    for rel in ("z/plan.md", "a/b/plan.md", "a/plan.md"):
        p = flow / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rel)
    found = C(tmp_path).find_deliverable(flow)
    assert found is not None
    assert found.relative_to(flow).as_posix() == "a/plan.md"  # depth 2 beats depth 3; a beats z
