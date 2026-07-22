from __future__ import annotations

import re
from pathlib import Path

from .defaults import SECRET_PATTERNS
from .evaluation_text import plain_clean, plain_key
from .paths import harness_root, security_root, to_posix
from .run_state import latest_run_dir_or_none
from .storage import read_json, read_text
from .task_store import find_task

CLI_COMMENT_MARKER = "<!-- harness-simple-pr-summary -->"
PUBLIC_SUMMARY_LIMIT = 3500
COMMAND_PREFIX_RE = re.compile(
    r"^\s*(?:(?:[-*+]|\d+[.)])\s+)?"
    r"(?:(?:PS\s+[^>\r\n]*>|[A-Za-z]:\\[^>\r\n]*>|"
    r"[\w.-]+@[\w.-]+:[^$#\r\n]*[$#]|[$#>])\s*)?",
    re.IGNORECASE,
)
RAW_COMMAND_RE = re.compile(
    r"^(?:python(?:\s+-m)?|pytest|npx|npm|pnpm|yarn|bun|node|deno|"
    r"git|gh|ruff|mypy|uv|pip|pipx|poetry|docker(?:-compose)?|kubectl|"
    r"curl|wget|pwsh|powershell|cmd|bash|sh|cargo|dotnet|java|mvn|gradle)\b",
    re.IGNORECASE,
)
FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
PUBLIC_SENSITIVE_PATTERNS = (
    re.compile(r"https?://[^\s<>)]+(?:recovery|access_token|refresh_token|token)[^\s<>)]+", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bsbp_[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    re.compile(
        r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?)\b"
        r"\s*[:=]\s*['\"]?[^\s'\";,]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE),
)
PUBLIC_SUMMARY_SECTIONS = {
    "o que foi feito",
    "resultado",
    "o que ficou pendente",
}


def redact_known_secrets(text: str) -> str:
    redacted = PRIVATE_KEY_BLOCK_RE.sub("[segredo redigido]", text)
    for _kind, pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[segredo redigido]", redacted)
    for pattern in PUBLIC_SENSITIVE_PATTERNS:
        redacted = pattern.sub("[conteúdo sensível redigido]", redacted)
    return redacted


def remove_fenced_code_blocks(text: str) -> str:
    visible_lines: list[str] = []
    fence_character: str | None = None
    for line in (text or "").splitlines():
        match = FENCE_LINE_RE.match(line)
        if match:
            current_character = match.group(1)[0]
            if fence_character is None:
                fence_character = current_character
            elif current_character == fence_character:
                fence_character = None
            continue
        if fence_character is None:
            visible_lines.append(line)
    return "\n".join(visible_lines)


def sanitize_public_pr_text(text: str, *, limit: int = PUBLIC_SUMMARY_LIMIT) -> str:
    redacted = redact_known_secrets(remove_fenced_code_blocks(text))
    lines: list[str] = []
    for line in redacted.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1]:
                lines.append("")
            continue
        command_candidate = COMMAND_PREFIX_RE.sub("", stripped, count=1)
        if RAW_COMMAND_RE.match(command_candidate):
            continue
        if plain_key(stripped).startswith("observacao simples:"):
            continue
        if stripped.startswith("```"):
            continue
        lines.append(stripped)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit].rsplit("\n", 1)[0].strip()
    return f"{truncated}\n\n[resumo encurtado pelo limite público]"


def plain_summary_for_task(root: Path, task_id: str) -> str:
    run_dir = latest_run_dir_or_none(root, task_id)
    plain_path = run_dir / "plain-summary.md" if run_dir else None
    plain = read_text(plain_path) if plain_path and plain_path.exists() else ""
    simple_summary = public_plain_summary_sections(plain) if plain else ""
    return simple_summary or "Resumo simples ainda não gerado."


def public_plain_summary_sections(summary: str) -> str:
    summary = remove_fenced_code_blocks(summary or "")
    lines: list[str] = []
    in_public_section = False
    for line in summary.splitlines():
        if line.startswith("## "):
            heading = plain_key(line.lstrip("#").strip())
            in_public_section = heading in PUBLIC_SUMMARY_SECTIONS
            if in_public_section:
                lines.append(f"{line.lstrip('#').strip()}:")
            continue
        if not in_public_section:
            continue
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1]:
                lines.append("")
            continue
        if plain_key(stripped).startswith("observacao simples:"):
            continue
        lines.append(stripped)

    cleaned = "\n".join(lines).strip()
    if cleaned:
        return cleaned
    fallback = re.sub(r"^\s*# [^\n]*\n+", "", summary, count=1).strip()
    return sanitize_public_pr_text(fallback) if fallback else ""


