# src/flowbench/cli.py
"""The engine CLI: run a case, watch a live run, compare a finished one.

Every setting is layered (`flowbench.settings.Settings`): a flag beats the
environment, which beats `.env`, which beats `[tool.flowbench]`. A flag that was
not passed is left out of the `Settings` call, so it never shadows one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer()


@app.callback()
def _bootstrap():
    """Compare agentic flows on a fixed case."""
    # The app's own help text, and what keeps typer from promoting a single
    # command to the root: `flowbench compare` stays a subcommand.


def _settings(**flags):
    from flowbench.settings import Settings

    return Settings(**{name: value for name, value in flags.items() if value is not None})


def _die(message: str):
    """A load-time error is the CLI's own output: the message on stderr, exit 1 —
    never a typer.BadParameter, whose exit code 2 reads as a usage mistake."""
    typer.echo(message, err=True)
    raise typer.Exit(1)


@app.command("run")
def run(
    case_dir: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="the case folder to benchmark")
    ],
    n: Annotated[int, typer.Option("--n", min=1, help="trials per case (default 1)")] = 1,
    run_id: Annotated[str, typer.Option(help="default: the current timestamp")] = None,
    runs_root: Annotated[Path, typer.Option(help="where run dirs go (default: settings)")] = None,
    sim_model: Annotated[str, typer.Option(help="the simulator's model")] = None,
    judge_model: Annotated[str, typer.Option(help="the judge's model")] = None,
    rescore: Annotated[
        str,
        typer.Option(help="re-score this existing run id instead of running it: no session"),
    ] = None,
):
    """Run every flow of the case at CASE_DIR under omnigent, then judge/score them."""
    from flowbench.case import check_gradable, load_case
    from flowbench.run import omni_factories, rescore_run, run_case_n

    settings = _settings(runs_root=runs_root, sim_model=sim_model, judge_model=judge_model)
    try:
        case = load_case(case_dir, settings)
        # load_case checks only a folder that already has a flows.yaml; asking
        # again here makes a missing one the CLI's own error too — before any
        # factory, and the runner still checks for a non-CLI caller.
        check_gradable(case)
    except (ValueError, OSError) as e:
        _die(str(e))

    if rescore is not None:
        run_root = settings.runs_root / case.name / rescore
        if not run_root.is_dir():
            _die(f"no run dir at {run_root}")
        typer.echo(json.dumps(asyncio.run(rescore_run(case, run_root)), indent=2))
        return

    make_flow_driver, make_simulator, run_judge = omni_factories(case)
    result = asyncio.run(
        run_case_n(
            case,
            run_id=run_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
            n=n,
            make_flow_driver=make_flow_driver,
            make_simulator=make_simulator,
            run_judge=run_judge,
        )
    )
    # n=1: the trial's own meta (winner, flow stats). n>1: the aggregate tally.
    payload = result["trials"][0] if n == 1 else result["aggregate"]
    typer.echo(json.dumps(payload, indent=2, default=str))
    typer.echo(f"\nRun written to: {result['run_root']}")


@app.command("watch")
def watch(
    run_id: Annotated[str, typer.Argument(help="the run id to follow")],
    runs_root: Annotated[Path, typer.Option(help="where run dirs live (default: settings)")] = None,
    pid: Annotated[int, typer.Option(help="the runner's pid; exit if it dies")] = None,
    interval: Annotated[float, typer.Option(help="seconds between ticks")] = 15.0,
):
    """Stream a live run's anomalies and progress until its run.json lands."""
    from flowbench.watch import RunWatch, follow

    settings = _settings(runs_root=runs_root)
    try:
        run_watch = RunWatch(run_id, runs_root=settings.runs_root)
    except ValueError as e:
        _die(str(e))
    follow(run_watch, pid=pid, interval=interval, out=lambda line: print(line, flush=True))


@app.command("compare")
def compare(
    run_base: str = typer.Option(
        ..., help="the runs base dir, e.g. ../flowbench-runs/todo-app-eval"
    ),
    run_id: str = typer.Option(..., help="the run id whose flow sub-dirs to compare"),
    out: str = typer.Option(None, help="write markdown here (default: stdout)"),
):
    """Side-by-side flow comparison from <run_base>/<run_id>/*/scorecard.json."""
    from flowbench.report.compare import render_compare

    md = render_compare(run_base, run_id)
    if out:
        Path(out).write_text(md)
        typer.echo(f"report written to {out}")
    else:
        typer.echo(md)


if __name__ == "__main__":
    app()
