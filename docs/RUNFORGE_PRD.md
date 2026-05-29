# PRD: Runforge Agent Operations Hub

Status: Draft pronto para decomposicao em issues  
Data: 2026-05-29  
Produto: Runforge  
Categoria: local-first agent harness + gamified operations hub  
Documento base: `docs/V0_3_HARNESS.md`, `docs/HUB_PIXEL_GAME_PLAN.md`,
`docs/HUB_PIXEL_GAME_HANDOFF.md`

## 1. Sumario executivo

Runforge e um harness local-first para agentes de codigo com governanca forte:
contratos, evidencia, sensores, checkpoints, revisao, avaliacao, seguranca e
relatorios. A proxima fase transforma Runforge em um agent operations hub:
um mission control gamificado onde agentes especializados vivem em mapas por
repo, executam tarefas governadas, delegam subtrabalhos isolados, usam runtimes
diversos, instalam skills/MCPs sob politica e rodam rotinas recorrentes sem
perder rastreabilidade.

O diferencial nao e copiar OpenClaw, Hermes ou qualquer assistente pessoal
generico. O diferencial e manter o DNA atual:

- contrato antes de execucao;
- sensores deterministicos;
- evidencia local;
- checkpoints e resume;
- avaliador e reviewer isolados;
- scanner de seguranca;
- relatorios auditaveis;
- policy gates explicitos.

O hub gamificado deve ser a interface viva dessa governanca. Cada agente e uma
entidade operacional com permissao, memoria, runtime, estado, historico e papel
claro. Cada execucao importante aparece no ledger. Cada automacao recorrente tem
standing order, limite e criterio de parada. Nada relevante acontece "fora do
mapa".

## 2. Objetivos

### 2.1 Objetivos de produto

1. Transformar Runforge de um harness de runs em um control plane local para
   agentes de codigo.
2. Permitir multiplos agentes especializados trabalhando em paralelo sem perder
   isolamento, escopo ou evidencia.
3. Dar ao operador uma visao visual e operacional clara do que esta rodando,
   quem iniciou, qual runtime executa, qual permissao foi usada, qual evidencia
   existe e qual decisao falta.
4. Permitir agentes de diferentes runtimes: Codex, Claude, Hermes, OpenClaw,
   ACP e PTY generico.
5. Criar uma camada de seguranca granular por agente antes de abrir mais canais
   externos.
6. Transformar skills e MCPs em capacidades instalaveis, revisaveis e
   ativaveis por agente.
7. Permitir cron jobs e standing orders para manter o hub vivo sem prompt humano
   constante.

### 2.2 Objetivos de engenharia

1. Preservar o core Python como fonte da verdade de dominio.
2. Manter estado local em `.harness/` com arquivos simples, versionaveis quando
   apropriado e atomicos para leitura concorrente.
3. Separar runtime execution de domain policy.
4. Criar contratos de dados estaveis para ledgers, agentes, runtimes,
   permissoes, skills, MCPs e schedules.
5. Permitir testes unitarios e integration tests sem chamar provedores reais.
6. Criar caminhos de migracao para repos com `.harness/` antigo.
7. Evitar acoplamento duro entre UI do hub e funcionamento do CLI.

## 3. Nao objetivos

1. Nao virar IDE completa.
2. Nao substituir GitHub, GitLab, Linear ou Jira.
3. Nao criar cloud sync obrigatorio.
4. Nao permitir execucao remota aberta por padrao.
5. Nao esconder comandos, custos, tokens, arquivos alterados ou falhas.
6. Nao criar um assistente pessoal generico sem contrato de trabalho.
7. Nao exigir que todos os usuarios usem o hub visual para operar o core.
8. Nao depender de um provedor unico de modelo ou CLI.

## 4. Usuarios e personas

### 4.1 Operador solo

Pessoa que usa agentes para implementar features e corrigir bugs em repos
locais. Quer velocidade, mas nao aceita perder controle de escopo.

Necessidades:

- ver rapidamente o que esta rodando;
- pausar, cancelar e retomar;
- saber se sensores passaram;
- receber revisao isolada;
- revisar logs sem abrir varias pastas;
- criar automacoes simples.

### 4.2 Tech lead

Pessoa que coordena multiplos repos ou varias frentes de produto. Quer agentes
especializados, mas com permissoes e evidence trail.

Necessidades:

- politica por repo/agente;
- subagentes para research, review, security e docs;
- ledger auditavel;
- follow-ups automaticos;
- relatorios para PR/issue;
- evitar que um agente mexa em area errada.

### 4.3 Builder de agentes

Pessoa que cria skills, MCPs, templates e perfis de agentes.

Necessidades:

- empacotar skill;
- declarar permissoes;
- testar capability;
- publicar localmente;
- ativar em alguns agentes;
- ver falhas e uso.

### 4.4 Auditor/security reviewer

Pessoa ou agente responsavel por permissao, secrets, policy drift e comandos
arriscados.

Necessidades:

- ver todo comando sensitivo;
- ver quais agentes podem acessar shell/network/secrets;
- aprovar ou negar acoes;
- bloquear runs;
- gerar relatorio de risco.

## 5. Principios do produto

1. Local-first: tudo funciona sem cloud obrigatoria.
2. Evidence-first: toda decisao importante aponta para evidencia.
3. Contract-first: agente nao deve expandir escopo sem novo contrato.
4. Policy-before-autonomy: autonomia so existe dentro de permissao explicita.
5. Runtime-neutral: Codex, Claude, Hermes, OpenClaw e ACP sao adaptadores, nao o
   dominio.
6. Inspectable by default: estado, logs, eventos, custos e permissoes sao
   visiveis.
7. Fail closed: se uma permissao, runtime ou capability for incerta, bloquear.
8. Human override: operador pode pausar, cancelar, assumir terminal e registrar
   decisao.
9. Game is state made visible: gamificacao representa estado operacional real,
   nao decoracao falsa.

## 6. Estado atual resumido

Ja existe:

- CLI Python com tasks, contratos, sensores, runs, relatorios e eventos.
- Queue, supervisor, checkpoints, memory, plugin registry e security scanner em
  diferentes niveis de maturidade.
- Hub Node opcional com `/api/world`, SSE, WebSocket terminal, spawn/message/kill
  de agentes e gate `hub.allow_remote_execution`.
- Cliente visual com mapa por repo, tiles Kenney, sprites, menu/onboarding,
  movimento por setor e interacao basica.
- Registry de agentes com campos para runtime/PTY/setor/repo/cwd/transcript.

Baseline definitivo do hub visual:

- a tela principal e o mapa de uma cidade por repo, nao o overworld;
- `hub/client/src/mapgen.js` gera uma cidade deterministica por repo;
- `hub/client/src/tiles.js` resolve uma vocabulario semantico de tiles para
  `kenney_tiny-town` e `kenney_tiny-dungeon`;
- `hub/client/src/render.js` desenha o mapa com canvas 2D, y-sort, predios,
  placas e tiles reais;
- `hub/client/src/agents.js` gerencia agentes em canvas, com pathfinding ate
  estacoes de setor e hit-test por clique;
- `hub/client/src/sprites.js` desenha `assets/sprites/agents.png`;
- `hub/client/src/menu.js` e `#menuRoot` em `index.html` controlam onboarding,
  escolha de tema, role e spawn do primeiro agente;
- tema de repo e salvo em `localStorage['hubTheme:<repoId>']`;
- assets vendorizados de xterm existem em `hub/client/assets/vendor/xterm/`
  (`xterm.mjs`, `addon-fit.mjs`, `xterm.css`) e o modal do agente ja usa
  xterm.js de fato;
