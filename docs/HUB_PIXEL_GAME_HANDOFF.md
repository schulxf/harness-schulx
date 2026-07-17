# Handoff: Hub Pixel-Art Implementado

Este handoff resume o que ja foi implementado do plano em
`docs/HUB_PIXEL_GAME_PLAN.md`, onde esta cada parte, como rodar, o que foi
testado e o que ainda falta para fechar o v1 do hub gamificado.

Data do handoff: 2026-05-29.

## Atualizacao 2026-05-29 (render de tiles + agentes + menu)

Esta sessao trocou o render procedural por um mapa de tiles real e adicionou o
fluxo de menu/onboarding. Resumo do que mudou no cliente:

- Mapa agora usa os tilesets packed da Kenney (`tilemap_packed.png`), 12x11 de
  16px, em vez de retangulos. Visual no nivel do `Sample.png`.
- `hub/client/src/tiles.js` (novo): loader das folhas + `TILESETS` por tema
  (`tiny-town`, `tiny-dungeon`) com vocabulario semantico de tiles (chao,
  caminho, praca 9-slice, kits de predio, arvores/props, placas, icones).
- `hub/client/src/mapgen.js` (novo): gera uma cidade determinista por repo de
  forma INDEPENDENTE de tema — praca central, caminhos de terra ate cada predio
  de setor, arvores/arbustos/placas, estacoes (onde o agente "trabalha") e
  retangulos de colisao para o A*.
- `render.js` reescrito: desenha chao, decoracao, predios e arvores com y-sort,
  placas com icone de setor e rotulos. Resolve a semantica do mapgen para tiles
  via o tileset do tema ativo.
- `sprites.js` reescrito: agentes agora sao sprites de canvas de
  `assets/sprites/agents.png` (6 frames 48px, 1 por papel) com sombra, anel de
  selecao, nome e balao de fala.
- `agents.js` reescrito: entidades de canvas que pathfind ate a estacao do setor
  da tarefa (builder->Forge, reviewer->Library, etc.) e perambulam na praca
  quando ociosas. Hit-test por clique no canvas.
- `menu.js` (novo) + `#menuRoot` no `index.html`: menu estilo jogo. Abre no
  onboarding (repo sem agentes) e pelo botao "Menu". Escolha de tema (preview
  real Kenney via `Sample.png`), escolha de papel (com o sprite), spawn do
  primeiro agente, add repo. O tema escolhido fica em
  `localStorage['hubTheme:<repoId>']` e o render troca a folha em tempo real.
- `overworld.js` deixou de ser o modo padrao; o mapa por repo (a cidade) e a
  visao principal. `viewToggle` foi trocado pelo botao `menuButton`.
- `package.json` `check` agora cobre `tiles.js`, `mapgen.js`, `menu.js`.

Verificacao usada nesta sessao (sem Playwright, sem mexer no browser do usuario):
o sidecar serve `hub/client` sem cache, entao editar + recarregar reflete na
hora. Captura do canvas via `wmux browser eval` de `canvas.toDataURL`. Para a
pagina inteira (menu DOM) foi usado um Chrome headless proprio via CDP em porta
isolada. Detalhes em `[[hub-pixel-verify-loop]]`.

Ainda divergente do plano original: Kaplay continua nao usado (render e
canvas 2D proprio); mapas sao procedurais em vez de Tiled JSON. O terminal
visual agora usa xterm.js real dentro do modal do agente. O resto deste
documento descreve o estado anterior a esta atualizacao.

## Resumo executivo

O plano ja saiu da fase de design. Existe uma primeira versao funcional do
hub opcional em `hub/`, com sidecar Node, snapshot de mundo, SSE de eventos,
spawn/message/kill de agentes, PTY via `node-pty`, cliente web com mapa
top-down em canvas, overworld multi-repo, setores, sprites DOM/CSS, A* simples
e overlay de terminal por WebSocket.

No core Python, o estado foi preparado para essa arquitetura: escritas JSON
agora sao atomicas, o config ganhou bloco `hub`, o registry de agentes ganhou
metadados do plano, e eventos de Harness podem atualizar agentes/setores para
o hub.

O que ainda nao esta completo: Kaplay ainda nao e usado no cliente, mapas
Tiled/licencas estao presentes mas o render atual e procedural em canvas, e a
regra "Node so muta via CLI Python" ainda nao e totalmente verdadeira porque o
sidecar tambem escreve registry/eventos/mensagens diretamente para operacoes
do hub.

