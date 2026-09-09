"""Transcript helpers: the driver's + the swe_planning orchestrator's shared
notion of "message text" and captured-session cleanup. Pure (no I/O, no
omnigent) so the driver, the normalizer, and any case's transcript rendering
can't diverge on what counts as conversation."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def item_text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Same accepted part-types as normalize._message_text so the driver's
        # notion of "assistant text" can't diverge from the scorer's.
        return "".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") in (None, "text", "input_text", "output_text")
        )
    return ""


def last_assistant_text(items: list[dict]) -> str:
    for it in reversed(items):
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant":
            txt = item_text(it)
            if txt.strip():
                return txt
    return ""


def n_assistant_messages(items: list[dict]) -> int:
    return sum(
        1
        for it in items
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant"
    )


def new_assistant_text(items: list[dict], n_before: int) -> str:
    """Text of the last NON-EMPTY assistant message beyond the first `n_before`
    assistant messages — i.e. a reply that landed after the inject `n_before` was
    taken for. "" when none did. An empty new message is not a reply: without
    this rule `last_assistant_text` would hand back an OLDER reply as this turn's."""
    msgs = [
        it
        for it in items
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant"
    ]
    return last_assistant_text(msgs[n_before:])


# Harness control injections that are NOT part of the user/agent conversation —
# Claude Code surfaces sub-agent completions as role=user `<task-notification>`
# messages. They must not pollute the transcript or be read as conversation.
_CONTROL_PREFIXES = ("<task-notification>",)


def is_control_message(text: str) -> bool:
    return text.lstrip().startswith(_CONTROL_PREFIXES)


def dedup_items(items: list[dict]) -> list[dict]:
    """Clean the captured conversation: drop (1) the consecutive duplicate message
    omnigent records for every injected turn, and (2) harness control injections
    (`<task-notification>`). Non-message items pass through untouched. A duplicate
    is a message whose (role, text) equals the previous KEPT message's — real
    turns are always separated by the other party's message, so this only ever
    collapses the capture artifact."""
    out: list[dict] = []
    last_key: tuple[str, str] | None = None
    for it in items:
        if not (isinstance(it, dict) and it.get("type") == "message"):
            out.append(it)
            continue
        text = item_text(it)
        if is_control_message(text):
            continue
        key = (it.get("role", ""), text)
        if key == last_key:
            continue
        last_key = key
        out.append(it)
    return out


def render_transcript(items: list[dict]) -> str:
    """Human-readable sim<->flow interaction from a captured session's items.
    Injected simulator answers appear as role=user; flow output as role=assistant."""
    lines = ["# Transcript", ""]
    for it in items:
        if not (isinstance(it, dict) and it.get("type") == "message"):
            continue
        text = item_text(it)
        if not text.strip():
            continue
        lines.append(f"## {it.get('role', '?')}")
        lines.append("")
        lines.append(text.strip())
        lines.append("")
    return "\n".join(lines)


def to_jsonable(ev: object) -> dict:
    """A streamed omnigent event as a plain JSON-able dict, tagged with its type.
    Pydantic model, dataclass, or anything else (recorded as a truncated repr) —
    the captured `events` list must survive `json.dump` whatever the client ships."""
    import dataclasses

    fn = getattr(ev, "model_dump", None)
    if callable(fn):
        try:
            return {"__type__": type(ev).__name__, **fn(mode="json")}
        except Exception as e:  # noqa: BLE001 -- the capture must survive whatever the
            # client ships; a recording failure never aborts the turn it records
            log.debug("model_dump(%s) failed, recording repr: %r", type(ev).__name__, e)
    if dataclasses.is_dataclass(ev):
        return {"__type__": type(ev).__name__, **dataclasses.asdict(ev)}
    return {"__type__": type(ev).__name__, "repr": repr(ev)[:300]}