- `hub/package.json` ainda declara `kaplay`, mas a arquitetura aceita isso como
  dependencia legada nao usada. Nenhum trabalho deste PRD deve depender de
  Kaplay.

Ainda falta:

- ledger unificado de background tasks;
- subagentes isolados como feature geral;
- runtime adapter alem de PTY/CLI simples;
- seguranca granular por agente;
- loja de skills/MCPs;
- cron/standing orders;
- transcripts persistidos com redacao;
- audit log completo para todas as mutacoes do sidecar.

## 7. Prioridades do roadmap

### P0. Background task ledger + subagentes isolados

Criar a base de execucoes paralelas, auditaveis e isoladas.

### P0. Runtime adapter

Abstrair Codex/Claude/Hermes/OpenClaw/ACP/PTI em um contrato comum de runtime,
sem depender apenas de terminal PTY.

### P0. Seguranca granular por agente

Antes de abrir mais canais, cada agente precisa de permissoes explicitas,
aproval gates, limites e audit trail.

### P1. Skills/MCP como lojas dentro do hub

Transformar skills e MCPs em capacidades instalaveis, revisaveis e ativaveis por
agente.

### P1. Cron/standing orders

Permitir tarefas recorrentes e rotinas autonomas com limites claros.

## 8. Modulo A: Background Task Ledger

### 8.1 Problema

Hoje o event stream (`events.jsonl`) registra acontecimentos, mas nao e um
ledger transacional de trabalhos vivos. Runs, PTYs, evaluator/reviewer, mensagens
e futuras automacoes precisam de um lugar unico para status, responsavel, input,
runtime, permissao, prazo, custos, artifacts e resultado.

### 8.2 Objetivo

Criar um ledger local para todo trabalho assicrono ou paralelo:

- subagentes;
- runtime sessions;
- cron jobs;
- standing orders;
- audits;
- reviews;
- research tasks;
- tasks de longa duracao;
- comandos do hub que disparam execucao.

### 8.3 Arquivos

```text
.harness/background/
  index.json
  tasks/
    BGT-YYYYMMDD-HHMMSS-xxxx.json
  logs/
    <background_id>.jsonl
  results/
    <background_id>.md
    <background_id>.json
```

### 8.4 Estados

```text
draft
queued
scheduled
running
waiting_for_approval
waiting_for_input
succeeded
failed
timed_out
cancelled
lost
needs_work
archived
```

### 8.5 Modelo de dados

```jsonc
{
  "id": "BGT-20260529-154455-a1b2",
  "kind": "subagent",
  "title": "Review TASK-014 implementation",
  "repo_root": "C:/repo/app",
  "task_id": "TASK-014",
  "run_id": "run-20260529T154455Z",
  "parent_background_id": "",
  "parent_agent_id": "builder-1",
  "agent_id": "reviewer-TASK-014",
  "runtime": {
    "adapter": "codex",
    "profile": "reviewer-standard",
    "session_id": "rt-codex-abc123"
  },
  "status": "running",
  "priority": "normal",
  "created_at": "2026-05-29T15:44:55Z",
  "started_at": "2026-05-29T15:45:02Z",
  "updated_at": "2026-05-29T15:50:00Z",
  "deadline_at": "2026-05-29T16:15:00Z",
  "timeout_seconds": 1800,
  "input": {
    "mode": "isolated",
    "prompt_path": ".harness/runs/TASK-014/run-x/greptile-reviewer-agent-handoff.md",
    "context_paths": [],
    "allowed_files": ["src/**", "tests/**"],
    "redacted": true
  },
  "policy": {
    "permission_profile": "reviewer_readonly",
    "requires_approval": false,
    "can_mutate_repo": false,
    "can_use_network": false,
    "can_read_secrets": false
  },
  "budgets": {
    "token_budget": 20000,
    "command_budget": 10,
    "elapsed_seconds_budget": 1800,
    "cost_budget_usd": 1.0
  },
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "commands": 0,
    "cost_usd": 0.0
  },
  "artifacts": [
    {
      "kind": "result",
      "path": ".harness/background/results/BGT-20260529-154455-a1b2.md"
    }
  ],
  "result": {
    "status": "",
    "summary": "",
    "blocking": false
  },
  "failure": {
    "reason": "",
    "details": ""
  }
}
```

### 8.6 Requisitos funcionais

- A ledger task deve ser criada antes de qualquer execucao assicrona relevante.
- Cada mudanca de estado deve atualizar `index.json` e append em
  `.harness/events.jsonl`.
- O ledger deve suportar cancelamento.
- O ledger deve detectar tasks perdidas quando o processo/runtime morreu.
- O ledger deve separar input, runtime, policy, budgets, usage, artifacts e
  result.
- O hub deve listar background tasks por repo, agente, status, kind e task.
- O CLI deve expor criacao, listagem, show, cancel, retry, archive e prune.
- O supervisor deve consultar o ledger antes de marcar uma run como finalizada.

### 8.7 Requisitos nao funcionais

- Escrita atomica para `index.json` e cada task JSON.
- Append-only logs para eventos internos.
- Leitura tolerante a JSON parcial ou task perdida.
- Sem dependencia de banco externo.
- API testavel sem runtime real.

### 8.8 CLI alvo

```powershell
python .\bin\harness.py --repo C:\repo background list
python .\bin\harness.py --repo C:\repo background show BGT-...
python .\bin\harness.py --repo C:\repo background cancel BGT-...
python .\bin\harness.py --repo C:\repo background retry BGT-...
python .\bin\harness.py --repo C:\repo background archive BGT-...
python .\bin\harness.py --repo C:\repo background prune --older-than 30d
```

### 8.9 API do hub alvo

```text
GET  /api/background
GET  /api/background/:id
POST /api/background/:id/cancel
POST /api/background/:id/retry
POST /api/background/:id/archive
```

### 8.10 Criterios de aceite

- Criar uma background task gera JSON individual, atualiza index e emite evento.
- Cancelar uma task running chama o runtime adapter e registra resultado.
- Se o sidecar reinicia, tasks running sem runtime vivo viram `lost`.
- O hub mostra tasks running/failed/succeeded no mapa e no inspector.
- Testes cobrem state transitions, cancelamento, retry e deteccao de lost.

## 9. Modulo B: Subagentes isolados

### 9.1 Problema

Hoje o fluxo tem evaluator/reviewer isolados como arquivos de handoff, mas isso
nao e uma capacidade geral. O builder nao consegue delegar pesquisa, review,
security, docs ou investigacao para um subagente com escopo isolado, retorno
controlado e ledger.

### 9.2 Objetivo

Criar subagentes como primeira classe. Um agente pai pode pedir um subtrabalho
com contexto controlado. Runforge cria uma background task, escolhe runtime,
aplica policy, executa, coleta resultado e entrega ao pai/hub/supervisor.

### 9.3 Modos de isolamento

#### `isolated`

Subagente recebe apenas prompt, contrato e paths explicitamente permitidos.
Nao herda chat nem memoria do pai.

Uso:

- reviewer;
- evaluator;
- security;
- audit;
- second opinion;
- research de risco.

#### `fork`

Subagente recebe resumo do contexto do pai, mas nao acesso livre ao historico.
Pode receber checkpoint, diff e ultimos eventos.

Uso:

- paralelizar investigacao;
- testar abordagem alternativa;
- documentar enquanto builder implementa.

#### `interactive`

Subagente tem terminal/sessao anexavel no hub.

Uso:

- operador quer supervisionar;
- agente especializado precisa shell;
- debug interativo.

### 9.4 Papeis iniciais

