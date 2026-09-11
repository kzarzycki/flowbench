"""A case is a folder: the `Case` contract, `case.py` discovery, the script hooks."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from flowbench.case import (
    SCENARIOS_DIR,
    Case,
    Workspace,
    load_case,
    scenarios_root,
    seed_workspace,
)
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


def _is_scenarios(name: str) -> bool:
    return name == SCENARIOS_DIR or name.startswith(f"{SCENARIOS_DIR}.")


@pytest.fixture
def isolated_imports(monkeypatch):
    """`sys.path` and every `scenarios.…` module put back after the test, so a tree
    under `tmp_path` can own the `scenarios` package name while it runs — and so
    what the loader inserts is visible instead of pre-supplied."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    saved = {name: mod for name, mod in sys.modules.items() if _is_scenarios(name)}
    for name in saved:
        del sys.modules[name]
    yield
    for name in [n for n in sys.modules if _is_scenarios(n)]:
        del sys.modules[name]
    sys.modules.update(saved)


SIBLING_CASE_PY = """\
from flowbench.case import Case
from scenarios.{pkg}.helper import DELIVERABLE


class Sibling(Case):
    deliverable = DELIVERABLE
"""


def _package(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").touch()
    return folder


def _importing_case(root: Path, pkg: str) -> Path:
    """`<root>/scenarios/<pkg>/case.py`, importing its own sibling by package path."""
    folder = _package(_package(root / SCENARIOS_DIR) / pkg)
    (folder / "helper.py").write_text(f'DELIVERABLE = "{pkg}.md"\n')
    (folder / "case.py").write_text(SIBLING_CASE_PY.format(pkg=pkg))
    return folder


def test_load_case_puts_the_scenarios_parent_on_sys_path(tmp_path, isolated_imports):
    """What the installed console script needs: its `sys.path[0]` is the script's
    own directory and the cwd is never added, so only the loader can make a
    case.py's `scenarios.…` import resolve."""
    case_dir = _importing_case(tmp_path, "alpha")
    parent = str(tmp_path.resolve())
    assert parent not in sys.path

    case = load_case(case_dir)

    assert type(case).__name__ == "Sibling"
    assert case.deliverable == "alpha.md"
    assert sys.path[0] == parent

    load_case(case_dir)

    assert sys.path.count(parent) == 1  # already there: not inserted again


def test_load_case_without_a_scenarios_ancestor_leaves_sys_path_alone(tmp_path, isolated_imports):
    case_dir = tmp_path / "loose" / "thing"
    _case_py(case_dir, "Loose", "out.md")
    before = list(sys.path)

    assert type(load_case(case_dir)).__name__ == "Loose"
    assert sys.path == before


BASE_PY = """\
from flowbench.case import Case


class SharedBase(Case):
    max_turns = 5
"""


def _with_a_shared_base(root: Path, pkg: str, case_py: str) -> Path:
    """`<root>/scenarios/base.py` holding `SharedBase`, plus `<pkg>/case.py`."""
    scenarios = _package(root / SCENARIOS_DIR)
    (scenarios / "base.py").write_text(BASE_PY)
    folder = _package(scenarios / pkg)
    (folder / "case.py").write_text(case_py)
    return folder


def test_an_imported_case_class_does_not_count_as_a_second_subclass(tmp_path, isolated_imports):
    case_dir = _with_a_shared_base(
        tmp_path,
        "derived",
        textwrap.dedent("""\
            from scenarios.base import SharedBase


            class Derived(SharedBase):
                deliverable = "derived.md"
            """),
    )

    case = load_case(case_dir)

    assert type(case).__name__ == "Derived"
    assert (case.deliverable, case.max_turns) == ("derived.md", 5)


def test_a_case_py_that_only_imports_a_case_class_defines_none(tmp_path, isolated_imports):
    case_dir = _with_a_shared_base(tmp_path, "borrowed", "from scenarios.base import SharedBase\n")

    with pytest.raises(ValueError, match=str(case_dir / "case.py")) as err:
        load_case(case_dir)

    assert "found 0" in str(err.value)


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


def _seeded(tmp_path, deliverable, seed_files):
    """A case declaring `deliverable` and a `seed/` tree, plus its flow dir."""
    case_dir = tmp_path / "case"
    for rel, body in seed_files.items():
        p = case_dir / "seed" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    cls = type(
        "Seeded",
        (Case,),
        {"deliverable": deliverable, "workspace": Workspace(seed="seed")},
    )
    return cls(case_dir), tmp_path / "flow"


def test_untouched_seeded_deliverable_is_not_found(tmp_path):
    """The seed is not delivery: a file the engine put there, unchanged, must not
    score as this flow's work."""
    case, flow = _seeded(tmp_path, "out.txt", {"out.txt": "seeded\n"})
    seed_workspace(case.workspace, case.case_dir, flow)

    assert case.find_deliverable(flow) is None


def test_modified_seeded_deliverable_is_found(tmp_path):
    case, flow = _seeded(tmp_path, "out.txt", {"out.txt": "seeded\n"})
    seed_workspace(case.workspace, case.case_dir, flow)

    (flow / "out.txt").write_text("seeded\nauthored\n")

    assert case.find_deliverable(flow) == flow / "out.txt"


def test_nested_seed_copy_is_skipped_for_a_modified_deeper_one(tmp_path):
    """The seed filter runs BEFORE the shallowest-first pick: filtering after it
    would answer None here, because the shallow candidate is the untouched seed."""
    case, flow = _seeded(tmp_path, "out.txt", {"sub/out.txt": "seeded\n"})
    seed_workspace(case.workspace, case.case_dir, flow)
    deep = flow / "deep" / "nested" / "out.txt"
    deep.parent.mkdir(parents=True)
    deep.write_text("authored\n")

    assert case.find_deliverable(flow) == deep


def test_an_edited_case_py_is_never_served_from_stale_bytecode(tmp_path):
    """Two same-length edits sharing one mtime second: CPython's `.pyc` check is
    `(mtime-to-the-second, size)`, so the loader must not consult the cache at all.
    `flowbench run --rescore` right after editing a case is exactly this shape."""
    case_dir = _tree(tmp_path)
    path = _case_py(case_dir, "First", deliverable="aaa.md")
    assert load_case(case_dir, Settings()).deliverable == "aaa.md"

    mtime = path.stat().st_mtime
    _case_py(case_dir, "First", deliverable="bbb.md")  # same length, same second
    os.utime(path, (mtime, mtime))

    assert load_case(case_dir, Settings()).deliverable == "bbb.md"
