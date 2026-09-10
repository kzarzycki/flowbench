"""coding_workflow entrypoint: the simulator and each flow run as omnigent
sessions via flowbench's OmnigentDriver — never `claude -p`. Unlike
swe_planning this case has no comparative judge; each flow is scored on its
own (the case's `score`) into <flow>/scorecard.json, read by `flowbench compare`.

Usage (from the repo root; needs a live omnigent server):

    uv run python -m scenarios.coding_workflow.run --case todo_app

    # re-score an existing run's flows (a dead grader session, a scorer fix)
    # without re-driving anything — no new session, session.json untouched:
    uv run python -m scenarios.coding_workflow.run --rescore <run-id>

Outputs land in ../flowbench-runs/coding_workflow/<case>/<run-id>/ (per-flow
subfolders), never inside the repo. The runtime (run_case/run_case_n,
SessionModel, the omnigent factories, rescore_run) lives in the engine:
`flowbench.run`; what the case is (deliverable, budgets, setup, score) lives in
its `case.py`. This module is the CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from flowbench.case import load_case
from flowbench.run import omni_factories, rescore_run, run_case_n
from scenarios.coding_workflow import scenario

SCENARIO = "coding_workflow"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def default_runs_root() -> Path:
    """Sibling ../flowbench-runs/coding_workflow — engine convention: outputs
    never live in the repo. Anchored off __file__, not cwd."""
    return _REPO_ROOT.parent / "flowbench-runs" / SCENARIO


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return n


def _positive_float(value: str) -> float:
    x = float(value)
    if x <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
    return x


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="todo_app", help="case name under cases/")
    ap.add_argument("--run-id", default=None, help="default: current timestamp")
    ap.add_argument("--runs-root", default=None, help="default: ../flowbench-runs/coding_workflow")
    ap.add_argument("--n", type=_positive_int, default=1, help="trials per case (default 1)")
    ap.add_argument(
        "--deadline-s",
        type=_positive_float,
        default=3600.0,
        help="per-flow session budget in seconds (default 3600)",
    )
    ap.add_argument(
        "--rescore",
        default=None,
        metavar="RUN_ID",
        help="re-score an existing run's flows in place (no new session); ignores "
        "--run-id. A flow no longer in flows.yaml is recorded as an error, "
        "overwriting its scorecard",
    )
    return ap.parse_args(argv)


def main() -> None:
    args = _parse_args()
    runs_root = Path(args.runs_root) if args.runs_root else default_runs_root()
    case = load_case(scenario.CASE_DIR(args.case))
    case.deadline_s = args.deadline_s  # the flag overrides what the case declares

    if args.rescore is not None:
        run_root = runs_root / case.name / args.rescore
        if not run_root.is_dir():
            raise SystemExit(f"--rescore: no run dir at {run_root}")
        result = asyncio.run(rescore_run(case, run_root))
        print(json.dumps(result, indent=2))
        return

    make_flow_driver, make_simulator, run_judge = omni_factories(SCENARIO)
    result = asyncio.run(
        run_case_n(
            case,
            run_id=args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
            n=args.n,
            make_flow_driver=make_flow_driver,
            make_simulator=make_simulator,
            run_judge=run_judge,
            runs_root=runs_root,
        )
    )
    # n=1: trials[0] is run_case's meta (the old single-run print). n>1: the
    # aggregate {n, counts, winner}.
    payload = result["trials"][0] if args.n == 1 else result["aggregate"]
    print(json.dumps(payload, indent=2))
    print(f"\nRun written to: {result['run_root']}")


if __name__ == "__main__":
    main()
