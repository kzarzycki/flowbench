import json
import typing

from flowbench.types import Completion, TurnResult, TurnStatus, UserModel


def test_members_are_their_values():
    assert {m.name: m.value for m in TurnStatus} == {
        "IDLE": "idle",
        "RUNNING": "running",
        "FAILED": "failed",
        "TIMEOUT": "timeout",
        "STALLED": "stalled",
    }
    for m in TurnStatus:
        assert m == m.value


def test_fstring_is_bare_value():
    # Load-bearing: only this test fails if StrEnum is swapped for (str, Enum) —
    # json.dumps emits "idle" for both, so the JSON test alone would not catch it.
    assert f"{TurnStatus.IDLE}" == "idle"


def test_completion_is_the_declared_return():
    hints = typing.get_type_hints(UserModel.generate)
    assert hints["return"] is Completion


def test_json_round_trip():
    assert json.loads(json.dumps({"exit_status": TurnStatus.STALLED})) == {"exit_status": "stalled"}


def test_turn_result_status_compares_to_literal():
    assert TurnResult(TurnStatus.IDLE, "", False).status == "idle"