def evaluation_gaps(root: Path, task_id: str) -> list[str]:
    run_dir = latest_run_dir_or_none(root, task_id)
    evaluation = read_json(run_dir / "evaluation.json", {}) if run_dir else {}
    return [plain_clean(item) for item in evaluation.get("gaps", []) if plain_clean(item)]


def automatic_pr_comment_enabled(root: Path) -> bool:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return False
    workflow_paths = [*workflows.glob("*.yml"), *workflows.glob("*.yaml")]
    return any(CLI_COMMENT_MARKER in read_text(path) for path in workflow_paths if path.is_file())


def render_github_pr_body(root: Path, task_id: str) -> str:
    task = find_task(root, task_id)
    task_title = sanitize_public_pr_text(plain_clean(task.get("title") or task_id), limit=200)
    report_path = harness_root(root) / "reports" / f"{task_id}.md"
    run_dir = latest_run_dir_or_none(root, task_id)
    sensors = read_json(run_dir / "sensors.json", {}) if run_dir else {}
    run_security_path = run_dir / "security-scan.json" if run_dir else None
    global_security_path = security_root(root) / "scan-latest.json"
    if run_security_path and run_security_path.exists():
        security = read_json(run_security_path, {})
    else:
        security = read_json(global_security_path, {})
    ptbr_review = read_json(run_dir / "ptbr-review.json", {}) if run_dir else {}
    simple_summary = sanitize_public_pr_text(plain_summary_for_task(root, task_id), limit=1000)
    check_lines = [
        "As conferências automáticas passaram."
        if sensors.get("passed")
        else "As conferências automáticas ainda não passaram.",
        "A verificação de segurança não encontrou segredos."
        if security and not security.get("findings")
        else "A verificação de segurança ainda precisa ser concluída.",
        "Os textos em PT-BR foram revisados."
        if ptbr_review.get("status") == "pass"
        else "A revisão dos textos em PT-BR ainda precisa ser concluída.",
    ]
    gaps = evaluation_gaps(root, task_id)
    pending_items = [sanitize_public_pr_text(gap, limit=250) for gap in gaps[:3]]
    if len(gaps) > 3:
        pending_items.append("Outras pendências constam na avaliação completa.")
    pending = "\n".join(f"- {item}" for item in pending_items) if pending_items else "Nenhuma."
    if security:
        finding_count = len(security.get("findings") or [])
        security_line = f"{finding_count} {'achado' if finding_count == 1 else 'achados'}"
    else:
        security_line = "não executada"
    ptbr_checkbox = "x" if ptbr_review.get("status") == "pass" else " "
    return (
        f"# {task_id} - {task_title}\n\n"
        "## Resumo simples\n\n"
        f"{simple_summary}\n\n"
        "## Como conferi\n\n"
        f"{' '.join(check_lines)}\n\n"
        "## Pendências\n\n"
        f"{pending}\n\n"
        "## Checklist\n\n"
        f"- [{ptbr_checkbox}] Revisei ortografia, acentuação e clareza dos textos em PT-BR.\n\n"
        "## Evidência Harness\n\n"
        f"- Status da tarefa: {task.get('status')}\n"
        f"- Verificação de segurança: {security_line}\n"
        f"- Relatório: `{to_posix(report_path.relative_to(root)) if report_path.exists() else 'pendente'}`\n"
    )


def render_github_pr_comment(root: Path, task_id: str) -> str:
    summary = sanitize_public_pr_text(plain_summary_for_task(root, task_id), limit=2200)
    gaps = evaluation_gaps(root, task_id)
    pending_items = [sanitize_public_pr_text(gap, limit=250) for gap in gaps[:3]]
    if len(gaps) > 3:
        pending_items.append("Outras pendências constam na avaliação completa.")
    pending = "\n".join(f"- {item}" for item in pending_items) if pending_items else "Nenhuma."
    return (
        f"{CLI_COMMENT_MARKER}\n"
        "## Resumo simples\n\n"
        f"{summary}\n\n"
        "## Pendências\n\n"
        f"{pending}\n\n"
        "_Comentário gerado pelo Harness a partir do resumo simples revisado em PT-BR._\n"
    )
