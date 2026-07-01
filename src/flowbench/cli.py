# src/flowbench/cli.py
from pathlib import Path

import typer
from dotenv import load_dotenv

app = typer.Typer()


@app.callback()
def _bootstrap():
    """Load .env if present (e.g. runner settings)."""
    load_dotenv()


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
