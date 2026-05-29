"""Hub HTTP authorization helpers."""

from __future__ import annotations


def hub_local_request_allowed(client_host: str) -> bool:
    return client_host in {"127.0.0.1", "::1", "localhost"}


def hub_action_authorized(client_host: str, supplied_token: str, action_token: str) -> bool:
    return hub_local_request_allowed(client_host) and bool(action_token and supplied_token == action_token)