- `builder`: implementa dentro do contrato.
- `reviewer`: revisa riscos do diff.
- `evaluator`: verifica se contrato foi atendido.
- `security`: procura secrets, RCE, unsafe writes, permission drift.
- `research`: coleta contexto tecnico/documentacao.
- `docs`: atualiza docs e handoffs.
- `qa`: roda/analisa checks, browser, screenshots ou mobile.
- `release`: prepara PR/release notes.

### 9.5 Modelo de subagent spec

```jsonc
{
  "id": "SUB-20260529-a1b2",
  "background_id": "BGT-20260529-154455-a1b2",
  "parent_agent_id": "builder-1",
  "role": "reviewer",
  "mode": "isolated",
  "repo_root": "C:/repo/app",
  "task_id": "TASK-014",
  "runtime_profile": "codex-reviewer-standard",
  "permission_profile": "reviewer_readonly",
  "prompt": {
    "source": "file",
    "path": ".harness/runs/TASK-014/run-x/greptile-reviewer-agent-handoff.md"
  },
  "context": {
    "contract": ".harness/contracts/TASK-014.json",
    "checkpoint": ".harness/runs/TASK-014/run-x/checkpoints/latest.json",
    "diff": ".harness/runs/TASK-014/run-x/diff.patch",
    "artifacts": []
  },
  "deliverable": {
    "kind": "review",
    "path": ".harness/runs/TASK-014/run-x/reviewer-output.md",
    "schema": "review_v1"
  }
}
```

### 9.6 Requisitos funcionais

- Todo subagente cria background ledger entry.
- Subagente deve declarar `role`, `mode`, `runtime_profile`,
  `permission_profile` e deliverable.
- Subagente isolado nao pode ler chat do pai.
- Subagente deve receber contexto via arquivos gerados e hashados.
- Resultado deve ser anexado ao run/artifact index quando houver `task_id`.
- Reviewer/evaluator existentes devem migrar para esse mecanismo.
- O pai deve receber notificacao/evento quando subagente termina.
- O hub deve animar subagente no setor correspondente.

### 9.7 CLI alvo

```powershell
python .\bin\harness.py --repo C:\repo subagent spawn `
  --role reviewer `
  --mode isolated `
  --task-id TASK-014 `
  --prompt .harness\runs\TASK-014\run-x\greptile-reviewer-agent-handoff.md `
  --runtime-profile codex-reviewer-standard `
  --permission-profile reviewer_readonly

python .\bin\harness.py --repo C:\repo subagent list
python .\bin\harness.py --repo C:\repo subagent result SUB-...
```

### 9.8 Criterios de aceite

- Reviewer e evaluator conseguem rodar como subagentes via ledger.
- Um subagente sem permissao de escrita nao consegue alterar repo.
- O hub mostra pai e subagente com relacao visual e status.
- O resultado do subagente fica em artifact index.
- Falha, timeout e cancelamento sao refletidos no task/report.

## 10. Modulo C: Runtime Adapter

### 10.1 Problema

O sidecar atual usa PTY como mecanismo principal. PTY e util para CLI humana,
mas insuficiente como contrato universal. Runtimes modernos podem oferecer API,
ACP, app-server, session resume, eventos estruturados, custos, tool calls e
resultados formais.

### 10.2 Objetivo

Criar uma camada `runtime_adapter` que permita iniciar, retomar, enviar input,
receber eventos, cancelar, coletar usage e anexar artefatos de diferentes
runtimes.

### 10.3 Runtimes alvo

- `pty`: comando local generico, fallback universal.
- `codex_cli`: Codex CLI via PTY ou exec/resume.
- `claude_cli`: Claude Code via CLI/PTY.
- `hermes`: Hermes Agent quando instalado.
- `openclaw`: OpenClaw runtime quando instalado.
- `acp`: Agent Client Protocol quando disponivel.
- `noop`: adapter de teste.

### 10.4 Interface conceitual

```python
class RuntimeAdapter:
    def health(self) -> RuntimeHealth: ...
    def start(self, request: RuntimeStartRequest) -> RuntimeSession: ...
    def resume(self, session_id: str) -> RuntimeSession: ...
    def send(self, session_id: str, message: RuntimeMessage) -> None: ...
    def events(self, session_id: str, cursor: str = "") -> RuntimeEventBatch: ...
    def cancel(self, session_id: str, reason: str) -> RuntimeCancelResult: ...
    def snapshot(self, session_id: str) -> RuntimeSnapshot: ...
```

### 10.5 Runtime start request

```jsonc
{
  "runtime": "codex_cli",
  "profile": "builder-standard",
  "repo_root": "C:/repo/app",
  "cwd": "C:/repo/app",
  "prompt_path": ".harness/background/prompts/BGT-...md",
  "env_policy": {
    "inherit": "minimal",
    "allow_env": ["PATH", "HOME"],
    "secret_refs": []
  },
  "permission_profile": "builder_write_scoped",
  "io": {
    "mode": "structured",
    "pty_fallback": true,
    "transcript_path": ".harness/agents/builder-1/transcript.jsonl"
  },
  "budgets": {
    "token_budget": 50000,
    "elapsed_seconds_budget": 3600
  }
}
```

### 10.6 Runtime event schema

```jsonc
{
  "id": "RTE-...",
  "session_id": "rt-codex-abc",
  "ts": "2026-05-29T16:00:00Z",
  "type": "message_delta",
  "source": "runtime",
  "payload": {},
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "cost_usd": 0.0
  }
}
```

Event types:

- `session_started`
- `session_resumed`
- `message_started`
- `message_delta`
- `message_completed`
- `tool_call_started`
- `tool_call_completed`
- `shell_command_requested`
- `shell_command_completed`
- `approval_requested`
- `approval_resolved`
- `usage_reported`
- `artifact_created`
- `session_failed`
- `session_cancelled`
- `session_completed`

### 10.7 Config de runtime

```jsonc
{
  "runtimes": {
    "default": "codex_cli",
    "profiles": {
      "builder-standard": {
        "adapter": "codex_cli",
        "model": "gpt-5-codex",
        "permission_profile": "builder_write_scoped",
        "context_mode": "contract_plus_checkpoint"
      },
      "reviewer-standard": {
        "adapter": "codex_cli",
        "permission_profile": "reviewer_readonly",
        "context_mode": "isolated_handoff"
      }
    },
    "adapters": {
      "codex_cli": {
        "cmd": ["codex"],
        "transport": "pty",
        "supports_resume": true
      },
      "acp": {
        "cmd": ["agent-server"],
        "transport": "jsonrpc",
        "supports_events": true
      }
    }
  }
}
```

### 10.8 Requisitos funcionais

- O runtime adapter deve ser chamado pelo background ledger, nao diretamente
  pela UI.
- PTY continua existindo como fallback e modo interativo.
- Runtimes estruturados devem fornecer eventos para o ledger.
- Usage deve ser normalizado.
- Runtime profiles devem selecionar permission profiles por padrao.
- O hub deve mostrar runtime, session id, health, usage e transport.
- O adapter deve expor `health` para diagnostico.

### 10.9 Criterios de aceite

- Um mesmo subagent spec roda com adapter `noop`, `pty` e `codex_cli`.
- Cancelamento funciona de forma uniforme.
- Eventos sao persistidos no background log.
- O hub nao precisa saber qual runtime esta por baixo para mostrar status.
- Testes simulam runtime sem instalar Codex/Claude/Hermes/OpenClaw.

## 11. Modulo D: Seguranca granular por agente

### 11.1 Problema

Spawnar terminal/LLM pela web e RCE por design. O gate atual
`hub.allow_remote_execution` e necessario, mas grosseiro. Antes de adicionar
mais canais ou autonomia, Runforge precisa de permissoes por agente, por runtime
e por capability.