## Arquitetura entregue

### Core Python continua fonte de verdade

Arquivos principais:

- `harness_core/storage.py`
- `harness_core/defaults.py`
- `harness_core/config.py`
- `harness_core/agent_registry.py`
- `harness_core/hub_agents.py`
- `harness_core/event_pipeline.py`
- `harness_core/hub_state.py`
- `bin/harness.py`

Implementado:

- Escrita atomica em `write_text`/`write_json` usando arquivo temporario,
  `fsync` e `os.replace`.
- `DEFAULT_HUB_CONFIG` com:
  - `allow_remote_execution`
  - `max_agents`
  - `default_cli`
  - `clis.codex`
  - `clis.claude`
  - `pty.idle_timeout_s`
  - `pty.scrollback_bytes`
- Helper `hub_config(config)` em `harness_core/config.py`.
- Registry de agentes estendido com:
  - `cli`
  - `sector`
  - `pty_id`
  - `repo_root`
  - `cwd`
  - `transcript_path`
  - `spawned_by`
- Normalizacao de agentes antigos para o novo shape.
- `sector_for_role` e `sector_for_event`.
- `sync_agent_from_event` agora:
  - infere role/state/phase a partir dos eventos do Harness;
  - atualiza/cria agente no registry;
  - emite `agent_sector_changed` quando o setor muda.
- `collect_hub_repo_state` continua servindo como fallback Python para snapshot
  do dashboard/hub.

### Sidecar Node `harness-hub`

Arquivos principais:

- `hub/package.json`
- `hub/server/index.js`
- `hub/server/harness.js`
- `hub/server/pty.js`
- `hub/server/security.js`

Dependencias declaradas:

- `ws`
- `kaplay`
- `@xterm/xterm`
- `@xterm/addon-fit`
- `node-pty` como dependencia opcional

Scripts:

- `npm start`
- `npm run check`
- `npm test`

Endpoints implementados:

- `GET /` e assets estaticos do cliente.
- `GET /api/world` para snapshot multi-repo.
- `GET /api/events?offset=N` para SSE incremental.
- `WS /ws/term?agent=<id>` para I/O do terminal PTY.
- `POST /api/agents/spawn`.
- `POST /api/agents/:id/message`.
- `POST /api/agents/:id/kill`.
- `POST /api/repos/add`.

Comportamento entregue:

- Leitura direta de `.harness/` para snapshot rapido.
- Fallback para repos registrados em `.harness/dashboard/hub/repos.json`.
- Eventos sao lidos por offset/cursor por repo.
- `spawn` valida repo registrado, gate de execucao remota e limite de agentes.
- `spawn` cria PTY e registra agente via CLI Python, depois complementa metadados
  no registry.
- `message` grava `agent-messages.jsonl` e emite `agent_message`.
- `kill` encerra PTY, marca agente offline/done e emite `agent_killed`.
- `add repo` inicializa `.harness` quando necessario e chama `dashboard
  hub-add-repo`.

### Seguranca do sidecar

Arquivo principal:

- `hub/server/security.js`

Implementado:

- Endpoints mutaveis exigem loopback.
- Endpoints mutaveis exigem header `X-Harness-Hub-Token`.
- WebSocket aceita token por query para browser, mas valida loopback e `Origin`.
- `hub.allow_remote_execution` e o gate para spawn/message/kill.
- Comparacao de token usa `crypto.timingSafeEqual`.
- Repos precisam estar registrados antes de spawnar agente.
- PTY tem limite de agentes, timeout ocioso e scrollback limitado.

Observacao importante:

- O scanner de segredos do core exclui `.harness/`. Como transcripts/mensagens
  vivem ali, ainda falta redacao de segredos antes de persistir saida de agente.

## Cliente web entregue

Arquivos principais:

- `hub/client/index.html`
- `hub/client/src/main.js`
- `hub/client/src/net.js`
- `hub/client/src/world.js`
- `hub/client/src/overworld.js`
- `hub/client/src/render.js`
- `hub/client/src/agents.js`
- `hub/client/src/pathfinding.js`
- `hub/client/src/statemachine.js`
- `hub/client/src/sprites.js`
- `hub/client/src/terminal.js`
- `hub/client/src/ui.js`
- `hub/client/src/styles.css`

