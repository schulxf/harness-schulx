# Plano de Design — Hub Pixel-Art com Agentes Vivos

> Documento de design/implementação para transformar o `dashboard hub` atual
> (HTML+CSS gerado por `render_dashboard_hub_html`) em um jogo top-down pixel-art
> onde cada repo é um mapa, agentes são personagens que andam até o setor da
> tarefa, e cada agente é uma sessão de LLM via CLI com terminal embutido
> (xterm.js + PTY). Destinado a ser executado por um agente implementador.

Versão do plano: 1.0 · Alvo: Harness v0.4 · Plataforma primária: Windows 11 + wmux.

---

## 1. Decisões fixadas

| Tema | Decisão |
|---|---|
| Terminais | **Embutidos**: xterm.js no cliente + backend PTY próprio (não depender do wmux) |
| Backend realtime | **Sidecar Node (`harness-hub`)** via `node-pty`/ConPTY; core Python segue zero-dep |
| Engine de render | **Kaplay** (jogo 2D top-down, vendorizado no cliente) |
| CLI dos agentes | **Multi-CLI configurável**: Codex e Claude Code, escolhível por agente/profile |
| Acesso a estado | Node **lê** `.harness/*.json` direto; **muta** via CLI Python — e escritas do Python passam a ser **atômicas** (tmp + `os.replace`) |
| Persistência PTY | Sessões **morrem no restart** do hub (v1); agentes marcados `offline`. Sem daemon |
| Arte/assets | **Kenney (CC0)** — tilesets variados, **1 tema de mapa por repo**; sem custo nem atribuição obrigatória (registramos mesmo assim em `LICENSES.md`) |
| Entrega | Sistemas + fluxo, com visual pixel-art licenciado a partir do M1 |

---

## 2. Princípio arquitetural

**Backend "burro" de estado · Cliente "esperto" de jogo.**

- O **Python CLI (`bin/harness.py`)** continua a **fonte da verdade** do domínio
  (tasks, contratos, fila, registry de agentes, `events.jsonl`). Ele **não**
  calcula pixels nem animação.
- Um **servidor Node (`harness-hub`)** novo cuida da camada *realtime*: serve o
  cliente Kaplay, faz streaming de estado (SSE) e de terminais (WebSocket + PTY),
  e proxia ações para o Python.