### 11.2 Objetivo

Criar um modelo de permissao local, auditavel e composable. Cada agente deve
rodar com um `permission_profile` explicito, com allow/deny para filesystem,
shell, network, secrets, MCP, skills, git, GitHub, Telegram e writes.

### 11.3 Permission profile

```jsonc
{
  "id": "builder_write_scoped",
  "label": "Builder: write scoped",
  "description": "Can edit contracted files and run reviewed sensors.",
  "applies_to_roles": ["builder"],
  "filesystem": {
    "read": ["."],
    "write": ["src/**", "tests/**", ".harness/runs/**"],
    "deny": [".env", ".git/**", ".harness/plugins/secrets/**"],
    "require_contract_expected_files": true
  },
  "shell": {
    "enabled": true,
    "allowed_commands": ["npm", "pnpm", "python", "git"],
    "denied_patterns": ["rm -rf", "git reset --hard", "curl | sh"],
    "requires_approval_patterns": ["npm install", "pip install", "git push"]
  },
  "network": {
    "enabled": false,
    "allowed_hosts": [],
    "requires_approval": true
  },
  "secrets": {
    "read_env": [],
    "redact_patterns": ["openai_key", "github_token", "telegram_bot_token"]
  },
  "runtime": {
    "allowed_adapters": ["codex_cli", "pty"],
    "max_parallel_sessions": 2
  },
  "mcp": {
    "allowed_servers": [],
    "allowed_tools": []
  },
  "approval": {
    "interactive_required": false,
    "timeout_seconds": 600,
    "default_on_timeout": "deny"
  }
}
```

### 11.4 Approval request

```jsonc
{
  "id": "APR-20260529-a1b2",
  "background_id": "BGT-...",
  "agent_id": "builder-1",
  "repo_root": "C:/repo/app",
  "kind": "shell_command",
  "summary": "Run npm install to add dependency",
  "requested_action": {
    "command": "npm install zod",
    "cwd": "C:/repo/app"
  },
  "risk": "medium",
  "policy_reason": "command_matches_requires_approval",
  "status": "pending",
  "created_at": "2026-05-29T16:20:00Z",
  "expires_at": "2026-05-29T16:30:00Z",
  "decision": {
    "status": "",
    "by": "",
    "reason": "",
    "decided_at": ""
  }
}
```

### 11.5 Arquivos

```text
.harness/security/
  permissions.json
  approvals/
    index.json
    APR-*.json
  audit.jsonl
```

### 11.6 Requisitos funcionais

- Todo agente deve ter `permission_profile`.
- Se ausente, usar perfil seguro por role:
  - reviewer/evaluator/security: readonly;
  - builder: write scoped;
  - research: network gated;
  - operator: interactive.
- Shell commands devem passar por policy engine antes de executar quando
  executados por adapter integrado.
- PTY puro deve ser marcado como high-risk se nao houver interceptacao de
  comandos.
- Writes fora do repo ou fora de expected files devem bloquear ou pedir
  aprovacao.
- Secrets nunca devem ser serializados em transcript, event payload ou report.
- Approval queue deve aparecer no hub.
- Toda decisao de aprovacao deve ir para audit log.

### 11.7 Criterios de aceite

- Spawn sem permission profile recebe default seguro.
- Agente readonly falha ao tentar write.
- Comando sensitivo gera approval pendente.
- Negar approval cancela a acao e registra evento.
- Aprovar executa e registra quem aprovou, quando e por que.
- Security scanner detecta permission drift.

## 12. Modulo E: Skills e MCP como lojas no hub

### 12.1 Problema

Skills e MCPs existem como capacidades tecnicas, mas nao como produto. O
operador precisa ver o que esta instalado, o que cada capability pode fazer,
qual permissao exige, quais agentes podem usar e se esta saudavel.

### 12.2 Objetivo

Criar duas lojas locais dentro do hub:

- Skill Store: skills instaladas/disponiveis, com manifesto, risco e roles.
- MCP Store: servidores MCP configuraveis, tools expostas, secrets e health.

### 12.3 Skill manifest

```jsonc
{
  "id": "greptile-review",
  "name": "Greptile Review",
  "version": "1.0.0",
  "kind": "skill",
  "source": {
    "type": "local",
    "path": "C:/Users/Schulx/.agents/skills/greptile-review"
  },
  "description": "Code review handoff and findings workflow.",
  "roles": ["reviewer"],
  "capabilities": ["read_diff", "write_review", "create_followups"],
  "permissions": {
    "filesystem_read": ["."],
    "filesystem_write": [".harness/runs/**"],
    "network": false,
    "secrets": []
  },
  "risk": "low",
  "status": "enabled",
  "health": {
    "state": "ok",
    "last_checked_at": "2026-05-29T16:30:00Z"
  }
}
```

### 12.4 MCP manifest

```jsonc
{
  "id": "github",
  "name": "GitHub MCP",
  "kind": "mcp_server",
  "transport": "stdio",
  "command": ["github-mcp-server"],
  "tools": [
    {
      "name": "create_issue",
      "risk": "medium",
      "requires_approval": true
    }
  ],
  "secrets": ["GITHUB_TOKEN"],
  "allowed_roles": ["operator", "release"],
  "status": "disabled",
  "health": {
    "state": "unknown",
    "last_checked_at": ""
  }
}
```

### 12.5 Arquivos

```text
.harness/capabilities/
  skills.json
  mcp.json
  marketplace-cache.json
  health.json
```

### 12.6 UX no hub

Skill Store deve mostrar:

- cards por skill;
- status enabled/disabled;
- roles permitidos;
- risco;
- arquivos/comandos permitidos;
- ultimo health check;
- botao enable/disable;
- botao test;
- botao view manifest.

MCP Store deve mostrar:

- servidores configurados;
- tools expostas;
- secrets necessarios;
- agents autorizados;
- approval policy por tool;
- logs de chamadas.

### 12.7 Requisitos funcionais

- Skills precisam de manifesto normalizado mesmo quando herdadas de skills
  locais antigas.
- Habilitar skill deve exigir review de permissoes se risco medio/alto.
- MCP server nao pode iniciar se faltarem secrets obrigatorios.
- Tools MCP devem ser filtradas por permission profile do agente.
- Chamadas MCP devem entrar no background/event audit quando gerarem mutacao.
- Skills/MCPs podem ser vinculados a runtime profiles e agent roles.

### 12.8 CLI alvo

```powershell
python .\bin\harness.py --repo C:\repo capability skills list
python .\bin\harness.py --repo C:\repo capability skills enable greptile-review
python .\bin\harness.py --repo C:\repo capability skills disable greptile-review
python .\bin\harness.py --repo C:\repo capability skills test greptile-review

python .\bin\harness.py --repo C:\repo capability mcp list
python .\bin\harness.py --repo C:\repo capability mcp add github --command github-mcp-server
python .\bin\harness.py --repo C:\repo capability mcp health github
```

### 12.9 Criterios de aceite

- Hub mostra skills e MCPs instalados.
- Habilitar skill de risco medio gera approval.
- Agente sem permissao nao ve tool MCP proibida.
- Health check falho aparece no mapa/loja.
- Todas as chamadas mutaveis ficam auditaveis.

## 13. Modulo F: Cron e Standing Orders

### 13.1 Problema

O hub so fica vivo quando o operador interage. Para virar operations hub, ele
precisa rodar rotinas seguras: revisar fila, auditar repos, checar sensores,
resumir progresso, gerar relatorios, abrir follow-ups e lembrar decisoes.

### 13.2 Objetivo

Permitir automacoes recorrentes com limites fortes, descricao humana e output
auditavel.

