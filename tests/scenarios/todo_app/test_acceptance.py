"""Acceptance runner vs good/bad fixture apps — proves it discriminates."""

import shutil
import sys
from pathlib import Path

from scenarios.coding_workflow.cases.todo_app.acceptance import resolve_invoker, run_acceptance

FIX = Path(__file__).parents[3] / "scenarios/coding_workflow/cases/todo_app/fixtures"


def _workspace(tmp_path, which):
    ws = tmp_path / which
    shutil.copytree(FIX / which, ws)
    return ws


def test_good_app_passes_all_checks(tmp_path):
    res = run_acceptance(_workspace(tmp_path, "good_app"))
    assert res.app_runs is True
    assert res.passed == res.total == 7
    assert res.score == 1.0


def test_bad_app_fails_persistence(tmp_path):
    res = run_acceptance(_workspace(tmp_path, "bad_app"))
    # in-memory: each CLI call is a fresh process, so `list` after the adds is
    # empty -> the "contains all three" check fails. Discriminates correctly.
    assert res.score < 1.0
    names = {c.name for c in res.checks if not c.passed}
    assert "list_shows_all_three" in names


def test_app_found_in_subdir(tmp_path):
    # C1: the package may be nested (e.g. <ws>/src/todo). Acceptance must find it.
    ws = tmp_path / "nested"
    (ws / "src").mkdir(parents=True)
    shutil.copytree(FIX / "good_app" / "todo", ws / "src" / "todo")
    res = run_acceptance(ws)
    assert res.app_runs is True and res.score == 1.0


def test_accepts_console_script_invocation(tmp_path):
    # Accept-both: an app that ships a console-script entry point (no __main__.py)
    # must pass via the pyproject [project.scripts] target, not only `python -m todo`.
    ws = tmp_path / "console"
    (ws / "todo").mkdir(parents=True)
    (ws / "todo" / "__init__.py").write_text("")
    (ws / "todo" / "cli.py").write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "S=Path('tasks.json')\n"
        "def _load():\n"
        "    return json.loads(S.read_text()) if S.exists() else []\n"
        "def main():\n"
        "    a=sys.argv[1:]; t=_load()\n"
        "    if a[0]=='add':\n"
        "        t.append({'text':a[1],'done':False}); S.write_text(json.dumps(t)); return 0\n"
        "    if a[0]=='list':\n"
        "        [print(f\"{i+1}. {'[x]' if x['done'] else '[ ]'} {x['text']}\") for i,x in enumerate(t)]; return 0\n"
        "    if a[0]=='done':\n"
        "        t[int(a[1])-1]['done']=True; S.write_text(json.dumps(t)); return 0\n"
        "    if a[0]=='rm':\n"
        "        t.pop(int(a[1])-1); S.write_text(json.dumps(t)); return 0\n"
        "    return 2\n"
    )
    (ws / "pyproject.toml").write_text(
        '[project]\nname="todo"\nversion="0.1.0"\n[project.scripts]\ntodo = "todo.cli:main"\n'
    )
    res = run_acceptance(ws)
    assert res.app_runs is True and res.score == 1.0


def test_done_marker_rejects_constant_hint(tmp_path):
    # H2: an app that prints "done" on every line (e.g. a usage hint) must NOT
    # pass done_marker_shown.
    ws = tmp_path / "hinty"
    (ws / "todo").mkdir(parents=True)
    (ws / "todo" / "__init__.py").write_text("")
    (ws / "todo" / "__main__.py").write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "S=Path('tasks.json')\n"
        "def load():\n"
        "    return json.loads(S.read_text()) if S.exists() else []\n"
        "def main(a):\n"
        "    t=load()\n"
        "    if a[0]=='add':\n"
        "        t.append(a[1]); S.write_text(json.dumps(t)); return 0\n"
        "    if a[0]=='list':\n"
        "        [print(f'{x} (toggle with: done <id>)') for x in t]; return 0\n"
        "    if a[0] in ('done','rm'):\n"
        "        if a[0]=='rm': t=[x for i,x in enumerate(t) if i!=int(a[1])-1]; S.write_text(json.dumps(t))\n"
        "        return 0\n"
        "    return 2\n"
        "raise SystemExit(main(sys.argv[1:]))\n"
    )
    res = run_acceptance(ws)
    failed = {c.name for c in res.checks if not c.passed}
    assert "done_marker_shown" in failed  # constant hint must not count as a marker


def test_console_only_app_passes_all_checks(tmp_path):
    # A console-script-only app with no `todo` package anywhere: resolve_invoker
    # must fall back to the shim, not just probe-fail into a broken `-m todo`.
    res = run_acceptance(_workspace(tmp_path, "console_only_app"))
    assert res.app_runs is True
    assert res.score == 1.0


def test_resolve_invoker_prefers_dash_m_for_package_app(tmp_path):
    ws = _workspace(tmp_path, "good_app")
    assert resolve_invoker(ws) == [sys.executable, "-m", "todo"]


def test_acceptance_has_no_error_string_gate():
    from scenarios.coding_workflow.cases.todo_app import acceptance

    assert "No module named" not in Path(acceptance.__file__).read_text()


def test_console_shim_propagates_exit_code(tmp_path):
    # gate finding on #46: the shim called the entry point and discarded its
    # return value, so every console-script app exited 0 and collected a free
    # 3/7 whatever it did. A console app that only ever fails must score low.
    ws = tmp_path / "failing_console"
    (ws / "todoapp").mkdir(parents=True)
    (ws / "todoapp" / "__init__.py").write_text("")
    (ws / "todoapp" / "cli.py").write_text("def main() -> int:\n    return 2\n")
    (ws / "pyproject.toml").write_text(
        '[project]\nname="todoapp"\nversion="0.1.0"\n[project.scripts]\ntodo = "todoapp.cli:main"\n'
    )
    res = run_acceptance(ws)
    assert res.app_runs is False
    assert not any(c.passed for c in res.checks)
