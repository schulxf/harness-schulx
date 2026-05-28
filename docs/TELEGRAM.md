# Telegram Guide

Harness Schulx can use Telegram for notifications, inbox messages, Codex
mirroring, queue control and a Codex bridge. In v0.3 Telegram is a
remote-control surface for the local supervisor.

## Setup

Create a bot with BotFather and export the token:

```powershell
$env:HARNESS_TELEGRAM_BOT_TOKEN = "<telegram-bot-token>"
```

Send `/start` to the bot, then discover your chat id:

```powershell
python $HARNESS --repo $APP_REPO telegram listen --once
```

Open the saved JSON in:

```text
.harness/inbox/telegram/
```

Use its `chat_id`:

```powershell
python $HARNESS --repo $APP_REPO telegram configure `
  --enable `
  --chat-id "1832050069" `
  --allowed-chat-id "1832050069"
```

Test outbound messages:

```powershell
python $HARNESS --repo $APP_REPO telegram send "Harness conectado."
```

## Modes

### listen

Receives messages and stores them in the inbox.

```powershell
python $HARNESS --repo $APP_REPO telegram listen
```

Create tasks from messages:

```powershell
python $HARNESS --repo $APP_REPO telegram listen --create-tasks
```

### mirror

Mirrors an active Codex CLI session by reading the newest JSONL transcript in
`~/.codex/sessions`.

```powershell
python $HARNESS --repo $APP_REPO telegram mirror
```

Include tool calls and outputs:

```powershell
python $HARNESS --repo $APP_REPO telegram mirror --include-tools
```

This mode is read-only and does not interrupt the agent.

### codex

Sends Telegram messages to Codex through `codex exec`.

```powershell
python $HARNESS --repo $APP_REPO telegram codex --resume-last
```

This is useful when the Telegram gateway owns the interaction. It does not type
into an already-open Codex TUI.

### bridge

Mirrors a running session and receives Telegram messages in the same process.

```powershell
python $HARNESS --repo $APP_REPO telegram bridge --include-tools
```

Default behavior:

- Codex updates are sent to Telegram.
- Normal Telegram messages are queued in `.harness/telegram/operator-messages.md`.
- `/codex <message>` calls `codex exec resume --last` in parallel.

More aggressive behavior:

```powershell
python $HARNESS --repo $APP_REPO telegram bridge --include-tools --send-mode codex-exec
```

This sends every normal Telegram message to Codex. Avoid it while a long TUI
turn is already running, unless parallel execution is intentional.

## Telegram Commands

```text
/help
/status
/tasks
/pick
/report TASK-001
/new describe a new task
/codex send this to Codex
```

v0.3 installations may also expose:

```text
/queue
/active
/checkpoint
/artifacts TASK-001
/budget
/pause
/resume
/block reason
```

Normal messages should be queued for the operator by default. Use `/codex`
when the intent is to send an active command to Codex.

## Media

Harness can download images, voice messages and audio files into:

```text
.harness/inbox/telegram/media/
```

Optional OpenAI media reading:

```powershell
$env:OPENAI_API_KEY = "<openai-api-key>"
python $HARNESS --repo $APP_REPO telegram configure --openai-media
```

Without `OPENAI_API_KEY`, media is still saved and referenced in the inbox.

## Safety

- Do not commit bot tokens.
- Use `allowed_chat_id`.
- Prefer `bridge` default queue mode during long autonomous work.
- Use `/codex` only when intentional.
- Use `--bypass` only in a trusted environment.
- Treat Telegram as remote control: require explicit chat allowlists and avoid
  exposing secrets, full logs or private artifacts.
- Security scanner findings about Telegram permissions block in `deep` profile
  unless explicitly accepted in the report.