### 13.3 Conceitos

#### Schedule

Define quando algo roda.

#### Standing order

Define o que um agente deve fazer de forma recorrente, com escopo, permissoes,
criterio de parada e formato de entrega.

### 13.4 Schedule model

```jsonc
{
  "id": "SCH-daily-audit",
  "enabled": true,
  "repo_scope": ["C:/repo/app"],
  "trigger": {
    "type": "cron",
    "expression": "0 9 * * 1-5",
    "timezone": "America/Sao_Paulo"
  },
  "standing_order_id": "SO-daily-audit",
  "last_run_at": "",
  "next_run_at": "2026-05-30T12:00:00Z",
  "max_concurrent": 1
}
```

### 13.5 Standing order model

```jsonc
{
  "id": "SO-daily-audit",
  "title": "Daily repo health audit",
  "enabled": true,
  "agent_role": "security",
  "runtime_profile": "security-standard",
  "permission_profile": "security_readonly",
  "objective": "Check queue, stale runs, security findings and missing reports.",
  "scope": {
    "repos": ["registered"],
    "tasks": ["active", "needs_work", "queued"]
  },
  "instructions_path": ".harness/standing-orders/daily-audit.md",
  "output": {
    "kind": "report",
    "path_template": ".harness/reports/daily-audit-{date}.md"
  },
  "limits": {
    "max_elapsed_seconds": 900,
    "max_background_tasks": 3,
    "max_cost_usd": 1.0
  },
  "approval": {
    "before_run": false,
    "before_mutation": true
  }
}
```

### 13.6 Arquivos

```text
.harness/schedules/
  index.json
  SCH-*.json
.harness/standing-orders/
  index.json
  SO-*.json
  *.md
```

### 13.7 Triggers suportados

P0:

- manual;
- interval;
- daily time;
- event match.

P1:

- cron expression;
- file change;
- queue threshold;
- stale run;
- failed sensor.

### 13.8 Requisitos funcionais

- Schedule nunca executa se `enabled=false`.
- Schedule deve criar background task para cada execucao.
- Standing order deve declarar runtime e permission profile.
- Execucao recorrente nao pode marcar task como passed sem politica completa.
- O hub deve mostrar proximas rotinas e ultimas execucoes.
- O operador pode pause/resume/cancel.
- Event-triggered schedules precisam de debounce.

### 13.9 Exemplos de standing orders iniciais

1. Daily health audit: revisar filas, runs perdidas e findings.
2. Stale context watcher: detectar docs required alterados.
3. Needs-work triage: resumir tasks travadas e sugerir proximo passo.
4. PR prep: gerar PR summary quando task passou.
5. Security patrol: rodar scanner e reportar drift de permissoes.
6. Skill health: testar skills/MCPs habilitados.

### 13.10 Criterios de aceite

- Criar schedule manual e interval via CLI.
- Scheduler cria background task no tempo correto.
- Standing order gera report local.
- Pausar schedule impede novas execucoes.
- Hub mostra agente/rotina andando pelo mapa durante execucao.

## 14. UX do hub gamificado

### 14.1 Objetivo de UX

O hub deve fazer o operador entender o sistema em segundos:

- qual repo esta ativo;
- quais agentes existem;
- qual agente trabalha em que setor;
- qual runtime cada agente usa;
- quais background tasks estao rodando;
- que aprovacoes precisam de decisao;
- que riscos bloqueiam progresso;
- que automacoes estao agendadas.

### 14.2 Mapa

Setores permanentes por repo:

- Planning Cabin: contratos, backlog, standing orders.
- Forge: builders e runs de implementacao.
- Library: reviewers/evaluators.
- Research Tower: research/subagents de investigacao.
- Watch Tower: security, approvals e permission drift.
- Records Office: reports, artifacts e memory.
- Portal/Gate: runtimes, skills e MCP store.
- Courtyard: idle agents e onboarding.

### 14.3 Visualizacao de background ledger

Cada background task deve aparecer como:

- icone pequeno no agente;
- trilha ate setor;
- badge de status;
- linha no inspector;
- evento na timeline.

Estados visuais:

- queued: agente aguardando com icone de relogio;
- running: agente no setor com animacao de trabalho;
- waiting_for_approval: agente parado na Watch Tower;
- succeeded: entrega envelope/report;
- failed: marcador vermelho no setor;
- cancelled: fade out controlado;
- lost: offline/glitch.

### 14.4 Inspector

Ao clicar agente:

- nome, role, runtime, profile;
- permission profile;
- task atual;
- background task atual;
- ultimo evento;
- uso/custo;
- artifacts;
- botoes permitidos:
  - open terminal;
  - pause;
  - cancel;
  - message;
  - view transcript;
  - view permissions.

Ao clicar setor:

- tasks associadas;
- agentes no setor;
- background tasks;
- aprovacoes;
- artifacts recentes;
- actions contextuais.

### 14.5 Loja de skills/MCPs

Visual no mapa:

- Portal/Gate ou Marketplace building.
- Skills aparecem como itens/placas.
- MCP servers aparecem como consoles.
- Health falho aparece como luz vermelha.

### 14.6 Cron/standing orders

Visual no mapa:

- Board de rotinas na Planning Cabin.
- Agente de rotina aparece no horario.
- Proxima execucao aparece como agenda.
- Falha recorrente aparece como alerta persistente.

## 15. Dados e eventos

### 15.1 Eventos novos

Background:

- `background_created`
- `background_queued`
- `background_started`
- `background_waiting_for_approval`
- `background_succeeded`
- `background_failed`
- `background_timed_out`
- `background_cancelled`
- `background_lost`

Subagents:

- `subagent_spawned`
- `subagent_completed`
- `subagent_failed`
- `subagent_result_attached`

Runtimes:

- `runtime_session_started`
- `runtime_session_resumed`
- `runtime_session_completed`
- `runtime_session_failed`
- `runtime_usage_reported`

Security:

- `approval_requested`
- `approval_approved`
- `approval_denied`
- `permission_denied`
- `permission_profile_changed`
- `security_policy_drift_detected`

Capabilities:

- `skill_enabled`
- `skill_disabled`
- `skill_health_checked`
- `mcp_server_added`
- `mcp_server_enabled`
- `mcp_server_disabled`
- `mcp_tool_called`

Schedules:

- `schedule_created`
- `schedule_enabled`
- `schedule_disabled`
- `schedule_triggered`
- `standing_order_started`
- `standing_order_completed`

### 15.2 Event envelope

```jsonc
{
  "id": "EVT-...",
  "ts": "2026-05-29T16:45:00Z",
  "type": "background_started",
  "source": "runforge",
  "project": "app",
  "root": "C:/repo/app",
  "task_id": "TASK-014",
  "run_dir": ".harness/runs/TASK-014/run-x",
  "agent_id": "builder-1",
  "background_id": "BGT-...",
  "payload": {},
  "visibility": {
    "safe_for_report": true,
    "contains_secret": false
  }
}
```

## 16. API e CLI geral

### 16.1 CLI namespaces

```text
background
subagent
runtime
permission
approval
capability
schedule
standing-order
agent
dashboard hub
```

### 16.2 Hub API namespaces

```text
/api/world
/api/events
/api/agents
/api/background
/api/subagents
/api/runtimes
/api/permissions
/api/approvals
/api/capabilities/skills
/api/capabilities/mcp
/api/schedules
/api/standing-orders
```

### 16.3 Mutations rule

Regra alvo:

- Node pode ler arquivos `.harness/` diretamente.
- Node deve chamar CLI Python para mutacoes de dominio.
- Node pode gerenciar ciclo de vida de PTY/runtime local quando essa for a
  responsabilidade do sidecar.
