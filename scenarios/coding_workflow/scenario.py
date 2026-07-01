"""The coding_workflow scenario: benchmark how different flows drive a coding agent
from a vague first prompt to a working deliverable.

Rules of this scenario — a flow is scored on whether it (a) elicits the underspecified
requirements (clarifying coverage) and (b) produces a deliverable that passes objective
black-box acceptance, read alongside a low-confidence judge. Scorers and acceptance live with
each case for now (single case); promote them here when a second case shares them.
"""

CASES = ["todo_app"]
