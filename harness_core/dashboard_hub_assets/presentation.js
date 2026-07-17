(() => {
"use strict";

const STATUS_META = Object.freeze({
  andamento: { label: "Em andamento", tone: "mint" },
  conferencia: { label: "Em conferência", tone: "blue" },
  revisao: { label: "Em revisão", tone: "amber" },
  atencao: { label: "Precisa de atenção", tone: "coral" },
  concluido: { label: "Concluído", tone: "green" },
  indisponivel: { label: "Indisponível", tone: "neutral" },
});

const STAGE_LABELS = Object.freeze([
  "Preparando",
  "Construindo",
  "Conferindo",
  "Revisando",
  "Concluído",
]);

const mockAnchor = Date.now();
const ago = (seconds) => new Date(mockAnchor - seconds * 1000).toISOString();
const task = (number, state, title, description, result = "") => ({
  id: `mock-${number}`,
  number,
  state,
  title,
  description,
  result,
  updated_at: ago((12 - number) * 180 + 120),
});

const mockState = {
  generated_at: new Date(mockAnchor).toISOString(),
  source: "demonstracao",
  projects: [
    {
      id: "loja",
      name: "Loja virtual",
      status: "andamento",
      implementation: "Novo processo de pagamento",
      summary: "Um jeito mais simples e seguro de pagar, agora com suporte a cupons de desconto.",
      situation: "Construindo a interface",
      stage: 1,
      updated_at: ago(12),
      current: {
        number: 3,
        total: 10,
        title: "Adicionar cupom de desconto",
        what_doing: "Está sendo adicionada uma área na tela de pagamento para o cliente informar um cupom de desconto.",
        why: "Isso permitirá que clientes utilizem descontos antes de finalizar a compra.",
        when_done: "O cliente poderá informar um cupom e visualizar o novo valor do pedido.",
        last_update: "A área do cupom já foi criada. Agora ela está sendo ajustada para funcionar bem no celular.",
        remaining: "Falta conferir cupons inválidos e revisar as mensagens apresentadas ao cliente.",
      },
      tasks: [
        task(1, "done", "Organizar as informações do pedido", "As informações do pedido serão reunidas em um só lugar.", "O sistema passou a reunir produtos, valores e endereço em uma única área."),
        task(2, "done", "Mostrar as formas de pagamento", "O cliente escolhe como deseja pagar.", "O cliente agora consegue visualizar e escolher entre as formas de pagamento disponíveis."),
        task(3, "doing", "Adicionar cupom de desconto", "Está sendo criada uma área para informar e aplicar um cupom."),
        task(4, "waiting", "Conferir a validade do cupom", "O sistema verificará se o cupom pode ser utilizado."),
        task(5, "waiting", "Atualizar o valor da compra", "O desconto será aplicado ao total apresentado ao cliente."),
        task(6, "waiting", "Mostrar mensagens claras", "O cliente saberá quando um cupom não puder ser usado."),
        task(7, "waiting", "Confirmar o pagamento", "Tudo será reunido para concluir a compra com segurança."),
        task(8, "waiting", "Enviar o comprovante", "O cliente receberá a confirmação da compra."),
        task(9, "waiting", "Registrar o pedido", "O pedido ficará guardado para acompanhamento."),
        task(10, "waiting", "Revisar toda a experiência", "Uma conferência final garantirá que tudo funcione bem."),
      ],
      last_completed: {
        title: "Mostrar as formas de pagamento",
        result: "O cliente agora consegue visualizar e escolher entre as formas de pagamento disponíveis.",
        completed_at: ago(620),
      },
      recent_updates: [
        { at: ago(12), text: "A área do cupom foi criada." },
        { at: ago(250), text: "A construção da nova tela começou." },
        { at: ago(430), text: "O trabalho da task foi preparado." },
        { at: ago(620), text: "A task anterior foi concluída." },
      ],
    },
    {
      id: "financeiro",
      name: "Sistema financeiro",
      status: "conferencia",
      implementation: "Exportação de relatórios em PDF",
      summary: "Permitir baixar os relatórios em PDF, prontos para guardar ou imprimir.",
      situation: "Conferindo o resultado",
      stage: 2,
      updated_at: ago(46),
      current: {
        number: 6,
        total: 8,
        title: "Conferir o conteúdo gerado",
        what_doing: "O conteúdo do relatório está sendo conferido e os valores estão sendo comparados com os dados do sistema.",
        why: "Assim temos certeza de que os relatórios mostram números corretos.",
        when_done: "O relatório poderá ser gerado com a garantia de que os valores estão certos.",
        last_update: "Os totais já foram conferidos. Agora estão sendo verificados os detalhes de cada seção.",
        remaining: "Falta conferir as últimas seções e comparar dois relatórios de exemplo.",
      },
      tasks: [
        task(1, "done", "Reunir os dados do relatório", "As informações passam a ser agrupadas automaticamente.", "As informações do relatório passaram a ser reunidas automaticamente."),
        task(2, "done", "Definir o modelo do relatório", "O relatório ganha um formato organizado.", "O relatório ganhou um formato organizado e fácil de ler."),
        task(3, "done", "Gerar o arquivo em PDF", "O sistema cria o arquivo para baixar.", "O sistema passou a criar o arquivo em PDF pronto para baixar."),
        task(4, "done", "Incluir os totais e resumos", "Os valores principais aparecem destacados.", "Os valores principais passaram a aparecer destacados no início do relatório."),
        task(5, "done", "Adicionar cabeçalho e data", "Cada relatório mostra quando foi gerado.", "Todo relatório passou a mostrar um cabeçalho com a data em que foi gerado."),
        task(6, "doing", "Conferir o conteúdo gerado", "O conteúdo está sendo conferido para garantir que está correto."),
        task(7, "waiting", "Ajustar a aparência para impressão", "O relatório ficará bem organizado quando impresso."),
        task(8, "waiting", "Liberar a exportação", "O recurso ficará disponível para todas as pessoas."),
      ],
      last_completed: {
        title: "Adicionar cabeçalho e data",
        result: "Todo relatório passou a mostrar um cabeçalho com a data em que foi gerado.",
        completed_at: ago(760),
      },
      recent_updates: [
        { at: ago(46), text: "A conferência do conteúdo começou." },
        { at: ago(320), text: "O arquivo em PDF foi gerado." },
        { at: ago(760), text: "O cabeçalho e a data foram adicionados." },
        { at: ago(980), text: "Os totais foram incluídos." },
      ],
    },
    {
      id: "clientes",
      name: "Sistema de clientes",
      status: "revisao",
      implementation: "Organização dos novos contatos",
      summary: "Deixar os contatos dos clientes mais organizados e fáceis de encontrar.",
      situation: "Revisando o resultado",
      stage: 3,
      updated_at: ago(88),
      current: {
        number: 4,
        total: 7,
        title: "Revisar a nova organização",
        what_doing: "A nova forma de organizar os contatos está sendo revisada antes de valer para todos.",
        why: "Isso evita que algum contato importante fique fora do lugar.",
        when_done: "Os contatos ficarão organizados de um jeito mais fácil de encontrar.",
        last_update: "As categorias já foram revisadas. Agora estão sendo conferidos os contatos sem categoria.",
        remaining: "Falta revisar os contatos que não se encaixaram em nenhuma categoria.",
      },
      tasks: [
        task(1, "done", "Reunir os contatos existentes", "Todos os contatos são reunidos em uma lista.", "Todos os contatos foram reunidos em uma lista única."),
        task(2, "done", "Agrupar contatos repetidos", "Contatos repetidos são identificados.", "Os contatos repetidos foram identificados e agrupados."),
        task(3, "done", "Separar por tipo de cliente", "Os contatos são organizados por categoria.", "Os contatos passaram a ficar agrupados por categoria, facilitando a busca."),
        task(4, "doing", "Revisar a nova organização", "A nova organização está passando por uma revisão final."),
        task(5, "waiting", "Confirmar as informações principais", "Nome, telefone e e-mail serão conferidos."),
        task(6, "waiting", "Aplicar a organização para todos", "A nova estrutura passará a valer para toda a base."),
        task(7, "waiting", "Avisar a equipe sobre as mudanças", "A equipe saberá como os contatos ficaram organizados."),
      ],
      last_completed: {
        title: "Separar por tipo de cliente",
        result: "Os contatos passaram a ficar agrupados por categoria, facilitando a busca.",
        completed_at: ago(920),
      },
      recent_updates: [
        { at: ago(88), text: "A revisão da organização começou." },
        { at: ago(520), text: "Os contatos repetidos foram agrupados." },
        { at: ago(920), text: "As categorias foram criadas." },
        { at: ago(1110), text: "Os contatos foram reunidos." },
      ],
    },
    {
      id: "portal",
      name: "Portal interno",
      status: "atencao",
      implementation: "Controle de acesso das equipes",
      summary: "Garantir que cada equipe acesse apenas as informações adequadas à sua função.",
      situation: "Precisa de atenção",
      stage: 1,
      updated_at: ago(58),
      blocker: {
        title: "Precisa de atenção",
        message: "Foi encontrado um problema ao diferenciar os acessos de gestores e colaboradores. O trabalho de correção está em andamento.",
      },
      current: {
        number: 2,
        total: 6,
        title: "Separar gestores e colaboradores",
        what_doing: "Está sendo definido o que gestores e colaboradores podem acessar no portal.",
        why: "Cada pessoa deve ver apenas as informações relacionadas à sua função.",
        when_done: "Gestores e colaboradores terão acessos separados e adequados.",
        last_update: "Foi encontrado um problema com perfis que têm as duas funções. O trabalho de correção está em andamento.",
        remaining: "Falta resolver os perfis com funções duplicadas e conferir os acessos.",
      },
      tasks: [
        task(1, "done", "Listar as equipes existentes", "As equipes são identificadas e listadas.", "Todas as equipes foram identificadas e reunidas em uma lista."),
        task(2, "doing", "Separar gestores e colaboradores", "Está sendo definido o que cada perfil pode acessar."),
        task(3, "waiting", "Definir o que cada perfil acessa", "Cada função terá os acessos corretos."),
        task(4, "waiting", "Aplicar as regras de acesso", "As regras passarão a valer no sistema."),
        task(5, "waiting", "Conferir os acessos", "Será conferido se cada pessoa vê apenas o que deve."),
        task(6, "waiting", "Liberar para as equipes", "O novo controle de acesso ficará disponível."),
      ],
      last_completed: {
        title: "Listar as equipes existentes",
        result: "Todas as equipes foram identificadas e reunidas em uma lista.",
        completed_at: ago(1340),
      },
      recent_updates: [
        { at: ago(58), text: "Um problema foi encontrado ao separar os acessos." },
        { at: ago(440), text: "A separação dos perfis começou." },
        { at: ago(900), text: "As equipes foram listadas." },
        { at: ago(1340), text: "O trabalho da task foi preparado." },
      ],
    },
    {
      id: "site",
      name: "Site institucional",
      status: "concluido",
      implementation: "Nova página de apresentação",
      summary: "Uma nova página para apresentar a empresa, concluída e pronta para publicação.",
      situation: "Concluído e conferido",
      stage: 4,
      updated_at: ago(132),
      current: {
        number: 5,
        total: 5,
        title: "Revisar e finalizar",
        what_doing: "A nova página de apresentação foi finalizada, com todos os textos e imagens no lugar.",
        why: "A empresa será apresentada de forma clara e atualizada.",
        when_done: "A página está pronta para ser publicada quando a equipe desejar.",
        last_update: "A revisão final foi concluída e nenhum ajuste ficou pendente.",
        remaining: "Nada pendente. Todas as tasks foram concluídas e conferidas.",
      },
      tasks: [
        task(1, "done", "Definir o conteúdo da página", "O texto e as seções são definidos.", "O texto e as seções da página foram definidos."),
        task(2, "done", "Montar a estrutura da página", "As seções são organizadas na ordem certa.", "As seções foram organizadas na ordem certa."),
        task(3, "done", "Adicionar textos e imagens", "A página recebe os conteúdos finais.", "A página recebeu todos os textos e imagens finais."),
        task(4, "done", "Conferir em celular e computador", "A página é conferida nos dois formatos.", "A página funciona bem no celular e no computador."),
        task(5, "done", "Revisar e finalizar", "Tudo é revisado antes da conclusão.", "A página foi revisada por completo e aprovada para publicação."),
      ],
      last_completed: {
        title: "Revisar e finalizar",
        result: "A página foi revisada por completo e aprovada para publicação.",
        completed_at: ago(132),
      },
      recent_updates: [
        { at: ago(132), text: "A página foi finalizada." },
        { at: ago(620), text: "A revisão final começou." },
        { at: ago(1240), text: "A página foi conferida no celular." },
        { at: ago(1780), text: "Os textos e imagens foram adicionados." },
      ],
    },
    {
      id: "entregas",
      name: "Aplicativo de entregas",
      status: "andamento",
      implementation: "Novo cálculo de frete",
      summary: "Calcular o frete de forma automática, considerando a distância e o peso do pedido.",
      situation: "Construindo o cálculo",
      stage: 1,
      updated_at: ago(368),
      stale_after_seconds: 180,
      stale_message: "Este projeto não envia uma atualização há alguns minutos. O trabalho pode continuar em andamento.",
      current: {
        number: 3,
        total: 9,
        title: "Calcular o frete por distância",
        what_doing: "Está sendo criado o cálculo do valor do frete de acordo com a distância da entrega.",
        why: "O cliente deve ver um valor de frete justo para o seu endereço.",
        when_done: "O frete será calculado automaticamente pela distância.",
        last_update: "O cálculo por distância começou a ser montado.",
        remaining: "Falta terminar o cálculo por distância e considerar o peso do pedido.",
      },
      tasks: [
        task(1, "done", "Reunir as regras de entrega", "As regras de frete atuais são reunidas.", "As regras de frete atuais foram reunidas."),
        task(2, "done", "Cadastrar as regiões atendidas", "As regiões de entrega são organizadas.", "As regiões de entrega foram organizadas e ficaram prontas para uso."),
        task(3, "doing", "Calcular o frete por distância", "Está sendo criado o cálculo do frete conforme a distância."),
        task(4, "waiting", "Considerar o peso do pedido", "O peso passará a influenciar o valor do frete."),
        task(5, "waiting", "Aplicar frete grátis acima de um valor", "Alguns pedidos terão frete grátis."),
        task(6, "waiting", "Mostrar o prazo de entrega", "O cliente verá quando o pedido deve chegar."),
        task(7, "waiting", "Exibir o frete no carrinho", "O valor aparecerá antes da finalização."),
        task(8, "waiting", "Conferir os cálculos", "Os valores serão conferidos em vários exemplos."),
        task(9, "waiting", "Liberar o novo cálculo", "O novo frete passará a valer na loja."),
      ],
      last_completed: {
        title: "Cadastrar as regiões atendidas",
        result: "As regiões de entrega foram organizadas e ficaram prontas para uso.",
        completed_at: ago(1020),
      },
      recent_updates: [
        { at: ago(368), text: "O cálculo por distância começou." },
        { at: ago(820), text: "As regiões atendidas foram cadastradas." },
        { at: ago(1020), text: "As regras de frete foram reunidas." },
      ],
    },
    {
      id: "indicadores",
      name: "Painel de indicadores",
      status: "indisponivel",
      implementation: "Atualização dos gráficos",
      summary: "",
      situation: "Indisponível",
      stage: 0,
      updated_at: "",
      current: null,
      tasks: [],
      recent_updates: [],
      unavailable_message: "Não foi possível receber informações deste projeto no momento. Tente novamente em alguns instantes.",
    },
  ],
};

function asDate(value) {
  const date = new Date(String(value || ""));
  return Number.isFinite(date.getTime()) ? date : null;
}

function statusFromRepo(repo, tasks) {
  if (repo.error || repo.phase === "offline") return "indisponivel";
  const statuses = new Set(tasks.map((item) => String(item.status || item.state || "")));
  if (Number(repo.counts?.security_findings || 0) > 0 || ["failed", "needs_work", "sensors_failed"].some((item) => statuses.has(item))) return "atencao";
  if (statuses.has("sensors_passed") || repo.phase === "review") return "revisao";
  if (tasks.length && tasks.every((item) => ["done", "passed"].includes(String(item.status || item.state || "")))) return "concluido";
  return "andamento";
}

function taskStateFromRaw(status, isCurrent) {
  const value = String(status || "").toLowerCase();
  if (["done", "passed"].includes(value)) return "done";
  if (isCurrent || ["in_progress", "needs_work", "sensors_failed", "sensors_passed"].includes(value)) return "doing";
  return "waiting";
}

function deriveRepoPresentation(repo) {
  const rawTasks = Array.isArray(repo.tasks) ? repo.tasks : [];
  const active = repo.active_task || rawTasks.find((item) => ["in_progress", "needs_work", "sensors_failed", "sensors_passed"].includes(String(item.status || ""))) || rawTasks[0] || null;
  const activeId = String(active?.task_id || active?.id || "");
  const tasks = rawTasks.map((item, index) => ({
    id: String(item.task_id || item.id || index + 1),
    number: index + 1,
    title: String(item.title || `Task ${index + 1}`),
    description: String(item.description || item.body || `Esta etapa prepara ${String(item.title || "o próximo resultado").toLowerCase()}.`),
    state: taskStateFromRaw(item.status, String(item.task_id || item.id || "") === activeId),
    result: String(item.result || ""),
    updated_at: String(item.updated_at || item.created_at || ""),
  }));
  const currentTask = tasks.find((item) => item.id === activeId) || tasks.find((item) => item.state === "doing") || tasks[0] || null;
  const status = statusFromRepo(repo, rawTasks);
  const stage = status === "concluido" ? 4 : status === "revisao" ? 3 : status === "conferencia" ? 2 : 1;
  const title = String(active?.title || currentTask?.title || "Primeira task ainda não planejada");
  return {
    status,
    status_label: STATUS_META[status].label,
    implementation: String(active?.implementation || active?.title || "Implementação em acompanhamento"),
    summary: String(active?.goal || `Acompanhar o trabalho atual de ${String(repo.project || repo.name || "este projeto")}.`),
    situation: STAGE_LABELS[stage],
    updated_at: String(active?.updated_at || repo.generated_at || ""),
    stage,
    tasks,
    current: currentTask ? {
      id: currentTask.id,
      number: currentTask.number,
      total: tasks.length,
      title,
      what_doing: currentTask.description,
      why: String(active?.goal || `Isso está sendo feito para concluir ${title.toLowerCase()}.`),
      when_done: String(active?.outcome || `O resultado de ${title.toLowerCase()} ficará pronto para conferência.`),
      last_update: "O acompanhamento recebeu uma atualização recente deste projeto.",
      remaining: "Falta concluir esta task e conferir o resultado.",
    } : null,
    last_completed: null,
    recent_updates: [],
    unavailable_message: repo.error ? "Não foi possível receber informações deste projeto no momento." : "",
  };
}

function normalizeTask(item, index) {
  return {
    id: String(item?.id || item?.task_id || index + 1),
    number: Number(item?.number || index + 1),
    title: String(item?.title || `Task ${index + 1}`),
    description: String(item?.description || item?.explanation || "Esta etapa ainda não foi iniciada."),
    state: ["done", "doing", "waiting"].includes(item?.state) ? item.state : taskStateFromRaw(item?.status, false),
    result: String(item?.result || ""),
    updatedAt: String(item?.updated_at || item?.updatedAt || ""),
  };
}

function safeProjectId(repo, source, index) {
  const explicit = String(source.id || repo.id || "").trim();
  if (explicit && /^[a-zA-Z0-9_-]+$/.test(explicit)) return explicit;
  const name = String(repo.name || repo.project || source.name || `projeto-${index + 1}`);
  const slug = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "projeto";
  return `${slug}-${index + 1}`;
}

function normalizeProject(repo, index, now) {
  const source = repo.presentation && typeof repo.presentation === "object"
    ? repo.presentation
    : repo.status && repo.implementation
      ? repo
      : deriveRepoPresentation(repo);
  const status = STATUS_META[source.status] ? source.status : "andamento";
  const tasks = (Array.isArray(source.tasks) ? source.tasks : []).map(normalizeTask);
  const current = source.current ? {
    id: String(source.current.id || ""),
    number: Number(source.current.number || tasks.find((item) => item.state === "doing")?.number || tasks.length || 1),
    total: Number(source.current.total || tasks.length),
    title: String(source.current.title || tasks.find((item) => item.state === "doing")?.title || "Task atual"),
    whatDoing: String(source.current.what_doing || source.current.whatDoing || "O trabalho desta task está em andamento."),
    why: String(source.current.why || "Esta task faz parte do resultado planejado."),
    whenDone: String(source.current.when_done || source.current.whenDone || "O resultado ficará pronto para conferência."),
    lastUpdate: String(source.current.last_update || source.current.lastUpdate || "Aguardando uma nova atualização."),
    remaining: String(source.current.remaining || "Falta concluir e conferir esta task."),
  } : null;
  const updatedAt = String(source.updated_at || source.updatedAt || repo.generated_at || "");
  const updatedDate = asDate(updatedAt);
  const staleAfter = Number(source.stale_after_seconds || source.staleAfterSeconds || 0);
  const stale = Boolean(source.stale) || Boolean(
    staleAfter > 0
    && updatedDate
    && now - updatedDate.getTime() > staleAfter * 1000
    && !["concluido", "indisponivel"].includes(status)
  );
  const completedCount = tasks.filter((item) => item.state === "done").length;
  const doingCount = tasks.filter((item) => item.state === "doing").length;
  const waitingCount = tasks.filter((item) => item.state === "waiting").length;
  return {
    id: safeProjectId(repo, source, index),
    name: String(repo.name || repo.project || source.name || `Projeto ${index + 1}`),
    status,
    statusLabel: String(source.status_label || source.statusLabel || STATUS_META[status].label),
    implementation: String(source.implementation || "Implementação em acompanhamento"),
    summary: String(source.summary || ""),
    situation: String(source.situation || STAGE_LABELS[Math.max(0, Math.min(4, Number(source.stage || 0)))]),
    stage: Math.max(0, Math.min(4, Number(source.stage || 0))),
    updatedAt,
    current,
    tasks,
    counts: { completed: completedCount, doing: doingCount, waiting: waitingCount },
    lastCompleted: source.last_completed ? {
      title: String(source.last_completed.title || "Task concluída"),
      result: String(source.last_completed.result || "A task foi concluída e conferida."),
      completedAt: String(source.last_completed.completed_at || source.last_completed.completedAt || ""),
    } : null,
    recentUpdates: (Array.isArray(source.recent_updates) ? source.recent_updates : []).map((item) => ({
      at: String(item.at || item.ts || ""),
      text: String(item.text || item.message || "Uma atualização foi recebida."),
    })),
    blocker: source.blocker ? {
      title: String(source.blocker.title || "Precisa de atenção"),
      message: String(source.blocker.message || "Foi encontrado um ponto que precisa de ajuste."),
    } : null,
    stale,
    staleMessage: String(source.stale_message || source.staleMessage || "Este projeto não envia uma atualização há alguns minutos. O trabalho pode continuar em andamento."),
    unavailableMessage: String(source.unavailable_message || source.unavailableMessage || "Não foi possível receber informações deste projeto no momento."),
  };
}

function buildDashboardState(raw = {}, options = {}) {
  const now = Number(options.now || Date.now());
  const sourceProjects = Array.isArray(raw.projects)
    ? raw.projects
    : Array.isArray(raw.repos)
      ? raw.repos
      : Array.isArray(raw.world?.repos)
        ? raw.world.repos
        : [];
  return {
    generatedAt: String(raw.generated_at || raw.generatedAt || new Date(now).toISOString()),
    source: String(raw.source || "local"),
    actionToken: String(raw.action_token || raw.actionToken || ""),
    projects: sourceProjects.map((project, index) => normalizeProject(project, index, now)),
  };
}

function taskPosition(project) {
  if (!project?.current || project.current.total < 1) return "Aguardando primeira task";
  return `Task ${project.current.number} de ${project.current.total}`;
}

function countsLine(project) {
  const completed = project?.counts?.completed || 0;
  const doing = project?.counts?.doing || 0;
  const waiting = project?.counts?.waiting || 0;
  return `${completed} ${completed === 1 ? "concluída" : "concluídas"} · ${doing} em andamento · ${waiting} aguardando`;
}

const HarnessPresentation = Object.freeze({
  STATUS_META,
  STAGE_LABELS,
  buildDashboardState,
  countsLine,
  mockState,
  taskPosition,
});

if (typeof window !== "undefined") window.HarnessPresentation = HarnessPresentation;
if (typeof module !== "undefined" && module.exports) module.exports = HarnessPresentation;
})();
