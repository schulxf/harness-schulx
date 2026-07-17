from __future__ import annotations

from pathlib import Path

from harness_core import codex_exec


def test_codex_prompt_uses_telegram_metadata_and_text() -> None:
    prompt = codex_exec.codex_prompt_from_item(
        {"chat_id": "123", "message_id": 10, "prompt_text": "Arrumar bug"}
    )

    assert "Mensagem recebida via Telegram pelo Harness." in prompt
    assert "Chat: 123" in prompt
    assert "Mensagem: 10" in prompt
    assert prompt.endswith("Arrumar bug")


def test_codex_prompt_mentions_attached_file_when_missing_from_text() -> None:
    prompt = codex_exec.codex_prompt_from_item(
        {
            "chat_id": "123",
            "message_id": 10,
            "prompt_text": "Veja a imagem",
            "media": {"local_path": "uploads/image.png"},
        }
    )

    assert "Arquivo anexado salvo em: uploads/image.png" in prompt


def test_codex_image_args_only_include_existing_image(tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"png")

    assert codex_exec.codex_image_args_from_item({"kind": "image", "media": {"local_path": str(image)}}) == [
        "-i",
        str(image),
    ]
    assert codex_exec.codex_image_args_from_item({"kind": "audio", "media": {"local_path": str(image)}}) == []
    assert codex_exec.codex_image_args_from_item({"kind": "image", "media": {"local_path": str(tmp_path / "x.png")}}) == []


def test_build_codex_exec_argv_new_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(codex_exec.shutil, "which", lambda _: "codex")
    out = tmp_path / "out.txt"
    argv = codex_exec.build_codex_exec_argv(
        tmp_path,
        out,
        model="gpt-5",
        sandbox="workspace-write",
        approval="never",
        images=["image.png"],
    )

    assert argv[:4] == ["codex", "exec", "-C", str(tmp_path)]
    assert "--skip-git-repo-check" in argv
    assert ["-m", "gpt-5"] == argv[argv.index("-m") : argv.index("-m") + 2]
    assert ["-i", "image.png"] == argv[argv.index("-i") : argv.index("-i") + 2]
    assert argv[-2:] == [str(out), "-"]


def test_build_codex_exec_argv_resume_last(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(codex_exec.shutil, "which", lambda _: "codex")
    out = tmp_path / "out.txt"
    argv = codex_exec.build_codex_exec_argv(tmp_path, out, resume_last=True)

    assert argv[:4] == ["codex", "exec", "resume", "--last"]
    assert "-C" not in argv
    assert argv[-2:] == [str(out), "-"]
