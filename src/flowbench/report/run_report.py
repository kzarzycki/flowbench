"""Render a flowbench run dir into one self-contained report.html.

Pure reader: (run_root with run.json/judge.md/<flow>/{deliverable,transcript,session})
-> report.html next to run.json. No deps; tiny md renderer; light/dark theme.

    uv run python -m flowbench.report.run_report <run_root>
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path


def md_to_html(md: str) -> str:
    """Crude markdown → html: headers, bold, code, bullet lists, paragraphs."""
    out, in_list = [], False
    for line in md.splitlines():
        stripped = line.strip()
        esc = html.escape(stripped)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = esc.lstrip("#").strip()
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h{level + 2}>{text}</h{level + 2}>")  # shift: doc owns h1/h2
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:]}</li>")
        elif re.match(r"^\d+\.\s", stripped):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc}</li>")
        elif not stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def transcript_html(md: str) -> str:
    """transcript.md alternates '## user' / '## assistant' headers — render as chat."""
    blocks = re.split(r"^## (user|assistant)\s*$", md, flags=re.M)
    # blocks: [preamble, role, text, role, text, ...]
    out = []
    for role, text in zip(blocks[1::2], blocks[2::2], strict=False):
        cls = "msg-user" if role == "user" else "msg-agent"
        who = "simulated user" if role == "user" else "agent"
        out.append(
            f'<div class="msg {cls}"><div class="who">{who}</div>{md_to_html(text.strip())}</div>'
        )
    return "\n".join(out)


def _deliverable_view(flow_dir: Path, name: str, relative: str | None = None) -> str:
    """The flow's deliverable as text to render: a file's own text, a directory's
    sorted file listing under a `(name/ — N files)` header, or "" when the flow
    produced none. `relative` is `flow_stats[<flow>].deliverable_path` — where the
    deliverable was *found*, relative to the flow dir, so a nested one is read
    where the agent left it — and falls back to the declared name for run dirs
    written before that path was recorded."""
    path = flow_dir / (relative or name)
    if path.is_dir():
        files = sorted(p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file())
        return "\n".join([f"({name}/ — {len(files)} files)", *files])
    return path.read_text() if path.is_file() else ""


def flow_card(name: str, run_root: Path, is_winner: bool, meta: dict) -> dict:
    stats = (meta.get("flow_stats") or {}).get(name)
    if stats is None:  # pre-flow_stats run.json: fall back to session.json
        s = json.loads((run_root / name / "session.json").read_text())
        stats = {
            "exit_status": s.get("exit_status"),
            "turns": s.get("turns"),
            "duration_s": s.get("duration_s"),
            "artifact_lines": None,
            "context_tokens": s.get("context_tokens"),
        }
    # The case's declared deliverable; an absent key is a run dir written before
    # it was recorded, when the deliverable was always plan.md. `None` is a case
    # that declares none, judged on its conversations alone: no panel, no count.
    deliverable = meta.get("deliverable", "plan.md")
    lines, view = None, ""
    if deliverable is not None:
        view = _deliverable_view(run_root / name, deliverable, stats.get("deliverable_path"))
        lines = stats.get("artifact_lines") or len(view.splitlines())
    transcript = (run_root / name / "transcript.md").read_text()
    tokens = stats.get("context_tokens")
    return {
        "name": name,
        "winner": is_winner,
        "model": meta["models"].get(name, "?"),
        "effort": meta["reasoning_effort"].get(name, "?"),
        "exit": stats.get("exit_status"),
        "turns": stats.get("turns"),
        "duration": f"{round(stats.get('duration_s') or 0)}s",
        "tokens": f"{tokens:,}" if tokens else "–",
        "deliverable_name": deliverable,
        "deliverable_lines": lines,
        "deliverable_html": md_to_html(view),
        "transcript_html": transcript_html(transcript),
    }


CSS = """
:root { --bg:#fff; --fg:#1a1a2e; --muted:#667; --line:#e2e2ea; --card:#f7f7fa;
        --win:#0a7d33; --winbg:#e8f7ee; --user:#eef2ff; --agent:#f7f7fa; --accent:#3949ab; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14141c; --fg:#e8e8f0; --muted:#99a; --line:#2c2c3a; --card:#1c1c28;
          --win:#4cc47a; --winbg:#12281a; --user:#1c2138; --agent:#1c1c28; --accent:#8c9eff; }
}
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.55 system-ui,-apple-system,sans-serif; }
main { max-width:1150px; margin:0 auto; padding:2rem 1.2rem 4rem; }
h1 { font-size:1.5rem; margin:0 0 .2rem } h2 { font-size:1.15rem; margin:2.2rem 0 .8rem }
h3,h4,h5 { margin:1.1rem 0 .4rem }
.sub { color:var(--muted); margin-bottom:1.6rem }
.banner { display:inline-block; background:var(--winbg); color:var(--win);
          border:1px solid var(--win); border-radius:8px; padding:.35rem .8rem;
          font-weight:600; margin:.4rem 0 0 }