- O **cliente Kaplay** é o jogo: tilemap, sprites, pathfinding, painéis,
  terminais xterm.js. Recebe **estado semântico** ("agente no setor `build`,
  status `working`") e anima sozinho.

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser (painel do wmux ou aba normal)                            │
│  ┌──────────────────────────┐   ┌────────────────────────────┐   │
│  │ Cliente Kaplay (jogo 2D)  │   │ Overlays xterm.js (terminais)│  │
│  │  tilemap · sprites · A*    │◀─▶│  1 por agente, ao vivo        │  │
│  └─────────────┬────────────┘   └──────────────┬─────────────┘   │
└────────────────┼───────────────────────────────┼─────────────────┘
        SSE estado│ + POST ações          WS terminal│ (input/output)
┌────────────────▼───────────────────────────────▼─────────────────┐
│ harness-hub (Node)                                                │
│  static · /api/world · SSE /api/events · WS /ws/term              │
│  PTY manager (node-pty) · proxy de ações → Python CLI            │
└───────────┬───────────────────────────────────┬──────────────────┘
   lê arquivos│ (.harness/*.json, events.jsonl)  │ shell-out p/ mutações
┌────────────▼───────────────────────────────────▼──────────────────┐
│ bin/harness.py (engine de domínio) + .harness/ (estado em arquivo) │
└────────────────────────────────────────────────────────────────────┘
```

**Regra de acesso a estado (importante para não duplicar lógica):**
- **Leituras** (snapshot/poll): o Node lê os arquivos JSON de `.harness/`
  diretamente (rápido, sem subprocess). Os formatos são estáveis e simples.
- **Mutações** (spawn, register, heartbeat, queue, etc.): o Node **chama o CLI
  Python** (`python bin/harness.py ...`) para que toda validação/segurança fique
  num lugar só. Exceção: o ciclo de vida do PTY é do Node.

---

## 3. Contratos de dados

### 3.1 Registry de agente (estender `upsert_agent`, `harness.py:1021`)

Campos atuais: `id, created_at, name, role, state, status, task_id, task_title,
phase, speech, run_dir, surface_id, last_event_id, heartbeat_at, updated_at`.

Adicionar:

```jsonc
{
  "cli": "codex",                 // "codex" | "claude" — qual LLM roda no PTY
  "sector": "implement",          // zona lógica (ver tabela §5)
  "pty_id": "pty-ab12",           // id da sessão PTY no Node (ou "")
  "repo_root": "C:/proj/app",     // a qual mapa/repo o agente pertence
  "cwd": "C:/proj/app",           // diretório de trabalho do processo
  "transcript_path": ".harness/agents/<id>/transcript.jsonl",
  "spawned_by": "ui"              // "ui" | "event" | "supervisor"
}
```

> Posição em pixels é do **cliente** (ele faz o pathfinding). O backend guarda só
> `sector`. Assim o backend não vira motor de física.

### 3.2 Eventos novos (reusar `append_harness_event`, `harness.py:930`)

| `type` | payload chave | uso no jogo |
|---|---|---|
| `agent_spawned` | `agent_id, role, cli, repo_root` | cria sprite |
| `agent_sector_changed` | `agent_id, sector` | dispara caminhada |
| `agent_message` | `from_agent, to_agent, text` | encontro + balão |
| `agent_terminal_attached` | `agent_id, pty_id` | habilita "ver terminal" |
| `agent_killed` | `agent_id` | remove sprite |

### 3.3 Config do hub (novo bloco em `config.json`)

```jsonc
"hub": {
  "allow_remote_execution": false,   // GATE de spawn (ver §8) — hoje é flag morta
  "max_agents": 8,
  "default_cli": "codex",
  "clis": {
    "codex":  { "cmd": ["codex"],  "args": [] },
    "claude": { "cmd": ["claude"], "args": [] }
  },
  "pty": { "idle_timeout_s": 1800, "scrollback_bytes": 262144 }
}
```

> Reaproveita o achado do audit: `allow_remote_execution` existe em
> `DEFAULT_TELEGRAM_CONFIG` (`harness.py:174`) mas **nunca é lido**. Agora ele
> ganha função real como gate do spawn de agentes.

---

## 4. Servidor `harness-hub` (Node) — endpoints

Todos os endpoints **mutáveis** e o **WS** exigem: origem loopback
(`127.0.0.1`/`::1`) **e** header `X-Harness-Hub-Token` igual ao token gerado no
boot (mesmo padrão de `HubHandler.authorized`, `harness.py:5840`).

| Método | Rota | Função |
|---|---|---|
| `GET` | `/` + `/assets/*` | cliente Kaplay (estático) |
| `GET` | `/api/world` | snapshot: repos[], agents[], setores por mapa |
| `GET` | `/api/events?offset=N` | **SSE**: novos eventos (tail incremental do `events.jsonl`) |
| `WS` | `/ws/term?agent=<id>` | I/O do terminal PTY do agente |
| `POST` | `/api/agents/spawn` | `{repo, role, cli, name?}` → cria PTY + registra agente |
| `POST` | `/api/agents/:id/message` | `{to, text}` → emite `agent_message` |
| `POST` | `/api/agents/:id/kill` | encerra PTY + `agent_killed` |
| `POST` | `/api/repos/add` | `{path}` → `hub-add-repo` (+ `init` se preciso) |

**SSE**: reusar `read_new_harness_events(offset)` (`harness.py:977`) — já lê por
offset. O Node mantém o offset por conexão e empurra deltas. Isso elimina o
*polling* de 3s e o achado de performance do audit (hoje cada poll relê o
`events.jsonl` inteiro e varre todas as runs).

**Protocolo do WS de terminal** (frames JSON):

```jsonc
// cliente → servidor
{ "type": "input",  "data": "ls\n" }
{ "type": "resize", "cols": 120, "rows": 30 }
// servidor → cliente
{ "type": "output", "data": "..." }   // chunk do PTY
{ "type": "exit",   "code": 0 }
```

---

## 5. Mapeamento tarefa → setor

O agente caminha até a zona correspondente ao que está fazendo.

| Setor (key) | Zona no mapa | Disparado por |
|---|---|---|
| `plan` | Cabana de Planejamento | role planner; `contract` criado |
| `implement` | Forja | role builder; `start`/`run_started`, `sensors_*` |
| `review` | Biblioteca | role reviewer; `evaluation_brief_created` |
| `research` | Torre de Pesquisa | role research; skill de pesquisa |
| `security` | Torre de Vigia | role security; `security scan`, findings |
| `report` | Arquivo/Escritório | `report_created` |
| `idle` | Pátio | sem task ativa (perambula) |

**Roteamento (híbrido, recomendado):**
1. **Base determinística**: o `role` escolhido no spawn define o setor "casa".
2. **Override por evento**: estender `sync_agent_from_event` (`harness.py:1082`,
   que já mapeia evento→phase) para também setar `sector`. Assim um builder que
   dispara uma auditoria "anda" até a Torre de Vigia e depois volta.
3. Helper `sector_for_role(role)` + `sector_for_event(type, payload)` no Python.

---

## 6. Cliente Kaplay — módulos

```
client/src/
  net.js          # snapshot /api/world, SSE /api/events, POST com token
  world.js        # carrega tilemap (Tiled JSON), grid de colisão, zonas de setor
  pathfinding.js  # A* sobre o grid; caminho até o centroide do setor
  agents.js       # cria/reconcilia sprites a partir do world state + deltas SSE
  statemachine.js # spawning → idle → walking → working → talking → done
  sprites.js      # sheets idle/walk 4 direções; paleta por papel
  terminal.js     # instância xterm.js + WS por agente (overlay)
  ui.js           # toolbar (add repo, spawn), painel ao clicar no agente
  overworld.js    # seletor de repos (1 prédio por repo → entra no mapa)
```

**Tilemap**: desenhar no **Tiled**, exportar JSON. Uma *object layer* `sectors`
com objetos retangulares nomeados (`name = implement`, etc.) define as zonas.
Uma *tile layer* `collision` define onde dá pra andar.

**Sprites/animação**: sheet com `idle-{down,up,left,right}` e `walk-*`. Kaplay
`loadSprite(..., { sliceX, sliceY, anims })`. Direção pela direção do movimento.
- `working`: pequeno *bob* (tween) perto da bancada do setor.
- `idle`: *wander* (waypoints aleatórios dentro do setor casa).
- `talking`: vira pro alvo + balão de fala (texto do campo `speech`).

**Reconciliação**: ao chegar delta SSE, comparar `agents[]`:
- novo id → spawnar sprite (`spawning`);
- `sector` mudou → A* até a nova zona (`walking` → estado do destino);
- `state`/`speech` mudou → atualizar anim/balão;
- sumiu / `agent_killed` → remover sprite.

**Multi-repo**: começar com **overworld** (zoom-out, 1 prédio por repo); clicar
entra no mapa daquele repo (cena Kaplay dedicada). Escala melhor que "uma sala
por repo na mesma tela". **Cada repo recebe um tema visual diferente** (um tileset
Kenney por mapa — ex.: vila, cidade moderna, masmorra), guardado num campo
`theme` no registry do repo; assim repos distintos ficam visualmente distintos.

---

## 7. Fluxos de uso

### 7.1 Novo projeto (puxar pasta → mapa novo)
1. Toolbar "Adicionar repo" → input de caminho absoluto (drag-drop do browser
   **não** entrega caminho local por segurança; usar input + lista de recentes).
2. `POST /api/repos/add` → Node chama `hub-add-repo` (`harness.py:5628`) e roda
   `init` se faltar `.harness`.
3. Overworld ganha um prédio novo; ao entrar, mapa vazio, sem agentes, com botão
   "Spawnar agente".

### 7.2 Spawnar agente + pedir tarefas
1. Botão "Spawnar agente" → escolhe `role` + `cli` (codex/claude) + nome.
2. `POST /api/agents/spawn`:
   - Node valida gate `hub.allow_remote_execution` + token + loopback;
   - cria PTY (`node-pty`) rodando o launcher do CLI com `cwd = repo`;
   - chama `harness agent register <id> --role ... --cli ... --sector ...`;
   - emite `agent_spawned`.
3. Sprite aparece no setor casa; clicar abre o **terminal embutido** (xterm.js
   ↔ WS). Você digita os pedidos ali, como num terminal normal.

### 7.3 Clicar em outro agente e ver o que faz
- Clique no sprite → painel lateral: task atual, status, run/checkpoint,
  **transcript** (`.harness/agents/<id>/transcript.jsonl`) e botão "abrir
  terminal" (anexa um xterm.js ao PTY existente daquele agente).

### 7.4 Agentes conversando
- v1 (visual + mailbox): `POST /api/agents/:id/message {to,text}` grava
  `agent_message`; o cliente faz os dois sprites se aproximarem e mostra balões;
  o agente alvo lê a "caixa de recados" (`agent-messages.jsonl`, padrão do
  `queue_operator_message`, `harness.py:2552`) antes de agir.
- Orquestração real LLM↔LLM (saída de um vira entrada do outro) fica para depois.

### 7.5 Auditor itinerante
- Spawnar agente role `security`/`auditor` com um script de tour: visita cada
  setor/repo, roda a skill `code-auditor`, publica achados como eventos. O
  cliente anima ele andando casa-a-casa e abre o relatório no fim.

---

## 8. Segurança (não negociável)

Spawnar terminal/LLM pela web **é RCE por design**. Requisitos:

1. **Loopback + token** em **todos** os POSTs e no WS (reusar o padrão de
   `authorized()`, `harness.py:5840`). Validar também o header `Origin` do WS.
2. **Gate `hub.allow_remote_execution`**: sem ele `true`, `/api/agents/spawn`
   responde 403. (Dá função à flag morta apontada no audit.)
3. **Validação de path**: `repo`/`cwd` resolvidos e checados (reusar
   `assert_inside_root`/`resolve`, `harness.py:571`). Nada de spawnar fora de
   repos registrados.
4. **Sanitização**: qualquer caminho mandado ao shell via `ps_single_quote`
   (`harness.py:4501`) / `shlex`. Nunca interpolar string crua.
5. **Limites de PTY**: `hub.max_agents`, `idle_timeout_s` (mata sessão ociosa),
   teto de `scrollback_bytes` por sessão.
6. **Segredos**: não logar env (token do bot, OPENAI_API_KEY) no transcript nem
   nos eventos. O scanner do audit **ignora** `.harness/`, então o transcript do
   agente pode reter segredos — redigir antes de persistir.
7. **Bind padrão** `127.0.0.1`; recusar `Origin` não-loopback no WS.

---

## 9. Realtime & persistência

- **SSE** para estado/eventos (incremental, via offset). Snapshot inicial em
  `/api/world`, depois só deltas.
- **WS** para terminais. PTYs vivem no processo Node, indexados por `agent_id`,
  com **ring buffer** de scrollback. Recarregar o browser **reanexa** ao PTY
  existente e **reproduz** o buffer (scrollback). Se o Node reinicia, as sessões
  morrem — documentar e marcar agentes como `state=offline` no próximo snapshot.

---

## 10. Extensões necessárias no Python (`bin/harness.py`)

- [ ] Estender `upsert_agent` (1021) e `command_agent_register` (5685) com
      `cli, sector, pty_id, repo_root, cwd, transcript_path, spawned_by`.
- [ ] `sector_for_role(role)` + estender `sync_agent_from_event` (1082) para
      setar `sector` e emitir `agent_sector_changed`.
- [ ] Subcomando `agent message <id> --to <id> --text ...` → evento
      `agent_message` + append em `agent-messages.jsonl`.
- [ ] Subcomando `agent kill <id>` (marca registry; o PTY é morto pelo Node).
- [ ] Bloco `hub` no `command_init` (1862) e leitura via novo `hub_config()`.
- [ ] Manter `dashboard hub-state --json` (5674) como fallback de snapshot.
- [ ] **Escrita atômica** em `harness_core/storage.py`: `write_text`/`write_json`
      hoje fazem `path.write_text(...)` (truncate-then-write), o que deixa o Node
      ler `.harness/*.json` parcial durante um rewrite. Trocar por gravar em
      `path` + sufixo temporário e `os.replace(tmp, path)` (atômico no Windows no
      mesmo volume). **Pré-requisito do M0** (a estratégia ler-arquivos depende disso).
- [ ] (Limpeza, do audit) extrair `render_dashboard_hub_html` gigante; o HTML
      passa a ser servido pelo Node como estático.

---

## 11. Estrutura de arquivos proposta

```
hub/
  server/
    index.js        # http + ws + sse + static + token/loopback
    pty.js          # node-pty manager (spawn/resize/write/kill + ring buffer)
    harness.js      # ler .harness/ + shell-out p/ bin/harness.py
    security.js     # token, loopback, origin, gate allow_remote_execution
  client/
    index.html
    src/{net,world,pathfinding,agents,statemachine,sprites,terminal,ui,overworld}.js
    assets/{tilesets,sprites,maps}/
  package.json      # kaplay, @xterm/xterm, @xterm/addon-fit, ws, node-pty
bin/harness.py      # extensões da §10
docs/HUB_PIXEL_GAME_PLAN.md
```

Dependências Node (cliente+servidor): `kaplay`, `@xterm/xterm`,
`@xterm/addon-fit`, `ws`, `node-pty`. (O CLI Python segue zero-dep; as deps são
só do hub opcional.)

---

## 12. Roadmap por fases (cada uma é entregável)

### M0 — Fundação
- Servidor Node serve cliente Kaplay vazio + `/api/world` (lê `.harness/`).
- Python: **escrita atômica** em `storage.py` (tmp + `os.replace`); extrair o HTML
  gigante; manter `hub-state --json`.
- **DoD**: `harness-hub` no ar; cliente carrega e lista repos/agentes do snapshot
  sem nunca ler JSON parcial durante uma escrita do CLI.

### M1 — Jogo de verdade
- Tilemap (Tiled) + colisão + zonas de setor; sprites idle/walk; A*.
- Agentes do registry aparecem e caminham até o setor certo; working/idle/talk.
- **DoD**: agente `working` fica na Forja; `idle` perambula; balão mostra `speech`.

### M2 — Terminais + spawn
- PTY manager + WS + xterm.js overlay; botão "Spawnar agente" (codex/claude);
  clicar agente → ver/abrir terminal.
- **DoD**: spawnar, digitar no terminal, ver saída ao vivo; reanexar após reload.

### M3 — Realtime + roteamento automático
- SSE deltas substituem polling; `sector` automático via eventos.
- **DoD**: rodar `harness sensors`/`evaluate` move o sprite e atualiza o painel.

### M4 — Social + novo-projeto + auditor
- `agent_message` + encontros visuais + mailbox; overworld + add-repo;
  auditor itinerante que ronda os setores e gera relatório.
- **DoD**: dois agentes "conversam"; puxar pasta cria mapa; auditor entrega report.

---

## 13. Decisões fechadas (resolvidas em 2026-05-29)

1. **Node sidecar vs Python puro** → **Node sidecar (`harness-hub`)**. Motivo:
   `node-pty` (ConPTY confiável no Windows) + ecossistema xterm.js, e o wmux já é
   Node. A alternativa all-Python (`pywinpty` + `websockets`) é mais frágil no
   PTY e exigiria reimplementar o transporte. O core Python (`bin/harness.py`)
   permanece **zero-dep**; as deps de Node ficam só no hub opcional.
2. **Estado: ler arquivos vs CLI** → **ler-arquivos p/ leitura + CLI p/ escrita**,
   com as escritas do Python tornadas **atômicas**. Confirmado no código:
   `write_text`/`write_json` (`harness_core/storage.py:15`) hoje fazem
   truncate-then-write, então a corrida é real. Correção: gravar em arquivo
   temporário + `os.replace()` (atômico no Windows, mesmo volume). Virou tarefa
   de §10 e **pré-requisito do M0**.
3. **ConPTY no Windows** → **mitigação, não bloqueio**. Testar resize/ANSI/encoding
   logo no início do M2 (caminho mais arriscado); não muda a arquitetura.
4. **Caminho do drag-drop** → **input de caminho absoluto + lista de recentes**.
   O browser não entrega path local por segurança; folder-picker nativo via Node
   fica como melhoria opcional futura.
5. **Persistência de PTY** → **sessões morrem no restart do hub no v1**. Ao
   reiniciar, os agentes são marcados `offline` no próximo snapshot e
   re-spawnados sob demanda. Daemon de PTY separado fica fora do v1.
6. **Coordenação LLM↔LLM real** → **fora de escopo do v1** (só mailbox + visual).
7. **Assets/licença** → **Kenney (CC0)**. Motivo: catálogo grande e **variado**,
   permitindo **1 tema de tileset por repo** (casa com o overworld da §6), e
   **CC0** (sem custo, sem atribuição obrigatória). Caveat: os personagens top-down
   do Kenney têm **poucos frames** — não é walk cycle 4-direções completo.
   Mitigação no v1: animação simples (bob/slide ao se mover) **ou** parear os
   mapas Kenney com um sheet de personagem CC0 (ex.: Ninja Adventure). Licenças
   registradas em `hub/client/assets/LICENSES.md`. Ver §14.

---

## 14. Assets (para chegar perto da referência)

Decisão (§13.7): **assets do Kenney (`kenney.nl`), licença CC0**. Sem custo, sem
atribuição obrigatória (mas registramos em `LICENSES.md` mesmo assim). Escolhido
pela variedade: **um tileset diferente por repo** (§6).

**Tilesets candidatos (top-down, 16×16, CC0):**

| Pack Kenney | Tema sugerido de mapa | Bom para |
|---|---|---|
| Tiny Town | vila aconchegante (default) | repo "casa", look Stardew |
| RPG Urban Pack | cidade moderna | repos de produto/web |
| Tiny Dungeon / Roguelike Dungeon | masmorra | repos de infra/baixo nível |
| Roguelike/RPG Pack (1700+ tiles) | RPG genérico amplo | base coringa de setores |

> Mapeamento `repo → theme` fica no registry do repo (§6). Começar com **Tiny Town**
> como tema padrão e variar conforme novos repos entram.

**Personagens (o caveat):** os sprites top-down do Kenney têm **poucos frames** —
não entregam walk cycle 4-direções completo. Duas saídas para o M1:
1. **Animação simples (recomendado p/ v1):** sprite do Kenney com *bob/slide* ao
   mover (sem ciclo de passos). Mantém tudo CC0 e numa fonte só.
2. **Parear com personagem CC0:** usar tilesets Kenney + um sheet de personagem
   com walk 4-dir (ex.: **Ninja Adventure**, CC0) recolorido nas 5 paletas
   (builder, reviewer, security, planner, research). Mais trabalho, visual melhor.

**Registro de licença:** cada asset usado entra em `hub/client/assets/LICENSES.md`
(pack, autor, URL, licença, data) — mesmo sendo CC0, para rastreabilidade.
