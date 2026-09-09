import asyncio

import pytest

import flowbench.model as model_mod
from flowbench.model import SessionModel
from flowbench.runner.driver import TurnResult
from flowbench.testing import ScriptedDriver
from flowbench.types import TurnStatus


def test_generate_trusts_fresh_text_on_failed_turn():
    # the terminal-readiness flake fires AFTER the reply lands (issue #39):
    # failed status with FRESH text is a completed turn, not a failure
    driver = ScriptedDriver([TurnResult(TurnStatus.FAILED, "the reply", False)])
    model = SessionModel(driver)
    out = asyncio.run(model.generate("x"))
    assert out.completion == "the reply"
    assert len(driver.sent) == 1


def test_generate_retries_stale_text_on_failed_turn(monkeypatch):
    # a failed turn whose text equals the PREVIOUS completion is stale — the new
    # prompt never got a reply; trusting it would corrupt the dialog (gate-1)
    monkeypatch.setattr(model_mod, "GENERATE_RETRY_WAIT_S", 0.0)
    driver = ScriptedDriver(
        [
            TurnResult(TurnStatus.IDLE, "first reply", False),
            TurnResult(TurnStatus.FAILED, "first reply", False),  # stale echo
            TurnResult(TurnStatus.IDLE, "second reply", False),
        ]
    )
    model = SessionModel(driver)
    assert asyncio.run(model.generate("q1")).completion == "first reply"
    out = asyncio.run(model.generate("q2"))
    assert out.completion == "second reply"
    assert driver.sent == ["q1", "q2", "q2"]


def test_generate_timeout_raises_without_retry():
    # a timed-out turn may still be mid-flight after delivery — resending there
    # is the known busy-terminal kill; fail immediately, even with fresh text
    for text in ("", "fresh but untrusted"):
        driver = ScriptedDriver([TurnResult(TurnStatus.TIMEOUT, text, False)])
        model = SessionModel(driver)
        with pytest.raises(RuntimeError, match="timeout"):
            asyncio.run(model.generate("x"))
        assert len(driver.sent) == 1


def test_generate_retries_failed_empty_turn(monkeypatch):
    monkeypatch.setattr(model_mod, "GENERATE_RETRY_WAIT_S", 0.0)
    driver = ScriptedDriver(
        [TurnResult(TurnStatus.FAILED, "", False), TurnResult(TurnStatus.IDLE, "second try", False)]
    )
    model = SessionModel(driver)
    out = asyncio.run(model.generate("x"))
    assert out.completion == "second try"
    assert driver.sent == ["x", "x"]


def test_generate_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setattr(model_mod, "GENERATE_RETRY_WAIT_S", 0.0)
    driver = ScriptedDriver([TurnResult(TurnStatus.FAILED, "", False)] * 3)
    model = SessionModel(driver)
    with pytest.raises(RuntimeError, match="3 attempts"):
        asyncio.run(model.generate("x"))
    assert len(driver.sent) == 3


def test_generate_idle_path_single_send():
    driver = ScriptedDriver([TurnResult(TurnStatus.IDLE, "ok", False)])
    model = SessionModel(driver)
    out = asyncio.run(model.generate("x"))
    assert out.completion == "ok"
    assert len(driver.sent) == 1


def test_close_closes_driver_only_after_start():
    class _Drv(ScriptedDriver):
        closed = False

        async def close(self):
            self.closed = True

    d = _Drv([TurnResult(TurnStatus.IDLE, "hi", False)])
    m = SessionModel(d)
    asyncio.run(m.close())
    assert d.closed is False  # never started: nothing to close
    asyncio.run(m.generate("x"))
    asyncio.run(m.close())
    assert d.closed is True
    asyncio.run(ScriptedDriver([]).close())  # the plain stub's close is a no-op
