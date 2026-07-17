from __future__ import annotations

from harness_core.hub_auth import hub_action_authorized, hub_local_request_allowed


def test_hub_local_request_allowed_only_accepts_loopback_hosts() -> None:
    assert hub_local_request_allowed("127.0.0.1") is True
    assert hub_local_request_allowed("::1") is True
    assert hub_local_request_allowed("localhost") is True
    assert hub_local_request_allowed("192.168.0.10") is False


def test_hub_action_authorized_requires_loopback_and_token_match() -> None:
    assert hub_action_authorized("127.0.0.1", "token", "token") is True
    assert hub_action_authorized("127.0.0.1", "", "token") is False
    assert hub_action_authorized("192.168.0.10", "token", "token") is False
