---
name: harness-runner
description: "Use quando trabalho planejado em repo precisar passar pelo protocolo Harness: converter issues em contratos de task, iniciar runs de implementacao, usar TDD com escopo limitado, rodar sensores deterministicos revisados, gerar brief/handoff de avaliador spawnado, gerar handoff de reviewer Greptile-style, registrar decisoes pass/fail e produzir relatorios. Acione depois de fluxos Grillme, PRD ou quebra em issues quando o usuario quiser implementar uma issue com evidencia e memoria."
---

# Harness Runner

Use o Harness Runner como camada operacional ao redor das skills de planejamento e codigo.
Nao substitua Grillme, PRD, issues ou TDD. Coloque essas etapas em um protocolo repetivel.

## CLI

Caminho local padrao depois de clonar este repo:

```powershell
<harness-schulx>\bin\harness.py
```

Use um caminho real e existente de repo via variavel. Nao rode placeholders literais:

```powershell
$HARNESS = "C:\path\to\harness-schulx\bin\harness.py" # trocar pelo caminho real
$APP_REPO = "C:\path\to\your-app" # trocar por um repo real existente
Test-Path -LiteralPath $APP_REPO
python $HARNESS --repo $APP_REPO <comando>
```

`init` nao cria o diretorio do repo por padrao. Use `init --create` apenas quando a criacao for intencional.

## Seguranca de branch

Comandos que escrevem arquivos ou rodam sensores sao bloqueados em `main`, `master` e `production`.
Crie uma branch de trabalho primeiro:

```powershell
git -C $APP_REPO switch -c harness/TASK-001
```

Se a excecao for intencional, passe `--allow-main` antes do comando:

```powershell
python <harness.py> --repo $APP_REPO --allow-main init
```

## Fluxo diario

1. Se o repo alvo nao tiver `.harness/config.json`, rode `init`.
2. Configure `required_context` em `.harness/config.json` para docs obrigatorios do projeto.
3. Ingira docs de contexto/PRD/arquitetura/ADR produzidos ou versionados no repo.
4. Rode `preflight` para confirmar que o contexto obrigatorio foi ingerido e nao mudou.
5. Importe ou crie uma task a partir de uma issue.
6. Crie um contrato antes da implementacao, citando docs especificos com `--required-doc` quando necessario.
7. Inicie uma run e leia o `builder-brief.md` gerado.
8. Implemente apenas essa task, preferencialmente usando a skill `tdd`.
9. Rode sensores revisados e preserve o resultado.
10. Gere brief e handoffs com `evaluate <task_id>`.
11. Spawn um agente avaliador com `fork_context=false`, entregando apenas o `evaluator-agent-handoff.md`.
12. Spawn um agente reviewer Greptile-style com `fork_context=false`, entregando apenas o `greptile-reviewer-agent-handoff.md`. Dispare os dois em paralelo.
13. Consolide os sinais usando `review-consolidation.md`.
14. Registre a decisao consolidada com `evaluate <task_id> --status ...`; isso tambem cria `plain-summary.md` com explicacao simples.
15. Gere `report <task_id>`; o relatorio inclui a explicacao simples.

## Comandos

Inicializar:

```powershell
python <harness.py> --repo $APP_REPO init
```

Ingerir docs:

```powershell
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\context.md" --kind context
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\prd.md" --kind prd
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\architecture.md" --kind architecture
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\adr\ADR-000-indice-e-principios.md" --kind adr
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\refactor\Fase 0 - Correções antes do refactor NestJS + Prisma" --kind refactor-plan
python <harness.py> --repo $APP_REPO preflight
```

Tipos aceitos em `--kind`: `context`, `domain-context`, `prd`, `issue`, `architecture`, `infrastructure`, `security`, `testing`, `refactor-plan`, `decision`, `adr`, `guardrail`, `other`.

Configure documentos globais obrigatorios em `.harness/config.json`:

```json
{
  "required_context": [
    { "path": "AGENTS.md", "kind": "context" },
    { "path": "CONTEXT.md", "kind": "domain-context" },
    { "path": "docs/adr/ADR-000-indice-e-principios.md", "kind": "adr" }
  ],
  "evaluation_policy": {
    "mode": "spawned_agent",
    "fork_context": false,
    "input_scope": "evaluator_agent_handoff"
  },
  "review_policy": {
    "enabled": true,
    "mode": "spawned_agent",
    "fork_context": false,
    "skill": "greptile-review",
    "input_scope": "greptile_reviewer_handoff",
    "blocking_findings": {
      "p0": true,
      "p1_in_changed_surface": true,
      "p2": false
    }
  }
}
```

Importar issues:

```powershell
python <harness.py> --repo $APP_REPO task import "$APP_REPO\issues\001-login.md"
```

