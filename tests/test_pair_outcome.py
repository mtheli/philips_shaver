"""The bridge's pair outcome maps to one error translation key.

Pure logic, no HA plumbing — the branch that matters is that the
passive-scanner diagnosis is reserved for a genuine timeout. A pair_failed
means a shaver was found and bonding failed, so it must never claim "the
bridge scanned passively and could never have seen it", even if a future
firmware attached the scanner_passive field to that outcome.
"""

from __future__ import annotations

import pytest

from custom_components.philips_shaver.config_flow import PhilipsShaverConfigFlow

_map = PhilipsShaverConfigFlow._pair_outcome_error_key


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "pair_timeout"}, "pair_timeout"),
        ({"status": "pair_timeout", "scanner_passive": "false"}, "pair_timeout"),
        (
            {"status": "pair_timeout", "scanner_passive": "true"},
            "pair_timeout_passive_scanner",
        ),
        (
            {"status": "pair_failed", "reason": "auth_max_failures"},
            "pair_failed_stale_bond",
        ),
        ({"status": "pair_failed", "reason": "other"}, "pair_timeout"),
        # A pair_failed that somehow carried scanner_passive must still NOT get
        # the passive text — a shaver was found, the passive diagnosis is wrong.
        (
            {"status": "pair_failed", "scanner_passive": "true"},
            "pair_timeout",
        ),
    ],
)
def test_pair_outcome_error_key(result, expected) -> None:
    assert _map(result) == expected
