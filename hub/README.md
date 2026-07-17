# Harness Hub

Optional realtime pixel hub for Harness projects.

The Python CLI remains the source of truth for tasks, events, queues, and agent
records. This Node sidecar serves the browser client, streams events, and owns
live PTY terminal sessions.

## Install

```powershell
cd hub
npm install
```

## Enable Agent Spawning

Spawning a terminal-backed agent is remote code execution by design, so it is
blocked until a repo explicitly enables the hub gate:

```powershell
python ..\bin\harness.py --repo C:\path\to\repo dashboard hub-configure --allow-remote-execution
```

To disable it again:

```powershell
python ..\bin\harness.py --repo C:\path\to\repo dashboard hub-configure --block-remote-execution
```

## Run

```powershell
cd hub
$env:HARNESS_HUB_TOKEN = "local-dev-token"
npm start -- --repo C:\path\to\repo --port 8899 --token $env:HARNESS_HUB_TOKEN
```

Open:

```text
http://127.0.0.1:8899/?token=local-dev-token
```

The token is required for mutable actions and terminal WebSocket attachment.
The server binds to `127.0.0.1` by default.

## Endpoints

- `GET /` serves `hub/client`.
- `GET /api/world` returns the current repo/world snapshot.
- `GET /api/events?offset=N` streams events with SSE.
- `POST /api/agents/spawn` starts a PTY and registers the agent through Python.
- `POST /api/agents/:id/message` records an agent-to-agent message through Python.
- `POST /api/agents/:id/kill` stops the PTY and marks the agent stopped through Python.
- `POST /api/repos/add` adds another Harness repo to the hub registry.
- `WS /ws/term?agent=<id>&token=<token>` attaches to an agent terminal.

## Validate

```powershell
cd hub
npm run check
npm test
```

The browser client modules are plain ES modules and can be checked with:

```powershell
Get-ChildItem client\src -Filter *.js | ForEach-Object { node --check $_.FullName }
```

