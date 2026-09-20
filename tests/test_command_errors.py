"""Tests for user-facing SPC control-command errors."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError
from spcedp import PanelRejected
from spcedp.errors import ReplyCode

from custom_components.spc_edp.commands import _rejection_message, async_run_command


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (ReplyCode.INVALID_PARAMS, "invalid command parameters"),
        (ReplyCode.PANEL_WAITING, "busy waiting for data"),
        (ReplyCode.PANEL_ENGINEER, "full engineer mode"),
        (ReplyCode.NOT_POSSIBLE_NOW, "current state"),
        (ReplyCode.NOT_PERMITTED, "EDP receiver"),
        (ReplyCode.NOT_IMPLEMENTED_PANEL, "panel command channel"),
    ],
)
def test_known_reply_codes_have_actionable_messages(
    code: ReplyCode, expected: str
) -> None:
    """Each known panel rejection explains what the user can do next."""
    message = _rejection_message(PanelRejected(code), "testing the command")
    assert expected in message


def test_not_implemented_arm_reply_explains_engineer_mode() -> None:
    """SPC4300 reports engineer-mode arm blocks as 0xFC."""
    message = _rejection_message(
        PanelRejected(ReplyCode.NOT_IMPLEMENTED),
        "arming this area away",
        engineer_mode_possible=True,
    )
    assert "engineer mode" in message
    assert "0xFC" in message


@pytest.mark.asyncio
async def test_command_wrapper_raises_home_assistant_error() -> None:
    """Protocol errors must not leak raw EDP text to the service caller."""

    async def reject() -> None:
        raise PanelRejected(ReplyCode.NOT_PERMITTED)

    with pytest.raises(HomeAssistantError, match="EDP receiver"):
        await async_run_command(reject(), "testing the command")


async def test_transport_failure_is_a_home_assistant_error() -> None:
    from spcedp import SpcTimeout

    async def timeout():
        raise SpcTimeout("no reply")

    with pytest.raises(HomeAssistantError, match="no reply"):
        await async_run_command(timeout(), "arming this area")