- Toda excecao deve ser documentada e coberta por audit log.

## 17. Seguranca e privacidade

### 17.1 Baseline

- Bind padrao `127.0.0.1`.
- Token obrigatorio para mutacoes.
- Origin loopback para WebSocket.
- `allow_remote_execution=false` por padrao.
- Permission profiles por agente.
- Approval queue para acoes sensitivas.
- Redacao de secrets em transcripts/events/reports.
- Audit log append-only.

### 17.2 Secrets

Secrets nunca devem aparecer em:

- `.harness/events.jsonl`;
- background logs;
- transcripts;
- reports;
- hub snapshots;
- browser console;
- error payloads.

### 17.3 Risk levels

- Low: read-only local, sem secrets, sem network.
- Medium: write em `.harness/`, GitHub issue, MCP read, package install.
- High: shell write amplo, network, git push, secrets, delete/move recursive.
- Critical: write fora do repo, exfiltracao, bypass policy, destructive git.

### 17.4 Blocking policy

Bloquear por padrao:

- permission profile ausente;
- repo nao registrado;
- runtime desconhecido;
- MCP tool nao allowlisted;
- secret necessario sem declaracao;
- network sem permissao;
- write fora do repo;
- final pass com background tasks blocking pendentes.

## 18. Observabilidade e metricas

### 18.1 Produto

- tempo ate primeiro agente spawnado;
- numero de background tasks por run;
- taxa de sucesso/falha/cancelamento;
- tempo medio em `waiting_for_approval`;
- numero de tasks salvas por subagentes;
- numero de findings bloqueantes detectados antes de pass;
- uso de skills/MCPs;
- schedules ativos.

### 18.2 Engenharia

- eventos perdidos por cursor;
- JSON read failures;
- runtime health failures;
- PTY spawn failures;
- tasks lost apos restart;
- tamanho de transcripts;
- tempo de snapshot `/api/world`;
- tempo de render do hub.

### 18.3 Usage/cost

```jsonc
{
  "agent_id": "builder-1",
  "background_id": "BGT-...",
  "runtime": "codex_cli",
  "tokens_in": 12000,
  "tokens_out": 3200,
  "cost_usd": 0.42,
  "commands": 8,
  "duration_seconds": 740
}
```

## 19. Milestones

### M1: Ledger foundation

Escopo:

- background ledger files;
- CLI list/show/cancel/retry;
- events;
- hub read-only view;
- lost detection;
- unit tests.

DoD:

- toda execucao assicrona nova consegue aparecer no ledger;
- restart marca runtime sem sessao como lost;
- hub mostra ledger por repo/agente.

### M2: Subagents via ledger

Escopo:

- `subagent spawn`;
- isolated/fork modes;
- reviewer/evaluator migrados;
- result attachment;
- parent notification;
- hub visual relation.

DoD:

- evaluator e reviewer rodam como subagentes isolados;
- resultado bloqueante impede pass;
- subagente cancelado aparece no report.

### M3: Runtime adapter

Escopo:

- adapter interface;
- noop adapter;
- pty adapter;
- codex_cli adapter;
- runtime profiles;
- usage/event normalization.

DoD:

- mesmo subagent roda em noop/pty/codex_cli;
- hub mostra runtime health e session status;
- cancelamento uniforme.

### M4: Agent permissions and approvals

Escopo:

- permission profiles;
- approval queue;
- policy checks;
- security audit log;
- hub Watch Tower UI.

DoD:

- agente readonly nao escreve;
- comando sensitivo pede aprovacao;
- negacao bloqueia acao e registra evento;
- scanner detecta drift.

### M5: Skills/MCP store

Escopo:

- manifests;
- skill list/enable/disable/test;
- MCP add/list/health;
- permission binding;
- hub store UI.

DoD:

- skill de review pode ser habilitada para reviewer;
- MCP tool mutavel pede approval;
- health falho aparece no hub.

### M6: Cron/standing orders

Escopo:

- schedules;
- standing orders;
- scheduler loop;
- manual/interval/daily/event triggers;
- reports recorrentes;
- hub routines UI.

DoD:

- rotina daily audit roda e gera background task/report;
- schedule pode pausar/retomar;
- execucao recorrente respeita permissoes.

### M7: Polish and hardening

Escopo:

- transcripts persistidos com redacao;
- migration docs;
- integration tests E2E;
- performance pass;
- docs publicas com nome Runforge.

DoD:

- fluxo spawn -> terminal -> task -> subagent -> approval -> report funciona
  end-to-end em repo local.

## 20. User stories

### 20.1 Background ledger

Como operador, quero ver todas as tarefas em background para saber o que ainda
esta rodando antes de fechar uma run.

Aceite:

- vejo background tasks running/failed/succeeded;
- posso abrir detalhes;
- posso cancelar;
- vejo artifacts e resultado.

### 20.2 Subagente reviewer

Como builder, quero disparar um reviewer isolado para revisar meu diff sem
herdar meu contexto e sem poder editar arquivos.

Aceite:

- reviewer recebe handoff isolado;
- nao tem permissao de escrita;
- resultado entra no report;
- P0/P1 bloqueia.

### 20.3 Runtime adapter

Como operador, quero escolher Codex, Claude, Hermes, OpenClaw ou ACP por perfil
sem alterar o fluxo de task.

Aceite:

- runtime profile seleciona adapter;
- UI mostra adapter ativo;
- cancelamento funciona;
- eventos ficam normalizados.

### 20.4 Approval queue

Como operador, quero aprovar comandos arriscados antes que o agente execute.

Aceite:

- comando gera approval;
- hub mostra alerta;
- posso aprovar/negar com motivo;
- decisao fica auditada.

### 20.5 Skill Store

Como builder de agentes, quero habilitar uma skill apenas para agentes
especificos e ver que permissoes ela pede.

Aceite:

- skill mostra manifest;
- enable exige approval se risco medio/alto;
- agente sem role permitida nao usa.

### 20.6 MCP Store

Como operador, quero adicionar um MCP server e restringir tools por agente.

Aceite:

- servidor aparece no hub;
- health check roda;
- tools mutaveis pedem approval;
- secrets nao aparecem em logs.

### 20.7 Standing order

Como tech lead, quero uma rotina diaria que audite repos e gere resumo sem eu
precisar pedir todo dia.

Aceite:

- schedule dispara;
- security agent roda;
- report e gerado;
- falhas aparecem no hub.

## 21. Acceptance global

Runforge vNext sera considerado pronto quando:

1. background ledger for a base de toda execucao paralela;
2. reviewer/evaluator rodarem como subagentes isolados;
3. pelo menos dois runtime adapters funcionarem alem de noop;
4. agentes tiverem permission profiles obrigatorios;
5. approval queue bloquear acoes sensitivas;
6. hub mostrar background tasks, runtime, permissoes e approvals;
7. skills/MCPs tiverem manifests e health;
8. pelo menos uma standing order recorrente funcionar;
9. final report incluir subagents, background tasks, approvals e riscos;
10. testes cobrirem ledger, subagents, runtime adapter, permissions e schedules.

## 22. Riscos

### 22.1 RCE local

Risco: hub com runtime/PTY pode executar comandos perigosos.

Mitigacao:

- permission profiles;
- approval queue;
- bind loopback;
- token;
- scanner;
- audit log;
- default deny.

### 22.2 Runtime heterogeneo

Risco: Codex, Claude, Hermes, OpenClaw e ACP tem semanticas diferentes.

Mitigacao:

- adapter interface minima;
- PTY fallback;
- health checks;
- evento normalizado;
- capability flags por adapter.

### 22.3 Estado local crescendo demais

