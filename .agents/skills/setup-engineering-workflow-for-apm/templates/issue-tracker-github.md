# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues. Run `gh` commands
inside the repository so the CLI infers the remote.

## Operations

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state all --json number,title,body,labels,url`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

## Publish an issue batch

Treat every set of issues produced by an engineering skill as one publication
batch. Issue titles are unique identities inside the draft. Stop on duplicate
titles, unknown blockers, or a dependency cycle.

### Canonical batch

Build one deterministic total order:

1. Start with tickets whose blockers are absent from the remaining set.
2. Select the ready ticket with the lexicographically smallest exact UTF-8
   title bytes.
3. Remove it and repeat.
4. Assign one-based `order` values from that result.

Sort and deduplicate each issue's labels by exact UTF-8 bytes. Sort and
deduplicate blockers by their final ticket order. Preserve titles and bodies
byte-for-byte. Serialize an array of issues as UTF-8 JSON with only `title`,
`body`, `labels`, `blockers`, and `order`; sort object keys, emit Unicode
characters directly, use comma and colon separators without surrounding
whitespace, and preserve the array order. The lowercase hexadecimal SHA-256 of
those bytes is `batch_sha256`.

Append the corresponding stable marker to each body:

```markdown
<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->
```

### Durable publication state

Store the exact approved batch at:

```text
.scratch/agent-skills/github-issue-batches/{batch_sha256}.json
```

The JSON state contains `version`, `batch_sha256`, `approved`, and the complete
canonical issue array. Each issue also records its marker, marked body, and
resolved URL or `null`. A `relationships` array records the blocked order,
blocker order, and `pending` or `confirmed` status for every edge.

Write state atomically after every transition: create a sibling temporary file,
flush and `fsync` it, replace the destination atomically, then `fsync` the
parent directory. A partially written file is never valid resume state. Stop
when an existing state file is malformed, its fingerprint differs, or its
canonical batch differs from the current batch.

### First publication

Before asking for approval:

1. Search every marker across all issue states with
   `gh issue list --state all --search "<marker>" --json url,body`.
2. Confirm the exact marker in each returned body. Record one matching URL in
   the proposed state. Stop before approval when multiple issues contain one
   marker, and report every matching URL.
3. Render one numbered review containing every issue's order, title, complete
   marked body, labels, and blockers.
4. Show the exact remaining write plan: each missing issue creation followed
   by each pending relationship edit.

When the remaining plan contains external writes, ask exactly: “Create these
GitHub Issues now?” Rejection, an edit request, or absent approval creates no
durable approval and performs no external write. A changed title, body, label,
blocker, or derived order produces a different fingerprint and requires this
complete reconciliation, preview, and approval flow.

After approval, atomically persist the exact batch with `approved: true`.
Proceed directly to the first mutating `gh` command; perform no intervening
remote read. The local atomic approval-state write is the only operation
between consent and the external-write boundary.

### Create and resume

For an exact-batch resume, load its approved state and retain the recorded
approval. Search every marker across all issue states before the next external
write. Reconcile each unique match into state and atomically persist the
result. This recovers an issue that GitHub created when the command response or
the following state write was lost.

Create only issues whose reconciled URL remains `null`, in canonical order.
Pass the approved title, marked body, and labels unchanged to
`gh issue create`. Atomically record and immediately print each returned URL.
On any command failure or interruption, stop with the current durable state;
the next run repeats reconciliation and does not request approval for the same
fingerprint.

After every issue has a URL, add native sub-issue and blocking relationships in
canonical edge order. Use an idempotent add operation so replaying a pending
edge has the same graph result. Atomically mark each edge `confirmed` only
after the command succeeds. When native relationships are unavailable, use an
idempotent body update with the confirmed `Part of` and `Blocked by` URLs.

Approval authorizes only the displayed missing issue creations and relationship
edits for this fingerprint. Closing, commenting on, relabeling, assigning, or
editing unrelated issues requires separate authority.

Pull requests are not a triage request surface unless this file says otherwise.

<!-- github-issue-batch-fixture-protocol
version: 2
canonical_fields:
  - title
  - body
  - labels
  - blockers
  - order
marker: "<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->"
approval_prompt: "Create these GitHub Issues now?"
ordering:
  algorithm: stable_topological
  ticket_tiebreak: title_utf8_bytes
  blocker_order: final_ticket_order
  unique_titles: true
state:
  directory: .scratch/agent-skills/github-issue-batches
  filename: "{batch_sha256}.json"
  atomic_write: sibling_temp_fsync_replace_directory_fsync
  durable_fields:
    - batch_sha256
    - approved
    - canonical_marked_issues
    - resolved_urls
    - relationship_statuses
external_write_boundary:
  - gh
  - issue
  - create
first_run:
  reconcile_before_preview: true
  exact_remaining_write_plan: true
  approval_immediately_before_write: true
resume:
  reuse_exact_batch_approval: true
  reconcile_before_write: true
  recover_lost_create_response: true
search:
  state: all
  before_creation: all_markers
  exact_body_marker: true
matches:
  zero: create
  one: reuse_and_report_url
  multiple: stop
creation_order: dependency
relationships:
  phase: after_all_issue_urls
  replay: idempotent_pending_edges
-->
