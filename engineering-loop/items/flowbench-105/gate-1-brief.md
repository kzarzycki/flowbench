You are reviewing a design document written by an engineer you've never met, for an
unattended pipeline — you are the only review this document will get before it merges and is
posted on the tracking issue.

Document under review: `docs/design/omnigent-api-inventory.md` (this worktree).
Spec + decisions it must satisfy: `/Users/zarz/dev/xebia/flowbench-scenarios--s025/.claude/engineering-loop/items/flowbench-105/spec.md` and `decisions.md` in the same dir.
Upstream issue draft it references: `/Users/zarz/dev/xebia/flowbench-scenarios--s025/.claude/engineering-loop/items/upstream/omnigent-client-create-launch-args.md`.

Verify by reading the code, not by trusting the prose:
- the driver: `src/flowbench/driver/omnigent.py`, `src/flowbench/driver/bundle.py`
- the pinned client + package: `.venv/lib/python3.13/site-packages/omnigent_client/` and
  `.venv/lib/python3.13/site-packages/omnigent/` (0.2.0). Note: `rg` skips `.venv` unless you
  pass `--no-ignore`.
- the running server's source: `/Users/zarz/dev/ext/omnigent/omnigent` (read-only; HEAD `8627eb9f`).

Reject unless ALL hold:
(a) every claim about the flowbench driver (line numbers, what each call does, why it exists)
    is true;
(b) every claim about omnigent — public exports, `create()` signatures, `SessionCreateMetadata`
    fields, `daemon_launch` endpoints, what the `Session` dataclass drops — is true in the
    version the doc attributes it to;
(c) the inventory is complete: every non-`self.` `_`-prefixed access into omnigent under
    `src/flowbench/` appears, and nothing listed is invented;
(d) each verdict (migrate-now / blocked-upstream / keep) follows from the evidence, and the
    doc nowhere suggests moving session-create to `sessions.create()` before the SDK carries
    `terminal_launch_args`;
(e) the spec's acceptance criteria A1-A4 are met by the doc as written;
(f) the upstream draft states only facts you can confirm in the omnigent checkout, and asks
    for a change the server already supports.

Verdict on the last line: APPROVE, or REVISE with numbered file:line objections.