Risco: `.harness/` ficar pesado com transcripts e logs.

Mitigacao:

- prune;
- retention policy;
- artifact index;
- compression futura;
- safe-to-share metadata.

### 22.4 Gamificacao virar decoracao

Risco: mapa bonito, mas operacionalmente irrelevante.

Mitigacao:

- todo elemento visual deve refletir estado real;
- cada alerta visual deve linkar para ledger/event/artifact;
- sem personagem fake quando ha agente real.

### 22.5 Autonomia sem governanca

Risco: cron/standing orders abrirem loop autonomo perigoso.

Mitigacao:

- standing orders com limites;
- approval before mutation;
- max concurrent;
- max cost;
- max background tasks;
- explicit enabled flag.

## 23. Decisoes fechadas para implementacao

Esta secao fecha as decisoes que estavam abertas no PRD. O implementador deve
seguir estas escolhas sem reabrir arquitetura durante a execucao, exceto se um
teste ou limitacao de plataforma provar impossibilidade tecnica.

### 23.1 Ownership de runtime

Decisao: a interface de runtime, profiles, policy checks, ledger linkage e
event normalization vivem no core Python, em `harness_core/runtime/`.

Racional:

- o core Python ja e a fonte de verdade de tasks, contratos, sensores, runs,
  reports e policies;
- o background ledger tambem vive no core Python;
- testes precisam simular runtime sem depender do sidecar Node;
- o sidecar Node deve continuar sendo transporte/UX local, nao dono do dominio.

Divisao final:

```text
harness_core/runtime/
  __init__.py
  base.py             # RuntimeAdapter, requests, events, result types
  registry.py         # resolve adapter/profile from config
  noop.py             # test adapter
  subprocess_cli.py   # generic non-interactive CLI adapter
  codex_cli.py        # first real adapter
  pty_proxy.py        # optional proxy to sidecar PTY for interactive sessions

hub/server/
  pty.js              # owns live ConPTY/node-pty lifecycle only
  runtime-bridge.js   # exposes PTY attach/status to browser, not domain policy
```

Node may manage live PTY sessions because ConPTY is a Node-side dependency in
this repo. Node must not become the canonical runtime ledger.

### 23.2 PTY usage

Decisao: PTY puro e permitido apenas para interactive agents e operator-driven
sessions. Non-interactive subagents must use structured or subprocess runtime
adapters.

Rules:

- `mode=interactive` may use PTY.
- `mode=isolated` and `mode=fork` must default to `codex_cli`,
  `subprocess_cli`, `noop` or future structured adapters.
- PTY sessions are always high-risk unless attached to an explicit
  `permission_profile`.
- PTY cannot be the only evidence source for a background task; the task must
  still write result/artifact files.
- PTY scrollback is not a report. Reports must reference redacted artifacts.

### 23.3 First real runtime adapter

Decisao: implement in this order:

1. `noop`: deterministic test adapter.
2. `subprocess_cli`: generic command adapter used by tests and local tools.
3. `codex_cli`: first real LLM adapter.
4. `pty_proxy`: interactive adapter through sidecar Node.
5. `acp`: first structured protocol adapter after Codex CLI.
6. `claude_cli`, `hermes`, `openclaw`: later adapters using the same interface.

Racional:

- Codex is already the dominant workflow in this repo;
- `noop` and `subprocess_cli` make the ledger/subagent architecture testable
  before external LLM behavior;
- ACP should come after the adapter boundary is proven.

### 23.4 Scheduler ownership

Decisao: schedules and standing orders run in Python, not in Node.

Implementation:

```powershell
python .\bin\harness.py --repo C:\repo scheduler run
python .\bin\harness.py --repo C:\repo scheduler tick
```

Rules:

- Node may show schedules and call CLI actions.
- Node must not independently decide schedule eligibility.
- `scheduler tick` is deterministic and testable.
- `scheduler run` is a long-running loop that repeatedly calls `tick`.
- If sidecar Node is running, it can display scheduler state but not own it.

### 23.5 Channels and remote access

Decisao: no new cloud/channel surfaces until permission profiles, approvals and
redaction are implemented.

Allowed before M4:

- local CLI;
- local hub on loopback;
- existing Telegram behavior as-is, without expanding remote execution;
- tests/mocks.

Blocked before M4:

- Discord/Slack/new cloud channels;
- remote browser access;
- non-loopback hub binding;
- webhook-triggered execution.

### 23.6 Branding migration

Decisao: product naming moves to Runforge now; public compatibility surfaces
stay stable.

Rules:

- README, docs and hub UI should say `Runforge`.
- Existing `bin/harness.py` remains the stable CLI entrypoint for compatibility.
- `.harness/` remains the state directory for compatibility.
- The internal term "harness" remains valid for the governed execution engine.
- Config should add:

```jsonc
{
  "product_name": "Runforge",
  "state_dir_name": ".harness"
}
```

No implementation should rename `.harness/` in this phase.

### 23.7 State schema versioning

Decisao: every new top-level state file must include `schema_version`.

Required:

```jsonc
{
  "schema_version": 1,
  "updated_at": "2026-05-29T00:00:00Z"
}
```

Files requiring schema version:

- `.harness/background/index.json`
- `.harness/background/tasks/*.json`
- `.harness/security/permissions.json`
- `.harness/security/approvals/index.json`
- `.harness/capabilities/skills.json`
- `.harness/capabilities/mcp.json`
- `.harness/schedules/index.json`
- `.harness/standing-orders/index.json`
- runtime profile config.

Migration rule:

- missing `schema_version` means version `0`;
- loaders must normalize version `0` in memory;
- writers must persist version `1`.

### 23.8 File locking and concurrency

Decisao: atomic writes are necessary but not sufficient. New mutable indexes use
an advisory lock.

Implementation:

```text
.harness/locks/
  background.lock
  approvals.lock
  capabilities.lock
  schedules.lock
```

Lock behavior:

- acquire by creating the lock file exclusively;
- lock file stores pid, command, created_at and expires_at;
- default lock timeout: 30 seconds;
- stale lock timeout: 120 seconds;
- failure to acquire lock must fail closed for mutating commands;
- read-only commands never require lock.

All writes still use temp file + `os.replace`.

### 23.9 ID generation

Decisao: IDs are deterministic in format, unique by timestamp + random suffix,
and never reused.

Formats:

```text
BGT-YYYYMMDD-HHMMSS-xxxxxxxx   background task
SUB-YYYYMMDD-HHMMSS-xxxxxxxx   subagent
APR-YYYYMMDD-HHMMSS-xxxxxxxx   approval
SCH-<slug>                     schedule
SO-<slug>                      standing order
RTE-YYYYMMDD-HHMMSS-xxxxxxxx   runtime event
RTS-YYYYMMDD-HHMMSS-xxxxxxxx   runtime session
CAP-<slug>                     capability if generated
```

Rules:

- `xxxxxxxx` is 8 lowercase hex chars from secure randomness.
- Human-created schedules and standing orders use stable slugs.
- Collision handling retries up to 5 times, then fails.

### 23.10 Mutations rule

Decisao: all domain mutations must go through Python CLI or Python core APIs.

Allowed direct Node writes:

- ephemeral PTY ring buffer in memory;
- WebSocket client state;
- static asset serving;
- process lifecycle metadata held only in Node memory.

Not allowed as final architecture:

- Node directly writing `.harness/agents/registry.json`;
- Node directly appending domain events;
- Node directly writing `agent-messages.jsonl`;
- Node directly changing queue/background/security/capability state.

Transition rule:

- existing direct writes in Node are accepted as current technical debt;
- M1/M2 implementation must move them behind Python CLI commands before adding
  broader autonomy.

