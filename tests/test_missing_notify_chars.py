"""Characteristics a model leaves out of an otherwise present service.

The subscribe list is filtered by service, so a model can still lack single
characteristics inside a service it has. Those are dropped after the first
attempt and reported once in a single warning that names them. Cleaning
progress has two alternative characteristics (0x011A, 0x0318); a model
lacking only one of them is not reported.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from bleak.exc import BleakCharacteristicNotFoundError

from custom_components.philips_shaver.const import (
    CHAR_BATTERY_LEVEL,
    CHAR_CLEANING_PROGRESS,
    CHAR_CLEANING_PROGRESS_CONTROL,
    CHAR_HEAD_REMAINING,
)
from custom_components.philips_shaver.coordinator import PhilipsShaverCoordinator

MISSING = {CHAR_CLEANING_PROGRESS, CHAR_CLEANING_PROGRESS_CONTROL, CHAR_HEAD_REMAINING}


class FakeTransport:
    is_connected = True

    def __init__(self, missing: set[str] = MISSING) -> None:
        self.attempts: list[str] = []
        self.missing = missing

    async def subscribe(self, char_uuid, cb) -> None:
        self.attempts.append(char_uuid)
        if char_uuid in self.missing:
            raise BleakCharacteristicNotFoundError(char_uuid)


def make_coordinator(transport: FakeTransport) -> PhilipsShaverCoordinator:
    coordinator = PhilipsShaverCoordinator.__new__(PhilipsShaverCoordinator)
    coordinator.address = "24:E5:AA:00:00:01"
    coordinator.transport = transport
    coordinator.data = {"model_number": "XP9405", "firmware": "1.3.4"}
    coordinator._notify_chars = [
        CHAR_BATTERY_LEVEL, CHAR_CLEANING_PROGRESS,
        CHAR_CLEANING_PROGRESS_CONTROL, CHAR_HEAD_REMAINING,
    ]
    coordinator._make_live_callback = lambda: (lambda *_: None)
    return coordinator


async def test_missing_chars_reported_once_in_one_line(caplog) -> None:
    transport = FakeTransport()
    coordinator = make_coordinator(transport)

    with caplog.at_level(logging.WARNING):
        assert await coordinator._start_all_notifications() == 1

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "XP9405" in warnings[0]
    assert "firmware 1.3.4" in warnings[0]
    assert "cleaning progress (011A)" in warnings[0]
    assert "cleaning progress control (0318)" in warnings[0]
    assert "head remaining (0117)" in warnings[0]

    # A reconnect neither retries the missing ones nor warns again.
    caplog.clear()
    transport.attempts.clear()
    with caplog.at_level(logging.WARNING):
        assert await coordinator._start_all_notifications() == 1
    assert transport.attempts == [CHAR_BATTERY_LEVEL]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


async def test_other_subscribe_errors_still_warn_per_char(caplog) -> None:
    class FailingTransport(FakeTransport):
        async def subscribe(self, char_uuid, cb) -> None:
            raise TimeoutError("no answer")

    coordinator = make_coordinator(FailingTransport())
    with caplog.at_level(logging.WARNING):
        assert await coordinator._start_all_notifications() == 0

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 4
    assert all(w.startswith("Failed to subscribe") for w in warnings)
    assert len(coordinator._notify_chars) == 4


async def test_one_cleaning_progress_source_is_enough(caplog) -> None:
    # The XP line has 0x011A but not 0x0318: dropped silently.
    transport = FakeTransport(missing={CHAR_CLEANING_PROGRESS_CONTROL})
    coordinator = make_coordinator(transport)

    with caplog.at_level(logging.WARNING):
        assert await coordinator._start_all_notifications() == 3

    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
    assert CHAR_CLEANING_PROGRESS_CONTROL not in coordinator._notify_chars
    assert CHAR_CLEANING_PROGRESS in coordinator._notify_chars