Implementado:

- Cliente carrega `/api/world` quando servido por HTTP.
- Fallback para `hub-state.json`, `state.json` e demo world.
- SSE via `EventSource` em `/api/events`, com fallback para polling.
- Normalizacao de world state independente do shape exato do snapshot.
- Aplicacao de eventos:
  - `agent_spawned`
  - `agent_sector_changed`
  - `agent_message`
  - `agent_terminal_attached`
  - `agent_killed`
- Modo `overworld` com predios por repo.
- Modo mapa por repo com setores:
  - `plan`
  - `implement`
  - `review`
  - `research`
  - `security`
  - `report`
  - `idle`
- Render procedural em canvas 16:9, com temas visuais por repo.
- A* simples em grid de 32 px para movimento de agentes.
- Camada DOM de agentes com:
  - sprites CSS fallback;
  - suporte opcional a `assets/sprites/agents.png`;
  - fala em balao;
  - estados visualmente distintos: idle, walking, working, talking, offline.
- Inspector lateral com contexto do repo/agente.
- Controles para:
  - alternar world/map;
  - refresh;
  - spawn agent;
  - add repo;
  - send message;
  - kill agent;
  - abrir terminal.
- Modal de agente com xterm.js real por WebSocket.

Limite atual do cliente:

- Kaplay ainda nao e usado, apesar de estar declarado no `package.json`.
- xterm.js foi integrado visualmente no modal do agente, com input direto,
  Ctrl+C, reconnect, clear e kill.
- Os mapas ainda nao usam Tiled/object layers; setores sao retangulos
  gerados/normalizados em JS.
- Colisao no pathfinding existe como suporte, mas o mapa atual nao passa
  obstaculos reais para A*.

## Assets entregues

Arquivos/pastas:

- `hub/client/assets/manifest.json`
- `hub/client/assets/LICENSES.md`
- `hub/client/assets/vendor/kenney_tiny-town/`
- `hub/client/assets/vendor/kenney_tiny-dungeon/`
- `hub/client/assets/vendor/ninja_adventure/`

Status:

- Assets CC0/abertos foram colocados no repo local para apoiar a direcao visual.
- Licencas foram registradas em `LICENSES.md`.
- O cliente atual ainda usa render procedural/CSS, nao tilemaps reais desses
  packs.

## Fases do plano

### M0: Fundacao

Status: substancialmente implementado.

Entregue:

- Sidecar Node em `hub/server`.
- Cliente web servido estaticamente.
- `/api/world`.
- Leitura direta de `.harness/`.
- Escrita atomica no core Python.
- `hub-state` Python permanece como fallback.
- Tests de seguranca e snapshot do Node.

Aberto:

- Garantir que todo mutating path do Node chame CLI Python. Hoje algumas
  mutacoes do hub escrevem arquivos diretamente.

### M1: Jogo de verdade

Status: parcialmente implementado.

Entregue:

- Overworld.
- Mapa por repo.
- Setores.
- Agentes visuais.
- Movimento com A*.
- Estados idle/walking/working/talking/offline.
- Speech bubbles.
- Temas por repo.

Aberto:

- Kaplay real.
- Tilemaps Tiled.
- Colisao baseada em layer.
- Spritesheets finais com walk cycle 4 direcoes.
- Mapas baseados nos packs Kenney/Ninja Adventure.

### M2: Terminais + spawn

Status: backend e frontend interativo implementados para o fluxo local.

Entregue:

- PTY manager.
- WebSocket de terminal.
- xterm.js real no modal do agente.
- Spawn de agente por UI/API.
- Reattach com scrollback em memoria enquanto o Node esta vivo.
- Kill de agente.
- Gate `hub.allow_remote_execution`.

Aberto:

- Persistencia de transcript.
- Redacao de segredos no transcript.
- UX final de spawn/profile/CLI.
- Marcar automaticamente sessoes offline apos restart do sidecar em todos os
  caminhos.

### M3: Realtime + roteamento automatico

Status: parcialmente implementado.

Entregue:

- SSE incremental em `/api/events`.
- Cliente aplica deltas de evento.
- Python emite `agent_sector_changed` ao sincronizar eventos do Harness.
- Helpers de setor por role/evento existem no Python e no cliente.

