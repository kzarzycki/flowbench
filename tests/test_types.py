import dataclasses
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
        "QUOTA": "quota",
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
    assert TurnResult(TurnStatus.IDLE, "").status == "idle"


def test_turn_result_has_no_artifact_field():
    # S02.4: the artifact concern lives in the loop/orchestrator, not the turn
    assert "artifact_exists" not in {f.name for f in dataclasses.fields(TurnResult)}


def test_driver_reexports_types():
    import flowbench.runner.driver as driver_mod
    import flowbench.types as types_mod

    assert driver_mod.TurnResult is types_mod.TurnResult
    assert driver_mod.TurnStatus is types_mod.TurnStatus


def test_user_model_implementations():
    from flowbench.model import SessionModel
    from flowbench.testing import ScriptedDriver, StubSim

    assert isinstance(SessionModel(ScriptedDriver([])), UserModel)
    assert isinstance(StubSim([]), UserModel)
    assert not isinstance(object(), UserModel)


def test_user_model_annotation_and_docstring():
    from flowbench.model import SessionModel
    from flowbench.runner.loop import run_agent_session

    hints = typing.get_type_hints(run_agent_session)
    assert hints["user_model"] is UserModel
    assert "flowbench.types.UserModel" in SessionModel.__doc__