Criar uma task manual:

```powershell
python <harness.py> --repo $APP_REPO task create "Titulo curto da task" --body "O que construir"
```

Criar contrato:

```powershell
python <harness.py> --repo $APP_REPO contract TASK-001 `
  --criteria "comportamento observavel" `
  --smoke-sensor "npm test -- login" `
  --affected-sensor "npm run typecheck" `
  --full-sensor "npm test" `
  --full-sensor "npm run build" `
  --reviewed-sensors `
  --required-doc "docs/adr/ADR-000-indice-e-principios.md" `
  --required-doc "docs/adr/ADR-015-testes.md" `
  --out "item fora de escopo"
```

Use `--reviewed-sensors` apenas depois de ler os comandos. Caso contrario, confirme depois com `sensors --reviewed`.

Iniciar implementacao:

```powershell
python <harness.py> --repo $APP_REPO start TASK-001
```

`start` roda `preflight TASK-001` automaticamente. Se um documento obrigatorio mudou desde o ultimo `ingest`, reingira o arquivo antes de iniciar. Use `--skip-preflight` apenas para excecao consciente.

Use `preflight --json` quando a saida for consumida por automacao; nesse modo o comando emite somente JSON.

Se `policy.warn_on_unevaluated_runs=true`, `status` e `start` avisam sobre runs sem avaliacao registrada em `evaluation.json` ou `.harness/evaluations/<task>.md`. Trate o aviso como divida de evidencia: gere ou registre a avaliacao antes de considerar a rodada concluida.

Rodar sensores:

```powershell
python <harness.py> --repo $APP_REPO sensors TASK-001 --tier quick --reviewed
python <harness.py> --repo $APP_REPO sensors TASK-001 --tier full --reviewed
```

Use `quick-pass TASK-001 --reviewed` para rodar a camada rapida e gerar handoffs. Use `full-pass TASK-001 --reviewed` para a rodada final. `evaluate` cria `parallel-dispatch.md`; use esse arquivo para disparar avaliador e reviewer em paralelo.

Sensores rodam sem shell por padrao. Use `--allow-shell` apenas quando um comando revisado depender de comportamento de shell.

No Windows, o runner resolve executaveis do `PATH` antes de chamar `subprocess` sem shell. Assim `npx`, `npm` e `pnpm` podem apontar para wrappers `.CMD` sem exigir `--allow-shell`.

Se uma run ja tiver avaliacao `pass` registrada e os sensores passarem novamente, o status da task permanece `passed`. Se algum sensor falhar, a task volta para `sensors_failed`.

Criar brief e handoffs do avaliador e reviewer:

```powershell
python <harness.py> --repo $APP_REPO evaluate TASK-001
```

Isso cria `evaluator-brief.md`, `evaluator-agent-handoff.md`,
`greptile-reviewer-agent-handoff.md`, `review-consolidation.md` e `parallel-dispatch.md` na ultima run.
Use cada handoff como unica entrada para seu respectivo agente spawnado sem contexto da sessao atual:

```text
spawn_agent:
- agent_type: default
- fork_context: false
- mensagem: conteudo ou caminho do evaluator-agent-handoff.md

spawn_agent:
- agent_type: default
- fork_context: false
- mensagem: conteudo ou caminho do greptile-reviewer-agent-handoff.md
```

Se `spawn_agent` nao estiver disponivel no ambiente, use uma nova sessao manual com somente
o conteudo do handoff correspondente. Nao repasse historico ou decisoes informais do implementador.

Consolidacao:

- O avaliador contratual decide se a task cumpre contrato, sensores e evidencia.
- O reviewer Greptile-style decide se o diff introduz risco tecnico.
- `FAIL` do avaliador bloqueia.
- `P0` do reviewer bloqueia.
- `P1` dentro da superficie alterada normalmente bloqueia.
- `P2` nao bloqueia por padrao; vira ajuste opcional ou follow-up.

Se houver P0/P1 bloqueante, gere fix brief na mesma task:

```powershell
python <harness.py> --repo $APP_REPO fix-brief TASK-001 --review-file reviewer-output.md
```

Depois corrija o menor trecho necessario, rode `sensors --tier quick`, gere handoffs de novo e so finalize depois de `sensors --tier full`.

Registrar decisao consolidada:

```powershell
python <harness.py> --repo $APP_REPO evaluate TASK-001 --status pass --notes "Evidencia aceita."
python <harness.py> --repo $APP_REPO evaluate TASK-001 --status fail --gap "Falta teste de persistencia."
```

Gerar relatorio:

```powershell
python <harness.py> --repo $APP_REPO report TASK-001
```

O fechamento cria ou atualiza `.harness\runs\<task>\<run>\plain-summary.md`, com linguagem simples sobre o que foi feito, por que foi feito, como foi conferido, resultado e pendencias. Use esse arquivo quando precisar prestar contas sem termos tecnicos.

## Telegram

Configure o token fora do repo:

```powershell
$env:HARNESS_TELEGRAM_BOT_TOKEN = "<telegram-bot-token>"
```

Habilite notificacoes e chats autorizados:

```powershell
python <harness.py> --repo $APP_REPO telegram configure `
  --enable `
  --chat-id "123456789" `
  --allowed-chat-id "123456789"
```