table { border-collapse:collapse; width:100%; margin:.6rem 0 }
th,td { text-align:left; padding:.45rem .7rem; border-bottom:1px solid var(--line) }
th { color:var(--muted); font-weight:600; font-size:.85rem; text-transform:uppercase }
td.win { color:var(--win); font-weight:700 }
.cols { display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:1.2rem }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:1rem 1.2rem; overflow-x:auto }
.card h3 { margin-top:0 }
.tag { font-size:.75rem; color:var(--muted); margin-left:.5rem; font-weight:400 }
.winner-tag { color:var(--win); font-weight:700 }
.verdict { border-left:3px solid var(--accent); padding-left:1.1rem }
details { margin:.8rem 0 } summary { cursor:pointer; color:var(--accent); font-weight:600 }
.msg { border:1px solid var(--line); border-radius:8px; padding:.6rem .9rem; margin:.55rem 0 }
.msg-user { background:var(--user) } .msg-agent { background:var(--agent) }
.who { font-size:.72rem; text-transform:uppercase; color:var(--muted); margin-bottom:.25rem }
code { background:var(--line); border-radius:4px; padding:.05rem .3rem; font-size:.9em }
footer { color:var(--muted); font-size:.8rem; margin-top:3rem }
"""


def render_report(run_root: Path) -> Path:
    meta = json.loads((run_root / "run.json").read_text())
    judge_md = (run_root / "judge.md").read_text()
    labels = meta["labels"]  # {"A": flow_name, "B": flow_name, ...}, this trial only
    ordered = sorted(labels.items())  # [("A", name), ("B", name), ...]
    winner_key = meta["winner"].lower()
    winner_name = labels.get(winner_key.upper())
    cards = [flow_card(name, run_root, name == winner_name, meta) for _, name in ordered]

    def lines_cell(c):  # a case that declares no deliverable has no count to show
        return "–" if c["deliverable_lines"] is None else c["deliverable_lines"]

    rows = "".join(
        f"<tr><td class='{'win' if c['winner'] else ''}'>{c['name']}"
        f"{' 🏆' if c['winner'] else ''}</td><td>{c['model']}/{c['effort']}</td>"
        f"<td>{c['exit']}</td><td>{c['turns']}</td><td>{c['duration']}</td>"
        f"<td>{c['tokens']}</td><td>{lines_cell(c)}</td></tr>"
        for c in cards
    )

    def col(c, label):
        wt = " <span class='winner-tag'>winner</span>" if c["winner"] else ""
        # A case that declares no deliverable is compared on its conversations alone.
        panel = (
            f"<details open><summary>{c['deliverable_name']} "
            f"({c['deliverable_lines']} lines)</summary>{c['deliverable_html']}</details>"
            if c["deliverable_name"] is not None
            else ""
        )
        return f"""<div class="card"><h3>{label}: {c["name"]}{wt}
          <span class="tag">{c["model"]}/{c["effort"]} · {c["turns"]} turns · {c["duration"]}</span></h3>
          {panel}
          <details><summary>conversation ({c["turns"]} turns)</summary>{c["transcript_html"]}</details>
        </div>"""

    verdict_line = (
        f"Winner: {winner_name} (flow {meta['winner'].upper()})" if winner_name else "Tie"
    )
    cols_html = "".join(col(c, letter) for (letter, _), c in zip(ordered, cards, strict=True))
    letters_str = "/".join(letter for letter, _ in ordered)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>flowbench · {meta["case"]} · {meta["run_id"]}</title><style>{CSS}</style></head><body><main>
<h1>flowbench run report</h1>
<div class="sub">case <strong>{meta["case"]}</strong> · run <strong>{meta["run_id"]}</strong></div>
<div class="banner">🏆 {verdict_line}</div>

<h2>Flows</h2>
<table><tr><th>flow</th><th>model</th><th>exit</th><th>turns</th><th>duration</th>
<th>context tokens</th><th>deliverable lines</th></tr>{rows}</table>

<h2>Judge verdict</h2>
<div class="verdict">{md_to_html(judge_md)}</div>

<h2>Deliverables &amp; conversations</h2>
<div class="cols">{cols_html}</div>

<footer>generated from {run_root} · flows {letters_str} order as judged · models {json.dumps(meta["models"])}</footer>
</main></body></html>"""
    out = run_root / "report.html"
    out.write_text(doc)
    return out