Aberto:

- Cobrir todos os eventos reais do Harness com transicoes semanticas.
- Unificar tabela de eventos Python/cliente para evitar divergencia.
- Atualizar mapa em tempo real para sensores/evaluate/report em todos os
  fluxos CLI.

### M4: Social + novo projeto + auditor

Status: parcial.

Entregue:

- `agent_message` via API.
- Visual de talking/speech no cliente.
- `/api/repos/add`.
- Overworld multi-repo.

Aberto:

- Mailbox lida por agentes antes de agir.
- Conversa LLM para LLM real.
- Auditor itinerante.
- Criacao de report visual apos tour.
- Drag/drop/folder picker nativo ainda fora do v1.

## Testes existentes relacionados

Python:

- `tests/test_core_agent_registry.py`
- `tests/test_core_hub_agents.py`
- `tests/test_core_hub_state.py`
- `tests/test_core_config.py`
- `tests/test_core_storage_paths.py`
- `tests/test_core_event_pipeline.py`

Node:

- `hub/server/harness.test.js`
- `hub/server/security.test.js`

Checks esperados:

```powershell
python -m pytest tests/test_core_agent_registry.py tests/test_core_hub_agents.py tests/test_core_hub_state.py tests/test_core_config.py tests/test_core_storage_paths.py tests/test_core_event_pipeline.py
cd hub
npm test
npm run check
```

## Como rodar manualmente

1. Inicializar um repo com Harness, se ainda nao tiver `.harness/`:

```powershell
python .\bin\harness.py --repo C:\path\to\repo init
```

2. Registrar repos no hub:

```powershell
python .\bin\harness.py --repo C:\control-repo dashboard hub-add-repo C:\path\to\repo
```

3. Habilitar execucao remota no config do repo que vai spawnar agentes:

```json
{
  "hub": {
    "allow_remote_execution": true
  }
}
```

4. Instalar dependencias do hub:

```powershell
cd hub
npm install
```

5. Rodar:

```powershell
npm start -- --repo C:\control-repo --watch-repo C:\path\to\repo
```

6. Abrir o URL mostrado no console e usar o token exibido pelo sidecar. O token
tambem pode vir por `HARNESS_HUB_TOKEN`.

## Divergencias conhecidas entre plano e implementacao

- Plano: cliente Kaplay. Implementacao: canvas/DOM proprio.
- Plano: terminal xterm.js. Implementacao: modal de agente com xterm.js real.
- Plano: Node le arquivos e muta sempre via Python CLI. Implementacao: mistura
  CLI Python com escritas diretas em Node para eventos, mensagens e augment de
  agentes.
- Plano: Tiled JSON e collision layer. Implementacao: setores hardcoded/
  normalizados em JS e mapa procedural.
- Plano: transcripts persistidos. Implementacao: caminho de transcript existe no
  registry, mas o PTY manager mantem scrollback em memoria.
- Plano: redacao de segredos em output de agente. Implementacao: ainda pendente.
- Plano: agente alvo le mailbox antes de agir. Implementacao: mailbox/evento
  existe, leitura pelo agente ainda pendente.

## Proximos passos recomendados

1. Persistir transcript JSONL com redacao de segredos.
2. Decidir se o cliente continua canvas/DOM ou migra para Kaplay. Se manter
   canvas, atualizar o plano para remover Kaplay como requisito.
3. Centralizar mutacoes do Node via CLI Python ou documentar excecoes seguras.
4. Criar teste end-to-end local do sidecar: spawn -> WS attach -> input/output
   -> kill.
5. Unificar `sector_for_event` entre Python e cliente.
6. Trocar mapa procedural por tilemaps Tiled com collision/object layers.
7. Implementar auditor itinerante como primeiro agente especializado gamificado.

## Estado de risco

Risco principal: RCE local por design. O gate atual e bom para v0 local, mas
antes de qualquer uso fora de loopback precisa haver modelo de permissao por
agente, redacao de segredo, audit log imutavel e approval queue para comandos
sensitivos.

Risco de produto: a base tecnica esta mais avancada que a camada de jogo. O
usuario ja ve um hub vivo, mas ainda nao ve "agentes autonomos colaborando" em
sentido forte. O proximo incremento de maior impacto e subagent/background
ledger ou auditor itinerante, nao apenas mais pixel art.