Comandos uteis:

```powershell
python <harness.py> --repo $APP_REPO telegram status
python <harness.py> --repo $APP_REPO telegram send "Harness conectado."
python <harness.py> --repo $APP_REPO telegram listen
python <harness.py> --repo $APP_REPO telegram codex --resume-last
python <harness.py> --repo $APP_REPO telegram mirror
python <harness.py> --repo $APP_REPO telegram bridge --include-tools
```

Use `telegram codex --resume-last` quando quiser um fluxo estilo OpenClaw/Hermes: mensagens normais do Telegram sao enviadas ao `codex exec resume --last`, e a resposta final volta para o Telegram. Sem `--resume-last`, cada mensagem abre uma execucao nova com `codex exec -C $APP_REPO`.

Use `telegram mirror` quando uma sessao Codex CLI ja estiver trabalhando e voce so quiser acompanhar updates pelo Telegram sem interromper o turno ativo. Ele le a transcricao mais recente em `~/.codex/sessions` e manda novas mensagens para o Telegram. Passe `--include-tools` para incluir chamadas/saidas de ferramentas.

Use `telegram bridge --include-tools` para acompanhar a sessao ativa e receber mensagens no mesmo processo. Por padrao, mensagens comuns ficam em `.harness/telegram/operator-messages.md` sem interromper o agente. Use `/codex <mensagem>` no Telegram quando quiser chamar `codex exec resume --last` em paralelo.

No Telegram, use:

```text
/help
/status
/tasks
/pick
/report TASK-001
/new descreva a nova tarefa
/codex mande esta mensagem direto para o Codex
```

Mensagens normais, imagens e audios entram em `.harness/inbox/telegram/`. Midias sao salvas em `.harness/inbox/telegram/media/`. Para transcrever audio e descrever imagem automaticamente, configure tambem `$env:OPENAI_API_KEY` e rode:

```powershell
python <harness.py> --repo $APP_REPO telegram configure --openai-media
```

## Regras operacionais

- Trabalhe em uma task por vez (uma issue por run; nao misture escopos).
- ADRs e docs obrigatorios ficam no repo alvo como fonte da verdade; o Harness so guarda manifest, hashes e copias locais.
- Nao inicie run se `preflight` falhar por contexto ausente ou desatualizado (aplicado por `policy.context_preflight_required_before_start`).
- Trate `.harness/contracts/<task>.json` como vinculante.
- Nao expanda escopo a partir de comentarios do avaliador.
- Nao marque task como concluida sem evidencia de sensores; o runner bloqueia `evaluate --status pass` sem `sensors.json` passando (aplicado por `policy.record_evidence_before_done`).
- Prefira sensores deterministicos antes de revisao semantica.
- O implementador pode se auto-checar, mas nao deve se autoaprovar — use sempre um agente avaliador separado.
- O avaliador deve ser um agente separado com `fork_context=false` sempre que a ferramenta estiver disponivel.
- O reviewer Greptile-style deve ser um segundo agente separado; ele revisa risco do diff, nao substitui o avaliador contratual.
- Use `review-consolidation.md`: `FAIL` do avaliador, `P0` do reviewer e `P1` dentro da superficie alterada bloqueiam; `P2` nao bloqueia por padrao.
- Se sensores falharem, crie o menor fix brief possivel e rode novamente.
- Guarde progresso em `.harness`, nao so na memoria do chat.
- Versione no maximo `.harness/config.json`, `.harness/progress.md`, `.harness/tasks/**`, `.harness/contracts/**` e `.harness/reports/**`.
- Mantenha `.harness/runs/**`, `.harness/context/**`, avaliacoes, logs, screenshots e outputs grandes locais.

## Prompt de handoff

Quando pedirem para implementar a proxima issue, use este formato:

```text
Vou rodar o Harness para uma issue:
1. escolher/importar a task
2. criar ou verificar o contrato
3. iniciar uma run
4. implementar com TDD
5. rodar sensores revisados
6. criar brief/handoffs do avaliador e do reviewer Greptile-style
7. spawnar avaliador sem contexto da sessao atual
8. spawnar reviewer Greptile-style sem contexto da sessao atual
9. consolidar sinais e registrar avaliacao/relatorio
```
