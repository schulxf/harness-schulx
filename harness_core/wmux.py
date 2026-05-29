"""wmux bridge helpers used by the dashboard hub."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any


def wmux_pipe_path() -> str:
    return os.environ.get("WMUX_PIPE") or (r"\\.\pipe\wmux" if os.name == "nt" else "")


def wmux_cli_path() -> str:
    cli = os.environ.get("WMUX_CLI", "")
    if cli and Path(cli).exists():
        return cli
    found = shutil.which("wmux")
    if found:
        return found
    if os.name == "nt":
        downloads = Path.home() / "Downloads"
        try:
            matches = sorted(
                downloads.glob("wmux-*-win-x64/resources/cli/wmux.js"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            matches = []
        if matches:
            return str(matches[0])
    return ""


def wmux_pipe_exchange(payload: bytes, max_bytes: int = 1024 * 1024) -> tuple[bool, str]:
    pipe = wmux_pipe_path()
    if not pipe:
        return False, "wmux pipe nao configurado."
    try:
        with open(pipe, "r+b", buffering=0) as handle:  # noqa: PTH123 - Windows named pipe.
            handle.write(payload + b"\n")
            data = b""
            while b"\n" not in data and len(data) < max_bytes:
                chunk = handle.read(4096)
                if not chunk:
                    break
                data += chunk
    except OSError as exc:
        return False, str(exc)
    return True, data.decode("utf-8", errors="replace").strip()


def wmux_send_v1(command: str) -> dict[str, Any]:
    ok, raw = wmux_pipe_exchange(command.encode("utf-8"))
    return {"ok": ok, "text": raw if ok else "", "error": "" if ok else raw}


def wmux_send_v2(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    request = json.dumps({"method": method, "params": params or {}, "id": 1}).encode("utf-8")
    ok, raw = wmux_pipe_exchange(request)
    if not ok:
        return {"ok": False, "error": raw, "result": None}
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": raw or "resposta invalida do wmux.", "result": None}
    if response.get("error"):
        error = response["error"]
        if isinstance(error, dict):
            error = error.get("message") or json.dumps(error, ensure_ascii=False)
        return {"ok": False, "error": str(error), "result": response}
    return {"ok": True, "error": "", "result": response.get("result")}


def wmux_command_hint() -> str:
    cli = wmux_cli_path()
    if not cli:
        return "wmux"
    if cli.endswith(".js"):
        node = shutil.which("node") or "node"
        return f'{node} "{cli}"'
    return cli


def extract_wmux_surface_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ["surfaceId", "surface_id", "id"]:
            found = value.get(key)
            if found and (key != "id" or value.get("type") == "terminal"):
                return str(found)
        for key in ["surface", "newSurface", "pane"]:
            found = extract_wmux_surface_id(value.get(key))
            if found:
                return found
        for key in ["surfaces", "newSurfaces"]:
            surfaces = value.get(key)
            if isinstance(surfaces, list):
                for surface in surfaces:
                    found = extract_wmux_surface_id(surface)
                    if found:
                        return found
    if isinstance(value, list):
        for item in value:
            found = extract_wmux_surface_id(item)
            if found:
                return found
    return ""


def ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def collect_wmux_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "available": False,
        "pipe": wmux_pipe_path(),
        "cli": wmux_cli_path(),
        "command": wmux_command_hint(),
        "surface_id": os.environ.get("WMUX_SURFACE_ID", ""),
        "panes": [],
        "surfaces": [],
        "agents": [],
        "tree": {},
        "error": "",
    }
    ping = wmux_send_v1("ping")
    if not ping.get("ok") or str(ping.get("text") or "").strip() != "pong":
        state["error"] = str(ping.get("error") or ping.get("text") or "wmux nao respondeu.")
        return state

    state["available"] = True
    for key, method in [
        ("panes", "pane.list"),
        ("surfaces", "surface.list"),
        ("agents", "agent.list"),
        ("tree", "system.tree"),
    ]:
        response = wmux_send_v2(method, {})
        if not response.get("ok"):
            state.setdefault("warnings", []).append({"method": method, "error": response.get("error")})
            continue
        result = response.get("result") or {}
        if key == "tree":
            state[key] = result.get("tree", result) if isinstance(result, dict) else result
        elif isinstance(result, dict):
            state[key] = result.get(key, result.get(key.rstrip("s"), []))
        else:
            state[key] = result
    return state


def wmux_focus(payload: dict[str, Any]) -> dict[str, Any]:
    surface_id = str(payload.get("surface_id") or payload.get("surfaceId") or "")
    pane_id = str(payload.get("pane_id") or payload.get("paneId") or "")
    if surface_id:
        response = wmux_send_v2("surface.focus", {"id": surface_id})
    elif pane_id:
        response = wmux_send_v2("pane.focus", {"id": pane_id})
    else:
        return {"ok": False, "error": "Informe surface_id ou pane_id."}
    return {"ok": bool(response.get("ok")), "error": response.get("error", ""), "result": response.get("result")}


def wmux_send_text(payload: dict[str, Any]) -> dict[str, Any]:
    surface_id = str(payload.get("surface_id") or payload.get("surfaceId") or os.environ.get("WMUX_SURFACE_ID", ""))
    text = str(payload.get("text") or "")
    enter = bool(payload.get("enter", True))
    if not text and not enter:
        return {"ok": False, "error": "Nada para enviar."}

    results: dict[str, Any] = {}
    ok = True
    if text:
        params: dict[str, Any] = {"text": text}
        if surface_id:
            params["surfaceId"] = surface_id
        response = wmux_send_v2("surface.send_text", params)
        results["send"] = response
        ok = ok and bool(response.get("ok"))
    if enter:
        params = {"key": "Enter", "modifiers": []}
        if surface_id:
            params["surfaceId"] = surface_id
        response = wmux_send_v2("surface.send_key", params)
        results["enter"] = response
        ok = ok and bool(response.get("ok"))
    return {"ok": ok, "surface_id": surface_id, "result": results}


def wmux_read_screen(payload: dict[str, Any]) -> dict[str, Any]:
    surface_id = str(payload.get("surface_id") or payload.get("surfaceId") or os.environ.get("WMUX_SURFACE_ID", ""))
    lines = int(payload.get("lines") or 80)
    params: dict[str, Any] = {"lines": lines}
    if surface_id:
        params["surfaceId"] = surface_id
    response = wmux_send_v2("surface.read_text", params)
    if not response.get("ok"):
        return {"ok": False, "error": response.get("error") or "Nao foi possivel ler a tela wmux."}
    result = response.get("result") or {}
    text = result.get("text") if isinstance(result, dict) else str(result or "")
    note = result.get("note") if isinstance(result, dict) else ""
    return {"ok": True, "surface_id": surface_id, "text": text or "", "note": note or ""}


def wmux_new_terminal(payload: dict[str, Any]) -> dict[str, Any]:
    cwd = str(payload.get("cwd") or payload.get("root") or "")
    direction = str(payload.get("direction") or "down")
    if direction not in {"down", "right"}:
        direction = "down"
    split = wmux_send_v2("pane.split", {"direction": direction, "type": "terminal"})
    if not split.get("ok"):
        return {"ok": False, "error": split.get("error"), "split": split}

    surface_id = extract_wmux_surface_id(split.get("result"))
    cd_result = None
    if cwd and surface_id:
        time.sleep(0.2)
        cd_result = wmux_send_text(
            {
                "surface_id": surface_id,
                "text": f"Set-Location -LiteralPath {ps_single_quote(cwd)}",
                "enter": True,
            }
        )
    return {
        "ok": True,
        "surface_id": surface_id,
        "split": split.get("result"),
        "cd": cd_result,
    }
