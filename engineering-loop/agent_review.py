"""One-shot cross-vendor reviewer for the engineering loop (issue #36).

Spawns a review session on one omnigent harness in the given worktree, sends
it a review brief, and prints the reviewer's final message to stdout. Reuses
flowbench's OmnigentDriver — the same machinery swe_planning uses for its
codex flows — so there is no hand-rolled HTTP here.

The loop pins no model id of its own: each harness runs whatever its host
install currently resolves to, so an upgrade there carries the gates forward.
The point is a reviewer from a different vendor than the implementer, on that
vendor's strongest current model. `--model` overrides for a one-off.

Usage (from the repo root, the live extra carries the omnigent client):

    uv run --extra live python scripts/agent_review.py \
        --cwd <worktree> --title "issue-36 gate-1" \
        --brief-file brief.md > review.md

`--harness` selects the vendor (default `codex-native`, the only one verified
end to end). Others omnigent lists may work but are unproven: `antigravity-native`
starts and resolves a model, then stalls the turn on a human-prompt signal.
Smoke-test a harness and get a verdict back before a gate depends on it.
"""

import argparse
import asyncio
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

from flowbench.driver import OmnigentDriver

SERVER = "http://127.0.0.1:6767"
DEFAULT_HARNESS = "codex-native"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"


def codex_model() -> str:
    """The model the host's codex CLI is configured to use."""
    if not CODEX_CONFIG.exists():
        sys.exit(f"no codex config at {CODEX_CONFIG}; pass --model")
    model = tomllib.loads(CODEX_CONFIG.read_text()).get("model")
    if not model:
        sys.exit(f"no 'model' key in {CODEX_CONFIG}; pass --model")
    return str(model)


# Harnesses whose host CLI keeps a model id we must read ourselves. Anything
# absent takes the harness default: the driver sends model_override=None and
# omnigent falls back to the agent spec's model.
MODEL_RESOLVERS = {"codex-native": codex_model}


def resolve_model(harness: str) -> str | None:
    resolver = MODEL_RESOLVERS.get(harness)
    return resolver() if resolver else None


def ensure_server() -> None:
    def up() -> bool:
        try:
            urllib.request.urlopen(f"{SERVER}/health", timeout=5)
            return True
        except OSError:
            return False

    if up():
        return
    subprocess.run(["omnigent", "server", "start"], check=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        if up():
            return
        time.sleep(2)
    sys.exit("omnigent server did not come up within 60s")


async def review(args: argparse.Namespace, brief: str) -> str:
    driver = OmnigentDriver(
        run_dir=Path(args.cwd).resolve(),
        harness=args.harness,
        model=args.model or resolve_model(args.harness),
        reasoning_effort=args.effort,
        skills="none",
        session_title=args.title,
        project="engineering-loop",
        turn_timeout_s=args.timeout,
    )
    await driver.start()
    try:
        result = await driver.send(brief)
    finally:
        await driver.close()
    return verdict_from(result)


def verdict_from(result) -> str:
    """The review file IS the reviewer's final message. A `--remote` native-TUI
    harness routinely reports status='failed' right after emitting that message
    (operating-omnigent gotcha; the same terminal-readiness flake that killed
    swe_planning's live codex turns) — so trust the text whenever there is one.
    Only a turn that produced NOTHING is a real failure; the loop's next rung
    takes over on the resulting non-zero exit."""
    if not result.assistant_text.strip():
        sys.exit(f"reviewer turn ended '{result.status}' with no verdict text")
    if result.status != "idle":
        print(
            f"[agent_review] turn status {result.status!r}; using the emitted verdict",
            file=sys.stderr,
        )
    return result.assistant_text


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--brief-file", required=True, help="file with the review brief (- for stdin)")
    p.add_argument("--cwd", default=".", help="worktree the reviewer reads (its shell cwd)")
    p.add_argument("--title", default="agent-review", help="omnigent session title")
    p.add_argument(
        "--harness",
        default=DEFAULT_HARNESS,
        help=f"omnigent harness to review on (default {DEFAULT_HARNESS})",
    )
    p.add_argument("--model", default=None, help="override the harness's resolved model")
    p.add_argument(
        "--effort",
        default="high",
        # The vendor validates: codex takes none/minimal/low/medium/high/xhigh,
        # claude low/medium/high/xhigh/max. Validation is provider-scoped, so
        # `minimal` is accepted for codex models that don't offer it and the
        # turn dies with zero usage — lowest usable rung is `low`.
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    )
    p.add_argument("--timeout", type=float, default=1800, help="turn timeout seconds")
    args = p.parse_args()

    brief = sys.stdin.read() if args.brief_file == "-" else Path(args.brief_file).read_text()
    ensure_server()
    print(asyncio.run(review(args, brief)))


if __name__ == "__main__":
    main()