def render_aggregate_report(run_root: Path) -> Path:
    """n>1 template path: aggregate run.json (flows/counts/winner/score_means/
    trials, all name-keyed) -> report.html linking the per-trial reports."""
    meta = json.loads((run_root / "run.json").read_text())
    flows = meta["flows"]
    counts = meta["counts"]
    winner = meta["winner"]

    ordered_names = [winner, *[n for n in flows if n != winner]] if winner in flows else flows
    count_str = "–".join(str(counts.get(n, 0)) for n in ordered_names)
    headline = (
        f"🏆 {winner} wins {count_str} (n={meta['n']})"
        if winner in flows
        else f"Tie {count_str} (n={meta['n']})"
    )
    extras = [f"{counts[k]} {k}" for k in ("tie", "unknown") if counts.get(k)]
    banner = html.escape(" · ".join([headline, *extras]))

    means = meta.get("score_means") or {}
    criteria = list(dict.fromkeys(c for name in flows for c in means.get(name, {})))
    scores_html = ""
    if criteria:
        header_cells = "".join(f"<th>{html.escape(n)}</th>" for n in flows)
        rows = "".join(
            "<tr><td>{}</td>{}</tr>".format(
                html.escape(c),
                "".join(f"<td>{means.get(n, {}).get(c, '–')}</td>" for n in flows),
            )
            for c in criteria
        )
        scores_html = f"""<h2>Score means</h2>
<table><tr><th>criterion</th>{header_cells}</tr>{rows}</table>"""

    trial_rows = "".join(
        f'<tr><td><a href="{t["trial"]}/report.html">{html.escape(t["trial"])}</a></td>'
        f"<td>{html.escape(str(t.get('winner_flow')))}</td></tr>"
        for t in meta["trials"]
    )

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>flowbench · {meta["case"]} · {meta["run_id"]} · aggregate</title>
<style>{CSS}</style></head><body><main>
<h1>flowbench aggregate report</h1>
<div class="sub">case <strong>{meta["case"]}</strong> · run <strong>{meta["run_id"]}</strong>
 · {meta["n"]} trials</div>
<div class="banner">{banner}</div>
{scores_html}
<h2>Trials</h2>
<table><tr><th>trial</th><th>winner</th></tr>{trial_rows}</table>
<footer>generated from {run_root} · flow names are order-independent · per-trial reports linked above</footer>
</main></body></html>"""
    out = run_root / "report.html"
    out.write_text(doc)
    return out


def render_any(run_root: Path) -> Path:
    """Standalone entrypoint over either run-dir kind: the aggregate run.json is
    the only one with a `trials` key (run.py writes both shapes)."""
    meta = json.loads((run_root / "run.json").read_text())
    return render_aggregate_report(run_root) if "trials" in meta else render_report(run_root)


if __name__ == "__main__":  # pragma: no cover
    print(render_any(Path(sys.argv[1])))
