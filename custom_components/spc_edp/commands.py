"""Translate panel rejections and connection failures into Home Assistant errors."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError
from spcedp import PanelRejected, SpcError
from spcedp.errors import ReplyCode


def _rejection_message(
    error: PanelRejected, action: str, *, engineer_mode_possible: bool = False
) -> str:
    """Turn an EDP reply code into an actionable Home Assistant error."""
    code = error.code
    if code == ReplyCode.INVALID_PARAMS:
        return f"The SPC panel rejected {action}: invalid command parameters. No action was taken."
    if code == ReplyCode.PANEL_WAITING:
        return f"The SPC panel is busy waiting for data. Wait a few seconds, then retry {action}."
    if code == ReplyCode.PANEL_ENGINEER:
        return (
            "The SPC panel is in full engineer mode. "
            f"Exit engineer mode at the panel, then retry {action}."
        )
    if code == ReplyCode.NOT_POSSIBLE_NOW:
        return f"The SPC panel cannot perform {action} in its current state. No action was taken."
    if code == ReplyCode.NOT_PERMITTED:
        return (
            f"The SPC panel does not permit {action} for this EDP receiver. "
            "Check the panel's EDP permissions."
        )
    if code == ReplyCode.NOT_IMPLEMENTED:
        if engineer_mode_possible:
            return (
                f"The SPC panel rejected {action}. This firmware reports 0xFC while "
                "it is in engineer mode; exit engineer mode at the panel and retry."
            )
        return f"The SPC panel firmware does not implement {action} (reply code 0xFC)."
    return (
        f"The SPC panel rejected {action} (reply code {code:#04x}). "
        "Check open zones and the panel's status before retrying."
    )


async def async_run_command(
    operation: Awaitable[None], action: str, *, engineer_mode_possible: bool = False
) -> None:
    """Run one panel control command with a user-facing protocol error."""
    try:
        await operation
    except PanelRejected as error:
        raise HomeAssistantError(
            _rejection_message(error, action, engineer_mode_possible=engineer_mode_possible)
        ) from error
    except SpcError as error:
        raise HomeAssistantError(f"Error {action}: {error}") from error
