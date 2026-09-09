import asyncio

import pytest

from flowbench.model import SessionModel
from flowbench.runner.driver import TurnResult
from flowbench.testing import ScriptedDriver
from flowbench.types import TurnStatus


def test_generate_idle_path_single_send():
    driver = ScriptedDriver([TurnResult(TurnStatus.IDLE, "ok", False)])
    model = SessionModel(driver)
    out = asyncio.run(model.generate("x"))
    assert out.completion == "ok"
    assert len(driver.sent) == 1


def test_generate_accepts_a_flaked_idle_turn():
    # the driver already resolved row 2 (FAILED-after-reply-landed) to IDLE with
    # flaked=True; generate trusts it like any other idle turn (S02.3)
    driver = ScriptedDriver([TurnResult(TurnStatus.IDLE, "the reply", False, flaked=True)])
    model = SessionModel(driver)
    out = asyncio.run(model.generate("x"))
    assert out.completion == "the reply"
    assert len(driver.sent) == 1


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (TurnStatus.TIMEOUT, "fresh but untrusted"),
        (TurnStatus.FAILED, ""),
        (TurnStatus.FAILED, "some text"),
        (TurnStatus.STALLED, ""),
    ],
)
def test_generate_raises_on_non_idle_without_retry(status, text):
    # the driver owns retry policy end-to-end; generate never re-sends
    driver = ScriptedDriver([TurnResult(status, text, False)])
    model = SessionModel(driver)
    with pytest.raises(RuntimeError, match=str(status.value)):
        asyncio.run(model.generate("x"))
    assert len(driver.sent) == 1


@pytest.mark.parametrize("text", ["", "  \n"])
def test_generate_raises_on_empty_idle_text(text):
    # NEW guard (S02.3): pre-S02.3 generate returned an empty completion here —
    # an idle result the driver hands back should always carry new non-empty
    # text by construction, so this fires only if that invariant breaks
    driver = ScriptedDriver([TurnResult(TurnStatus.IDLE, text, False)])
    model = SessionModel(driver)
    with pytest.raises(RuntimeError, match="no reply"):
        asyncio.run(model.generate("x"))
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