### 23.11 Cost and usage when runtime does not report tokens

Decisao: use nullable usage fields plus confidence metadata.

Schema:

```jsonc
{
  "tokens_in": null,
  "tokens_out": null,
  "cost_usd": null,
  "commands": 3,
  "duration_seconds": 420,
  "source": "estimated|reported|unavailable",
  "confidence": "high|medium|low|none"
}
```

Rules:

- never invent exact token/cost numbers;
- if unknown, store `null`;
- reports may show duration/commands as fallback;
- budget enforcement on unknown token usage uses elapsed time and command count.

### 23.12 Skill trust model

Decisao: v1 requires hashes, not cryptographic signatures.

Rules:

- every enabled skill stores SHA-256 of `SKILL.md` and manifest at enable time;
- local skills are trusted only by explicit enablement;
- changed hash turns skill health to `changed_requires_review`;
- remote marketplace install is out of scope for v1 unless a lockfile with
  source URL and expected SHA-256 is provided;
- signatures can be added later without changing the manifest shape.

### 23.13 MCP trust model

Decisao: MCP servers are disabled by default and tool-level allowlists are
mandatory.

Rules:

- adding a server does not enable it;
- enabling requires health check;
- every exposed tool has risk level;
- mutating tools default to `requires_approval=true`;
- secrets are referenced by env var name only, never stored in config;
- MCP calls that mutate external state create audit events.

### 23.14 Default permission profiles

Decisao: ship these built-in profiles first:

```text
operator_interactive
builder_write_scoped
reviewer_readonly
evaluator_readonly
security_readonly
research_network_gated
docs_write_scoped
qa_test_runner
release_gated
```

Role defaults:

```text
builder   -> builder_write_scoped
reviewer  -> reviewer_readonly
evaluator -> evaluator_readonly
security  -> security_readonly
research  -> research_network_gated
docs      -> docs_write_scoped
qa        -> qa_test_runner
release   -> release_gated
operator  -> operator_interactive
```

Missing profile blocks spawn.

### 23.15 Redaction

Decisao: all text leaving a runtime must pass through a central redactor before
being persisted outside volatile memory.

Apply redaction before writing:

- events;
- transcripts;
- background logs;
- reports;
- approval payloads;
- runtime error messages;
- browser-visible API payloads.

Redactor inputs:

- existing `SECRET_PATTERNS`;
- configured `secrets.redact_patterns`;
- env var names declared in runtime/MCP config;
- provider-specific token patterns.

Redaction marker:

```text
[REDACTED:<pattern_id>]
```

### 23.16 Retention and pruning

Decisao: nothing is pruned automatically in v1 except volatile in-memory PTY
scrollback.

Defaults:

- PTY scrollback memory limit: existing hub config default.
- Background logs: keep until explicit prune.
- Transcripts: keep until explicit prune.
- Reports/artifacts: keep until explicit prune.
- `prune --older-than` must require explicit CLI invocation.

Future auto-prune must be opt-in.

### 23.17 Hub render engine

Decisao: continue with the current canvas 2D + tile renderer. Do not migrate to
Kaplay in this roadmap.

Rules:

- Kaplay may remain installed temporarily because it already exists in
  `hub/package.json`, but it is not an architectural dependency and must not be
  used for new vNext work;
- map generation remains semantic/procedural with Kenney tiles;
- Tiled import remains optional future work, not part of these milestones;
- xterm.js ja cobre o terminal interativo basico; M7 deve focar persistencia,
  redacao e polish de terminal.

Racional:

- current hub already has real tiles, deterministic mapgen, sprites and menu;
- migrating engine now would distract from ledger/runtime/security work;
- product value is operational state, not game engine purity.

### 23.18 Runtime result schemas

Decisao: each subagent deliverable must declare one of these initial result
schemas:

```text
review_v1
evaluation_v1
security_scan_v1
research_note_v1
docs_patch_v1
qa_result_v1
release_note_v1
freeform_markdown_v1
```

Rules:

- blocking automation only reads structured schemas, not arbitrary prose;
- freeform markdown can be attached as artifact but cannot by itself mark pass;
- evaluator/reviewer/security schemas feed final report and failure policy.

### 23.19 Scheduler trigger scope

Decisao: M6 ships only `manual`, `interval`, `daily_time` and `event_match`.

Out of M6:

- full cron expression parser;
- file watch daemon;
- queue threshold trigger;
- failed sensor trigger.

Those remain P1 follow-ups after the scheduler loop is stable.

### 23.20 Test strategy

Decisao: every milestone requires deterministic tests before UI polish.

Required per milestone:

- Python unit tests for state loaders/writers and policy logic.
- Python integration tests using temp repos.
- Node unit tests for sidecar API/security when hub changes.
- No real LLM/provider in CI.
- `noop` runtime tests for success/failure/timeout/cancel.
- One local E2E smoke by M7: spawn -> background -> subagent -> approval ->
  report.

### 23.21 Packaging

Decisao: keep Python zero-runtime-dependency. Node remains optional under `hub/`.

Rules:

- background ledger, permission policy, runtime registry and scheduler must not
  require Node;
- hub requires Node only for browser/PTY UX;
- provider-specific adapters must fail with clear health errors if their CLI is
  missing.

## 24. Sequenciamento fechado

Implementar nesta ordem:

1. Implementar background ledger minimalista.
2. Migrar evaluator/reviewer para subagents isolados usando
   `noop`/`subprocess_cli` primeiro, depois `codex_cli`.
3. Extrair runtime adapter e plugar Codex CLI.
4. Criar permission profiles e approval queue.
5. Integrar hub visual para ledger/approvals/runtime.
6. Criar Skill Store/MCP Store em modo read-only primeiro.
7. Habilitar enable/disable/test com audit.
8. Implementar standing orders com trigger manual e interval.
9. Adicionar daily audit como primeira rotina oficial.
10. Atualizar branding/docs para Runforge.

## 25. Definicao curta do produto

Runforge e um harness local-first e operations hub gamificado para agentes de
codigo. Ele transforma prompts, issues e rotinas em runs governadas por
contratos, sensores, subagentes isolados, runtime adapters, permissoes
granulares, skills/MCPs auditaveis, standing orders e relatorios com evidencia.

## 26. Lacunas eliminadas nesta revisao

Esta revisao removeu as decisoes que ainda poderiam travar a implementacao.

Fechado:

- runtime adapter fica no core Python;
- Node fica como sidecar de browser, realtime e PTY interativo;
- PTY puro e restrito a agentes interativos;
- primeiro adapter real e `codex_cli`;
- scheduler roda no Python;
- novos canais externos ficam bloqueados ate seguranca granular;
- branding passa a Runforge agora, mantendo `bin/harness.py` e `.harness/`;
- todos os novos estados ganham `schema_version`;
- indexes mutaveis usam advisory locks;
- IDs seguem formato unico por tipo;
- mutacoes de dominio devem passar pelo Python;
- custo desconhecido usa `null`, nunca estimativa falsa;
- skills v1 exigem hash, nao assinatura;
- MCP e disabled-by-default com allowlist por tool;
- default permission profiles foram nomeados;
- redaction central e obrigatoria antes de persistencia;
- pruning automatico fica fora do v1;
- hub segue canvas 2D + tiles, sem migrar para Kaplay;
- deliverables de subagentes usam schemas nomeados;
- M6 inclui apenas triggers simples;
- cada milestone exige testes deterministicos antes de polish;
- Python continua zero-runtime-dependency e Node continua opcional.

Ainda pode haver detalhamento por issue, mas nao deve haver escolha
arquitetural pendente para iniciar implementacao.
