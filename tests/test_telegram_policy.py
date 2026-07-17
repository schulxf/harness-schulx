from harness_core.telegram_policy import (
    telegram_allowed_chat_ids,
    telegram_chat_allowed,
    telegram_remote_execution_allowed,
)


def test_inbound_chat_allowlist_fails_closed_without_configured_ids():
    assert telegram_allowed_chat_ids({"telegram": {}}) == []
    assert telegram_chat_allowed({"telegram": {}}, "123") is False


def test_chat_ids_are_used_when_allowed_chat_ids_are_empty():
    config = {"telegram": {"chat_ids": [123, "456"], "allowed_chat_ids": []}}

    assert telegram_allowed_chat_ids(config) == ["123", "456"]
    assert telegram_chat_allowed(config, "123") is True
    assert telegram_chat_allowed(config, 456) is True
    assert telegram_chat_allowed(config, "789") is False


def test_allowed_chat_ids_override_notification_chat_ids():
    config = {"telegram": {"chat_ids": ["123"], "allowed_chat_ids": ["456"]}}

    assert telegram_allowed_chat_ids(config) == ["456"]
    assert telegram_chat_allowed(config, "123") is False
    assert telegram_chat_allowed(config, "456") is True


def test_remote_execution_requires_flag_and_effective_allowlist():
    assert telegram_remote_execution_allowed({"telegram": {"chat_ids": ["123"]}}) is False
    assert (
        telegram_remote_execution_allowed(
            {"telegram": {"allow_remote_execution": True, "chat_ids": []}}
        )
        is False
    )
    assert (
        telegram_remote_execution_allowed(
            {"telegram": {"allow_remote_execution": True, "chat_ids": ["123"]}}
        )
        is True
    )
    assert (
        telegram_remote_execution_allowed(
            {"telegram": {"allow_remote_execution": True, "allowed_chat_ids": ["456"]}}
        )
        is True
    )


def test_remote_execution_uses_allowed_chat_ids_override_for_allowlist_presence():
    config = {
        "telegram": {
            "allow_remote_execution": True,
            "chat_ids": ["123"],
            "allowed_chat_ids": ["456"],
        }
    }

    assert telegram_allowed_chat_ids(config) == ["456"]
    assert telegram_remote_execution_allowed(config) is True
