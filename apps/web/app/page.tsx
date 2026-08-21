"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

type View =
  | "overview"
  | "decisions"
  | "jobs"
  | "applications"
  | "profile"
  | "answers"
  | "rules"
  | "platforms"
  | "inbox"
  | "notifications"
  | "interventions"
  | "analytics"
  | "automation"
  | "settings"
  | "logs"
  | "security";
type ApprovedAnswer = {
  id: string;
  question: string;
  category: string;
  approved_answer: string;
  language: string;
  verified: boolean;
  usage_count: number;
};
type LogEntry = { at: string; message: string };
type AgentStatus = {
  status: string;
  platform?: string;
  role?: string;
  found: number;
  blocked: number;
  message: string;
};
type Job = {
  source: string;
  title: string;
  url: string;
  search_role: string;
  status: string;
  score?: number;
  decision?: string;
};
type Application = {
  id: string;
  title: string;
  source: string;
  score: number;
  status: string;
  reason: string;
  job_url: string;
  created_at?: string;
  submitted_at?: string | null;
  attempts?: number;
  ai_answers?: Array<{ name: string; answer: string; evidence: string }>;
  region?: string;
  salary_brl?: number | null;
  recommendation?: string;
  feedback?: string;
};
type CareerMail = {
  message_id: string;
  subject: string;
  sender: string;
  received_at: string;
  category: string;
  confidence: number;
  reason: string;
  snippet: string;
  status: string;
  suggested_reply?: string;
  draft_id?: string | null;
  calendar_event_id?: string | null;
  event_candidate?: {
    title: string;
    start: string;
    end: string;
    timezone: string;
  } | null;
  questionnaire_url?: string | null;
  questionnaire_status?: string | null;
};
type GoogleStatus = {
  connected: boolean;
  email?: string | null;
  calendar: boolean;
  alerts: number;
  last_items: CareerMail[];
};
type Profile = {
  full_name: string;
  email: string;
  phone: string;
  city: string;
  state: string;
  linkedin_url: string;
  salary_expectation: string;
  work_models: string[];
  target_roles: string[];
  skills: string[];
  approved_answers: Record<string, string>;
  resume_path: string;
};
type CareerRule = {
  id: string;
  code: string;
  label: string;
  rule_type: string;
  configuration: Record<string, unknown>;
  priority: number;
  enabled: boolean;
};
type Decision = {
  id: string;
  recommendation: string;
  status: string;
  summary: Record<string, unknown>;
  title: string;
  company?: string;
  location?: string;
  work_model?: string;
  source_url: string;
  fit?: number;
};
type PortalDashboard = {
  workspace: {
    name: string;
    jobs: number;
    applications: number;
    pending_decisions: number;
  };
  rules: CareerRule[];
  decisions: Decision[];
  generatedAt: string;
};
type CareerNotification = { id: string; kind: string; title: string; body: string; priority: string; read_at?: string | null; created_at: string };
type HumanIntervention = { id: string; reason: string; status: string; title: string; instructions: string; page_url?: string | null; evidence: Record<string, unknown>; created_at: string };
type CareerAnalytics = { sample: { applications: number; submitted: number; communications: number }; funnel: Array<{ status: string; total: number }>; sources: Array<{ source: string; jobs: number; applications: number; progressed: number }>; interventions: { total: number; pending: number; resolved: number }; rates: { submission_percent: number | null; response_percent: number | null }; warnings: string[]; recommendations_enabled: boolean; generated_at: string };
const AGENT_URL = "/agent";

const nav: Array<[View, string]> = [
  ["overview", "Radar TI"],
  ["decisions", "Decisões"],
  ["jobs", "Oportunidades"],
  ["applications", "Pipeline"],
  ["profile", "Perfil e Currículos"],
  ["answers", "Respostas aprovadas"],
  ["rules", "Regras de carreira"],
  ["platforms", "Fontes"],
  ["inbox", "Gmail e Agenda"],
  ["notifications", "Notificações"],
  ["interventions", "Intervenções"],
  ["analytics", "Resultados"],
  ["automation", "Automação"],
  ["settings", "Preferências"],
  ["logs", "Auditoria"],
  ["security", "Segurança"],
];

const platforms = [
  {
    name: "InfoJobs",
    priority: "Prioridade 1",
    home: "https://www.infojobs.com.br/",
    search: (q: string) =>
      `https://www.infojobs.com.br/vagas-de-emprego-${encodeURIComponent(q.toLowerCase().replaceAll(" ", "-"))}.aspx`,
  },
  {
    name: "Indeed",
    priority: "Prioridade 2",
    home: "https://br.indeed.com/",
    search: (q: string) =>
      `https://br.indeed.com/jobs?q=${encodeURIComponent(q)}&l=Brasil`,
  },
  {
    name: "Catho",
    priority: "Prioridade 3",
    home: "https://www.catho.com.br/vagas/",
    search: (q: string) =>
      `https://www.catho.com.br/vagas/?q=${encodeURIComponent(q)}`,
  },
  {
    name: "LinkedIn",
    priority: "Prioridade 4",
    home: "https://www.linkedin.com/jobs/",
    search: (q: string) =>
      `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(q)}&location=Brasil`,
  },
];

const defaultRoles =
  "Analista de Sustentação\nAnalista de Suporte N3\nAnalista de Sistemas\nDBA SQL Server\nEngenheiro de Dados";

export default function Home() {
  const [view, setView] = useState<View>("overview");
  const [roles, setRoles] = useState(defaultRoles);
  const [location, setLocation] = useState("Remoto Brasil; Campinas e região");
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [saved, setSaved] = useState(false);
  const [agent, setAgent] = useState<AgentStatus>({
    status: "offline",
    found: 0,
    blocked: 0,
    message: "Conectando ao agente local...",
  });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [profile, setProfile] = useState<Profile>({
    full_name: "",
    email: "",
    phone: "",
    city: "Campinas",
    state: "SP",
    linkedin_url: "",
    salary_expectation: "",
    work_models: ["REMOTE", "HYBRID"],
    target_roles: [],
    skills: [],
    approved_answers: {},
    resume_path: "",
  });
  const [skillsText, setSkillsText] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [resumeFamily, setResumeFamily] = useState("GENERAL");
  const [answers, setAnswers] = useState<ApprovedAnswer[]>([]);
  const [answerDraft, setAnswerDraft] = useState({
    question: "",
    category: "GENERAL",
    approved_answer: "",
    language: "pt-BR",
    verified: true,
  });
  const [answerMessage, setAnswerMessage] = useState("");
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>({
    connected: false,
    calendar: false,
    alerts: 0,
    last_items: [],
  });
  const [dashboard, setDashboard] = useState<PortalDashboard | null>(null);
  const [notifications, setNotifications] = useState<CareerNotification[]>([]);
  const [interventions, setInterventions] = useState<HumanIntervention[]>([]);
  const [analytics, setAnalytics] = useState<CareerAnalytics | null>(null);
  const [dashboardMessage, setDashboardMessage] = useState(
    "Sincronizando dados da VPS…",
  );
  const appliedCount = applications.filter(
    (application) => application.status === "APPLIED",
  ).length;
  const pendingCount = applications.filter((application) =>
    ["INSPECTING", "READY_TO_PREPARE", "READY_FOR_REVIEW"].includes(
      application.status,
    ),
  ).length;

  useEffect(() => {
    const storedRoles = localStorage.getItem("careeros.roles");
    const storedLocation = localStorage.getItem("careeros.location");
    const storedLogs = localStorage.getItem("careeros.logs");
    if (storedRoles) setRoles(storedRoles);
    if (storedLocation) setLocation(storedLocation);
    if (storedLogs) setLogs(JSON.parse(storedLogs) as LogEntry[]);
    void fetch("/api/portal/profile")
      .then(async (response) => {
        if (response.ok) {
          const nextProfile = (await response.json()) as Profile;
          setProfile(nextProfile);
          setSkillsText(nextProfile.skills.join(", "));
        }
      })
      .catch(() => undefined);
    void fetch("/api/portal/answers")
      .then(async (response) => {
        if (response.ok)
          setAnswers((await response.json()) as ApprovedAnswer[]);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    async function refreshDashboard() {
      const response = await fetch("/api/portal/dashboard", {
        cache: "no-store",
      }).catch(() => null);
      if (!response?.ok) {
        setDashboardMessage(
          "Central disponível, mas os dados ainda não sincronizaram.",
        );
        return;
      }
      setDashboard((await response.json()) as PortalDashboard);
      const notificationResponse = await fetch(
        "/api/portal/notifications?unread_only=false",
        { cache: "no-store" },
      ).catch(() => null);
      if (notificationResponse?.ok)
        setNotifications((await notificationResponse.json()) as CareerNotification[]);
      const interventionResponse = await fetch("/api/portal/interventions?status=PENDING", { cache: "no-store" }).catch(() => null);
      if (interventionResponse?.ok)
        setInterventions((await interventionResponse.json()) as HumanIntervention[]);
      const analyticsResponse = await fetch("/api/portal/analytics", { cache: "no-store" }).catch(() => null);
      if (analyticsResponse?.ok)
        setAnalytics((await analyticsResponse.json()) as CareerAnalytics);
      setDashboardMessage("Dados persistidos e atualizados pela VPS.");
    }
    void refreshDashboard();
    const timer = window.setInterval(refreshDashboard, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    async function refresh() {
      try {
        const statusResponse = await fetch(`${AGENT_URL}/status`);
        if (!statusResponse.ok) throw new Error("agent-status");
        if (statusResponse.ok)
          setAgent((await statusResponse.json()) as AgentStatus);
        const [jobsResult, applicationsResult, googleResult] =
          await Promise.allSettled([
            fetch(`${AGENT_URL}/jobs`),
            fetch(`${AGENT_URL}/applications`),
            fetch(`${AGENT_URL}/google/status`),
          ]);
        if (jobsResult.status === "fulfilled" && jobsResult.value.ok)
          setJobs((await jobsResult.value.json()) as Job[]);
        if (
          applicationsResult.status === "fulfilled" &&
          applicationsResult.value.ok
        )
          setApplications(
            (await applicationsResult.value.json()) as Application[],
          );
        if (googleResult.status === "fulfilled" && googleResult.value.ok)
          setGoogleStatus((await googleResult.value.json()) as GoogleStatus);
      } catch {
        setAgent((current) => ({
          ...current,
          status: "offline",
          message:
            "Sem comunicação com o computador. Verifique o Wi-Fi; o painel tentará reconectar automaticamente.",
        }));
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 2500);
    return () => window.clearInterval(timer);
  }, []);

  const roleList = useMemo(
    () =>
      roles
        .split("\n")
        .map((role) => role.trim())
        .filter(Boolean),
    [roles],
  );
  const mainRole = roleList[0] ?? "Analista de Sustentação";

  function record(message: string) {
    const next = [
      { at: new Date().toLocaleTimeString("pt-BR"), message },
      ...logs,
    ].slice(0, 100);
    setLogs(next);
    localStorage.setItem("careeros.logs", JSON.stringify(next));
  }

  function openPlatform(name: string, url: string) {
    window.open(url, "_blank", "noopener,noreferrer");
    record(`${name} aberto no Chrome para login ou consulta manual.`);
  }

  async function beginWork() {
    try {
      await fetch(`${AGENT_URL}/browser/start`, { method: "POST" });
      setRunning(true);
      record(`Agente iniciado. Busca principal: ${mainRole}.`);
      setView("automation");
    } catch {
      record("Falha ao conectar ao agente local na porta 8765.");
      setView("automation");
    }
  }

  async function stopWork() {
    await fetch(`${AGENT_URL}/stop`, { method: "POST" }).catch(() => undefined);
    setRunning(false);
    record("Sessão interrompida pelo botão de emergência.");
  }

  async function openLogin() {
    const response = await fetch(`${AGENT_URL}/browser/login`, {
      method: "POST",
    });
    if (!response.ok) {
      record("Não foi possível abrir o Chrome exclusivo.");
      return;
    }
    setRunning(true);
    record("Chrome exclusivo aberto para autenticação nas plataformas.");
  }

  async function openManualLogin() {
    const response = await fetch(`${AGENT_URL}/browser/manual-login`, {
      method: "POST",
    });
    if (!response.ok) {
      record("Não foi possível iniciar o modo de login Google.");
      return;
    }
    setRunning(false);
    record("Chrome normal aberto para login Google. Feche-o ao terminar.");
  }

  async function runSearch() {
    const response = await fetch(`${AGENT_URL}/play`, { method: "POST" });
    if (!response.ok) {
      record(
        "A operação diária não iniciou: já existe uma execução ou o agente está indisponível.",
      );
      return;
    }
    setRunning(true);
    record(
      "Operação diária completa iniciada: busca, análise, preparação e candidatura.",
    );
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    const nextProfile = {
      ...profile,
      target_roles: roleList,
      skills: skillsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
    const response = await fetch("/api/portal/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nextProfile),
    });
    if (!response.ok) {
      setProfileMessage("Falha ao salvar o perfil.");
      return;
    }
    setProfile((await response.json()) as Profile);
    setProfileMessage("Perfil salvo.");
    record("Perfil profissional atualizado.");
  }

  async function uploadResume(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setProfileMessage("Enviando currículo...");
    const response = await fetch(
      `/api/portal/profile/resume?family=${encodeURIComponent(resumeFamily)}&language=pt-BR`,
      { method: "POST", body },
    );
    if (!response.ok) {
      setProfileMessage(
        "Falha ao importar currículo. Use PDF ou DOCX de até 10 MB.",
      );
      return;
    }
    const data = (await response.json()) as { resume_path: string };
    setProfile((current) => ({ ...current, resume_path: data.resume_path }));
    setProfileMessage("Currículo importado com segurança.");
    record("Currículo importado.");
  }

  async function saveApprovedAnswer(event: FormEvent) {
    event.preventDefault();
    setAnswerMessage("Salvando resposta verificada...");
    const response = await fetch("/api/portal/answers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(answerDraft),
    });
    if (!response.ok) {
      setAnswerMessage("Não foi possível salvar. Revise os campos.");
      return;
    }
    const savedAnswer = (await response.json()) as ApprovedAnswer;
    setAnswers((current) => [
      savedAnswer,
      ...current.filter((item) => item.id !== savedAnswer.id),
    ]);
    setAnswerDraft((current) => ({
      ...current,
      question: "",
      approved_answer: "",
    }));
    setAnswerMessage("Resposta aprovada e registrada com auditoria.");
    record("Memória de respostas atualizada.");
  }

  async function analyzeJobs() {
    const response = await fetch(`${AGENT_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ minimum_score: 75, limit: 500 }),
    });
    if (!response.ok) {
      record("Falha ao analisar vagas.");
      return;
    }
    const data = (await response.json()) as {
      approved: number;
      review: number;
      ignored: number;
    };
    record(
      `Análise concluída: ${data.approved} aprovadas, ${data.review} para revisão e ${data.ignored} ignoradas.`,
    );
  }

  async function prepareApplications() {
    const response = await fetch(`${AGENT_URL}/applications/prepare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 20 }),
    });
    if (!response.ok) {
      record(
        "Não foi possível preparar candidaturas. Verifique perfil e currículo.",
      );
      return;
    }
    setRunning(true);
    record("Preparação de até 20 candidaturas iniciada.");
  }

  async function scanCareerMail() {
    record("Verificando novos e-mails de processos seletivos...");
    const response = await fetch(`${AGENT_URL}/google/scan`, {
      method: "POST",
    });
    if (!response.ok) {
      record("Falha ao consultar o Gmail.");
      return;
    }
    const data = (await response.json()) as {
      discovered: number;
      items: CareerMail[];
    };
    setGoogleStatus((current) => ({
      ...current,
      alerts: data.items.filter((item) => item.status === "NEW").length,
      last_items: data.items.slice(0, 20),
    }));
    record(`Gmail analisado: ${data.discovered} novos alertas relevantes.`);
  }

  async function createMailDraft(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId }),
    });
    if (!response.ok) {
      record("Não foi possível criar o rascunho seguro.");
      return;
    }
    record(
      "Rascunho criado no Gmail para sua revisão; nenhuma mensagem foi enviada.",
    );
    await scanCareerMail();
  }

  async function scheduleCareerEvent(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/calendar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId }),
    });
    if (!response.ok) {
      record(
        "Não foi possível criar o compromisso; confira data e horário do convite.",
      );
      return;
    }
    record(
      "Compromisso criado na Agenda Google com lembretes de 24 horas e 1 hora.",
    );
    await scanCareerMail();
  }

  async function markQuestionnaireComplete(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/questionnaire/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId }),
    });
    if (!response.ok) {
      record("Não foi possível atualizar o questionário.");
      return;
    }
    record("Questionário marcado como concluído.");
    setGoogleStatus((current) => ({
      ...current,
      last_items: current.last_items.map((item) =>
        item.message_id === messageId
          ? {
              ...item,
              questionnaire_status: "COMPLETED_MANUALLY",
              status: "COMPLETED",
            }
          : item,
      ),
    }));
  }

  function saveSettings(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem("careeros.roles", roles);
    localStorage.setItem("careeros.location", location);
    setSaved(true);
    record("Configurações de busca atualizadas.");
    setTimeout(() => setSaved(false), 2500);
  }

  async function decide(id: string, decision: "APPROVED" | "DISCARDED") {
    const response = await fetch(`/api/portal/decisions/${id}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    if (!response.ok) {
      record("Não foi possível registrar a decisão.");
      return;
    }
    setDashboard((current) =>
      current
        ? {
            ...current,
            decisions: current.decisions.filter((item) => item.id !== id),
            workspace: {
              ...current.workspace,
              pending_decisions: Math.max(
                0,
                current.workspace.pending_decisions - 1,
              ),
            },
          }
        : current,
    );
    record(
      decision === "APPROVED"
        ? "Oportunidade aprovada para preparação."
        : "Oportunidade descartada com rastreabilidade.",
    );
  }

  async function markNotificationRead(id: string) {
    const response = await fetch(`/api/portal/notifications/${id}/read`, { method: "POST" });
    if (!response.ok) return;
    setNotifications((current) => current.map((item) =>
      item.id === id ? { ...item, read_at: new Date().toISOString() } : item,
    ));
  }

  async function evaluateFollowups() {
    const response = await fetch("/api/portal/followups/evaluate", { method: "POST" });
    if (!response.ok) {
      record("Não foi possível avaliar follow-ups.");
      return;
    }
    const result = (await response.json()) as { notifications: number };
    record(`${result.notifications} lembrete(s) de follow-up criado(s), sem envio automático.`);
  }

  async function resolveIntervention(id: string, resolution: "RESOLVED" | "SKIPPED") {
    const response = await fetch(`/api/portal/interventions/${id}/resolve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ resolution }),
    });
    if (!response.ok) {
      record("Não foi possível atualizar a intervenção.");
      return;
    }
    setInterventions((current) => current.filter((item) => item.id !== id));
    record(resolution === "RESOLVED" ? "Intervenção concluída." : "Intervenção ignorada com registro.");
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand-mark">H</div>
        <h1>
          HelpSystem<span> Carreira</span>
        </h1>
        <p>CareerOS · orquestrador de carreira</p>
        <nav>
          {nav.map(([id, label]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="status-dot online" />
          VPS online
        </div>
      </aside>
      <section className="content">
        <header className="topbar">
          <div>
            <span className="eyebrow">CENTRAL OPERACIONAL</span>
            <h2>{nav.find(([id]) => id === view)?.[1]}</h2>
            <p>
              Descobrir, validar, decidir e acompanhar oportunidades
              qualificadas.
            </p>
          </div>
          <div className="topbar-actions">
            <button className="intervention-button" onClick={() => setView("interventions")}>Ações <span>{interventions.length}</span></button>
            <button className="notification-button" onClick={() => setView("notifications")}>Alertas <span>{notifications.filter((item) => !item.read_at).length}</span></button>
            <button className="danger" onClick={stopWork} disabled={!running}>PARAR AUTOMAÇÃO</button>
          </div>
        </header>

        {view === "overview" && (
          <>
            <div className="hero-panel">
              <div>
                <span className="eyebrow">RADAR INTELIGENTE</span>
                <h3>Bom trabalho, Rodolfo.</h3>
                <p>
                  Menos candidaturas ruins. Mais decisões explicáveis e
                  oportunidades com aderência real.
                </p>
              </div>
              <button className="primary" onClick={() => setView("decisions")}>
                Revisar decisões <span>{dashboard?.decisions.length ?? 0}</span>
              </button>
            </div>
            <div className="metrics">
              {[
                [
                  "Encontradas",
                  String(dashboard?.workspace.jobs ?? jobs.length),
                  "Hoje e histórico",
                ],
                [
                  "Qualificadas",
                  String(jobs.filter((job) => (job.score ?? 0) >= 75).length),
                  "Fit mínimo 75",
                ],
                [
                  "Aplicadas",
                  String(dashboard?.workspace.applications ?? appliedCount),
                  "Confirmadas",
                ],
                [
                  "Ação necessária",
                  String(
                    dashboard?.workspace.pending_decisions ?? pendingCount,
                  ),
                  "Revisão humana",
                ],
              ].map(([label, value, hint]) => (
                <article key={label}>
                  <small>{label}</small>
                  <b>{value}</b>
                  <span>{hint}</span>
                </article>
              ))}
            </div>
            <div className="grid two dashboard-grid">
              <article className="panel">
                <div className="section-header">
                  <div>
                    <span className="eyebrow">PIPELINE</span>
                    <h3>Conversão de carreira</h3>
                  </div>
                  <button
                    className="link-button"
                    onClick={() => setView("applications")}
                  >
                    Ver pipeline
                  </button>
                </div>
                <div className="pipeline">
                  {[
                    [
                      "Aplicadas",
                      dashboard?.workspace.applications ?? appliedCount,
                    ],
                    ["Respostas", 0],
                    ["Entrevistas", 0],
                    ["Técnicas", 0],
                    ["Propostas", 0],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                      <i
                        style={{ width: `${Math.max(4, Number(value) * 8)}%` }}
                      />
                    </div>
                  ))}
                </div>
              </article>
              <article className="panel system-card">
                <div className="section-header">
                  <div>
                    <span className="eyebrow">SAÚDE</span>
                    <h3>Estado dos motores</h3>
                  </div>
                  <span className="live-pill">VPS ativa</span>
                </div>
                <ul className="engine-list">
                  <li>
                    <span className="status-dot online" />
                    Orquestrador, API, banco e fila: online
                  </li>
                  <li>
                    <span
                      className={`status-dot ${agent.status === "offline" ? "warning" : "online"}`}
                    />
                    Executor do navegador:{" "}
                    {agent.status === "offline"
                      ? "aguardando conector do computador"
                      : agent.status}
                  </li>
                  <li>
                    <span
                      className={`status-dot ${googleStatus.connected ? "online" : "warning"}`}
                    />
                    Gmail e Agenda:{" "}
                    {googleStatus.connected
                      ? "conectados"
                      : "OAuth pendente na VPS"}
                  </li>
                  <li>
                    <span className="status-dot safe" />
                    Autoenvio: bloqueado por segurança
                  </li>
                </ul>
                <small className="muted">{dashboardMessage}</small>
              </article>
            </div>
            <article className="panel roadmap-strip">
              <div>
                <span className="eyebrow">ESTRATÉGIA</span>
                <h3>Como o CareerOS decide</h3>
              </div>
              {[
                "Descobrir",
                "Validar",
                "Pontuar",
                "Decidir",
                "Personalizar",
                "Acompanhar",
              ].map((step, index) => (
                <div className="roadmap-step" key={step}>
                  <b>{index + 1}</b>
                  <span>{step}</span>
                </div>
              ))}
            </article>
          </>
        )}

        {view === "decisions" && (
          <>
            <div className="notice">
              <strong>Inbox de decisões</strong>
              <span>
                Somente oportunidades ambíguas, de alto impacto ou que exigem
                consentimento chegam aqui.
              </span>
            </div>
            {!dashboard?.decisions.length ? (
              <article className="panel empty-state">
                <div className="empty-icon">✓</div>
                <h3>Nenhuma decisão pendente</h3>
                <p>
                  A fila está limpa. Novas oportunidades qualificadas aparecerão
                  aqui com score, riscos e justificativas.
                </p>
                <button className="primary" onClick={() => setView("rules")}>
                  Revisar regras
                </button>
              </article>
            ) : (
              <div className="decision-grid">
                {dashboard.decisions.map((item) => (
                  <article className="panel decision-card" key={item.id}>
                    <div className="fit-ring">
                      <strong>{item.fit ?? "—"}</strong>
                      <small>FIT</small>
                    </div>
                    <div>
                      <span className="badge">{item.recommendation}</span>
                      <h3>{item.title}</h3>
                      <p>
                        {item.company ?? "Empresa não identificada"} ·{" "}
                        {item.work_model ?? "Modalidade a validar"}
                      </p>
                      <small>
                        {item.location ?? "Localização não informada"}
                      </small>
                      <div className="decision-actions">
                        <button
                          className="primary"
                          onClick={() => void decide(item.id, "APPROVED")}
                        >
                          Aprovar
                        </button>
                        <button
                          onClick={() => void decide(item.id, "DISCARDED")}
                        >
                          Descartar
                        </button>
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Ver vaga
                        </a>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </>
        )}

        {view === "rules" && (
          <>
            <div className="notice">
              <strong>Memória operacional persistida</strong>
              <span>
                Estas regras ficam no PostgreSQL e explicam por que uma vaga
                recebe bônus, risco, revisão ou bloqueio.
              </span>
            </div>
            <div className="rule-grid">
              {(dashboard?.rules ?? []).map((rule) => (
                <article className="panel rule-card" key={rule.code}>
                  <div>
                    <span
                      className={`rule-type ${rule.rule_type.toLowerCase()}`}
                    >
                      {rule.rule_type}
                    </span>
                    <small>Prioridade {rule.priority}</small>
                  </div>
                  <h3>{rule.label}</h3>
                  <code>{rule.code}</code>
                  <p>
                    {Object.entries(rule.configuration)
                      .map(
                        ([key, value]) =>
                          `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`,
                      )
                      .join(" · ")}
                  </p>
                </article>
              ))}
            </div>
          </>
        )}

        {view === "profile" && (
          <form className="panel form" onSubmit={saveProfile}>
            <h3>Perfil profissional obrigatório</h3>
            <p>
              Somente estes dados aprovados poderão ser usados nos formulários.
            </p>
            <label>
              Nome completo
              <input
                required
                value={profile.full_name}
                onChange={(event) =>
                  setProfile({ ...profile, full_name: event.target.value })
                }
              />
            </label>
            <label>
              E-mail
              <input
                required
                type="email"
                value={profile.email}
                onChange={(event) =>
                  setProfile({ ...profile, email: event.target.value })
                }
              />
            </label>
            <label>
              Telefone
              <input
                value={profile.phone}
                onChange={(event) =>
                  setProfile({ ...profile, phone: event.target.value })
                }
              />
            </label>
            <div className="form-row">
              <label>
                Cidade
                <input
                  value={profile.city}
                  onChange={(event) =>
                    setProfile({ ...profile, city: event.target.value })
                  }
                />
              </label>
              <label>
                Estado
                <input
                  value={profile.state}
                  onChange={(event) =>
                    setProfile({ ...profile, state: event.target.value })
                  }
                />
              </label>
            </div>
            <label>
              LinkedIn
              <input
                value={profile.linkedin_url}
                onChange={(event) =>
                  setProfile({ ...profile, linkedin_url: event.target.value })
                }
              />
            </label>
            <label>
              Pretensão salarial
              <input
                value={profile.salary_expectation}
                onChange={(event) =>
                  setProfile({
                    ...profile,
                    salary_expectation: event.target.value,
                  })
                }
              />
            </label>
            <label>
              Competências, separadas por vírgula
              <textarea
                rows={5}
                value={skillsText}
                onChange={(event) => setSkillsText(event.target.value)}
              />
            </label>
            <label>
              Objetivo deste currículo
              <select
                value={resumeFamily}
                onChange={(event) => setResumeFamily(event.target.value)}
              >
                <option value="GENERAL">Geral</option>
                <option value="PT_SUPPORT_SENIOR">
                  Suporte e Sustentação Sênior
                </option>
                <option value="PT_DBA_SQL">DBA e SQL</option>
                <option value="PT_DATA">Dados</option>
                <option value="EN_SUPPORT_DATABASE">
                  Support / Database (English)
                </option>
                <option value="EN_DATA_DATABASE">
                  Data / Database (English)
                </option>
                <option value="EN_DATA_ENGINEERING">
                  Data Engineering (English)
                </option>
              </select>
            </label>
            <label>
              Currículo PDF ou DOCX
              <input
                type="file"
                accept=".pdf,.docx"
                onChange={(event) => void uploadResume(event)}
              />
            </label>
            <p className={profile.resume_path ? "ok" : "danger-text"}>
              {profile.resume_path
                ? "Currículo importado."
                : "Currículo ainda não importado."}
            </p>
            <button className="primary" type="submit">
              Salvar perfil
            </button>
            {profileMessage && <span className="ok">{profileMessage}</span>}
          </form>
        )}

        {view === "answers" && (
          <div className="grid two answer-layout">
            <form className="panel form" onSubmit={saveApprovedAnswer}>
              <h3>Memória de respostas</h3>
              <p>
                Cadastre apenas fatos verdadeiros. O sistema nunca inventa uma
                resposta quando não encontra conteúdo aprovado.
              </p>
              <label>
                Pergunta
                <input
                  required
                  value={answerDraft.question}
                  onChange={(event) =>
                    setAnswerDraft({
                      ...answerDraft,
                      question: event.target.value,
                    })
                  }
                  placeholder="Ex.: Qual é sua pretensão salarial?"
                />
              </label>
              <div className="form-row">
                <label>
                  Categoria
                  <select
                    value={answerDraft.category}
                    onChange={(event) =>
                      setAnswerDraft({
                        ...answerDraft,
                        category: event.target.value,
                      })
                    }
                  >
                    <option value="GENERAL">Geral</option>
                    <option value="EXPERIENCE">Experiência</option>
                    <option value="AVAILABILITY">Disponibilidade</option>
                    <option value="COMPENSATION">Remuneração</option>
                    <option value="ELIGIBILITY">Elegibilidade</option>
                  </select>
                </label>
                <label>
                  Idioma
                  <select
                    value={answerDraft.language}
                    onChange={(event) =>
                      setAnswerDraft({
                        ...answerDraft,
                        language: event.target.value,
                      })
                    }
                  >
                    <option value="pt-BR">Português</option>
                    <option value="en">English</option>
                  </select>
                </label>
              </div>
              <label>
                Resposta aprovada
                <textarea
                  required
                  rows={6}
                  value={answerDraft.approved_answer}
                  onChange={(event) =>
                    setAnswerDraft({
                      ...answerDraft,
                      approved_answer: event.target.value,
                    })
                  }
                />
              </label>
              <button className="primary" type="submit">
                Salvar resposta verificada
              </button>
              {answerMessage && <span className="ok">{answerMessage}</span>}
            </form>
            <article className="panel">
              <h3>Base aprovada ({answers.length})</h3>
              {answers.length === 0 ? (
                <p className="muted">
                  Nenhuma resposta cadastrada. Perguntas desconhecidas exigirão
                  revisão humana.
                </p>
              ) : (
                <div className="answer-list">
                  {answers.map((answer) => (
                    <div key={answer.id}>
                      <span className="badge">
                        {answer.category} · {answer.language}
                      </span>
                      <strong>{answer.question}</strong>
                      <p>{answer.approved_answer}</p>
                      <small>
                        {answer.verified ? "Verificada" : "Em revisão"} · usada{" "}
                        {answer.usage_count} vez(es)
                      </small>
                    </div>
                  ))}
                </div>
              )}
            </article>
          </div>
        )}

        {view === "platforms" && (
          <>
            <div className="notice">
              <strong>Acesso centralizado</strong>
              <span>
                Se uma plataforma pedir login, autentique-se na aba aberta. O
                Chrome manterá a sessão como já faz normalmente.
              </span>
            </div>
            <div className="platform-grid">
              {platforms.map((platform) => (
                <article className="platform" key={platform.name}>
                  <div>
                    <span className="badge">{platform.priority}</span>
                    <h3>{platform.name}</h3>
                    <p>
                      Buscar por: <strong>{mainRole}</strong>
                    </p>
                  </div>
                  <div className="actions">
                    <button
                      onClick={() => openPlatform(platform.name, platform.home)}
                    >
                      Abrir / entrar
                    </button>
                    <button
                      className="primary"
                      onClick={() =>
                        openPlatform(platform.name, platform.search(mainRole))
                      }
                    >
                      Buscar vagas
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="blocked">
              <strong>Gupy bloqueada</strong>
              <span>
                Links para gupy.io não são oferecidos pelo HelpSystem Carreira.
              </span>
            </div>
          </>
        )}

        {view === "jobs" && (
          <article className="panel">
            <div className="section-header">
              <h3>Vagas coletadas ({jobs.length})</h3>
              <button className="primary" onClick={() => void analyzeJobs()}>
                Analisar e calcular score
              </button>
            </div>
            {jobs.length === 0 ? (
              <p className="muted">
                Execute uma busca automática para preencher esta lista.
              </p>
            ) : (
              <div className="job-list">
                {jobs
                  .slice()
                  .reverse()
                  .map((job) => (
                    <a
                      key={job.url}
                      href={job.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="badge">{job.source}</span>
                      <strong>{job.title}</strong>
                      <small>
                        {job.score !== undefined
                          ? `${job.score}% · ${job.decision}`
                          : `${job.search_role} · ${job.status}`}
                      </small>
                    </a>
                  ))}
              </div>
            )}
          </article>
        )}
        {view === "applications" && (
          <article className="panel">
            <div className="section-header">
              <h3>Status e feedback ({applications.length})</h3>
              <button
                className="primary"
                onClick={() => void prepareApplications()}
              >
                Preparar até 20 qualificadas
              </button>
            </div>
            {applications.length === 0 ? (
              <p className="muted">
                Nenhuma candidatura preparada. Complete o perfil, analise as
                vagas e inicie a preparação.
              </p>
            ) : (
              <div className="job-list">
                {applications
                  .slice()
                  .sort((a, b) =>
                    String(b.created_at ?? "").localeCompare(
                      String(a.created_at ?? ""),
                    ),
                  )
                  .map((application) => (
                    <a
                      key={application.id}
                      href={application.job_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="badge">{application.source}</span>
                      <strong>{application.title}</strong>
                      <small>
                        {application.status === "APPLIED"
                          ? "✅ Enviada e confirmada"
                          : application.status === "CLOSED"
                            ? "⛔ Encerrada"
                            : application.status === "MANUAL_REQUIRED"
                              ? "⚠️ Precisa de ação"
                              : application.status === "FAILED"
                                ? "❌ Falhou"
                                : "⏳ Em processamento"}{" "}
                        · {application.reason}
                      </small>
                      {application.feedback && (
                        <small>
                          Recomendação: {application.recommendation} ·{" "}
                          {application.feedback}
                        </small>
                      )}
                      <small>
                        {application.region
                          ? `Região: ${application.region} · `
                          : ""}
                        {application.salary_brl
                          ? `Salário informado: ${application.salary_brl.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })} · `
                          : "Salário não publicado · "}
                        Tentativas: {application.attempts ?? 0}
                        {application.submitted_at
                          ? ` · Confirmada em ${new Date(application.submitted_at).toLocaleString("pt-BR")}`
                          : ""}
                      </small>
                      {application.ai_answers &&
                        application.ai_answers.length > 0 && (
                          <small>
                            IA respondeu:{" "}
                            {application.ai_answers
                              .map(
                                (item) => `${item.answer} (${item.evidence})`,
                              )
                              .join("; ")}
                          </small>
                        )}
                    </a>
                  ))}
              </div>
            )}
          </article>
        )}
        {view === "notifications" && <article className="panel">
          <div className="section-header"><div><h3>Central de notificações</h3><p>Entrevistas e propostas aparecem primeiro. Nenhum follow-up é enviado sem sua revisão.</p></div><button className="primary" onClick={() => void evaluateFollowups()}>Avaliar follow-ups</button></div>
          {notifications.length === 0 ? <p className="muted">Nenhuma notificação pendente.</p> : <div className="notification-list">{notifications.map((item) => <button key={item.id} className={`${item.priority.toLowerCase()} ${item.read_at ? "read" : ""}`} onClick={() => void markNotificationRead(item.id)}><span className="badge">{item.priority}</span><strong>{item.title}</strong><p>{item.body}</p><small>{new Date(item.created_at).toLocaleString("pt-BR")}{item.read_at ? " · lida" : " · toque para marcar como lida"}</small></button>)}</div>}
        </article>}
        {view === "interventions" && <article className="panel">
          <div className="section-header"><div><h3>Intervenções humanas</h3><p>Somente decisões que exigem você. CAPTCHA, MFA e dados não comprovados nunca são contornados.</p></div><span className="badge">{interventions.length} pendente(s)</span></div>
          {interventions.length === 0 ? <div className="empty-state"><strong>Tudo sob controle</strong><p className="muted">Nenhuma ação humana está pendente.</p></div> : <div className="intervention-list">{interventions.map((item) => <section key={item.id} className="intervention-card"><div><span className="badge">{item.reason.replaceAll("_", " ")}</span><strong>{item.title}</strong><p>{item.instructions}</p><small>{new Date(item.created_at).toLocaleString("pt-BR")}</small></div><div className="intervention-actions">{item.page_url && <a className="secondary-button" href={item.page_url} target="_blank" rel="noreferrer">Abrir página</a>}<button className="primary" onClick={() => void resolveIntervention(item.id, "RESOLVED")}>Concluí</button><button onClick={() => void resolveIntervention(item.id, "SKIPPED")}>Ignorar</button></div></section>)}</div>}
        </article>}
        {view === "analytics" && <>
          <section className="metrics analytics-metrics"><article><span>Candidaturas no Core</span><b>{analytics?.sample.applications ?? 0}</b><small>Base auditável</small></article><article><span>Envios confirmados</span><b>{analytics?.sample.submitted ?? 0}</b><small>{analytics?.rates.submission_percent == null ? "Sem taxa calculável" : `${analytics.rates.submission_percent}% da base`}</small></article><article><span>Comunicações</span><b>{analytics?.sample.communications ?? 0}</b><small>{analytics?.rates.response_percent == null ? "Sem taxa calculável" : `${analytics.rates.response_percent}% após envio`}</small></article><article><span>Ações humanas</span><b>{analytics?.interventions.pending ?? 0}</b><small>{analytics?.interventions.resolved ?? 0} resolvidas</small></article></section>
          <div className="dashboard-grid"><article className="panel"><h3>Funil comprovado</h3>{!analytics || analytics.funnel.length === 0 ? <p className="muted">Sem candidaturas persistidas. O sistema não fabricará indicadores.</p> : <div className="analytics-list">{analytics.funnel.map((item) => <div key={item.status}><span>{item.status.replaceAll("_", " ")}</span><strong>{item.total}</strong></div>)}</div>}</article><article className="panel"><h3>Qualidade da análise</h3>{analytics?.warnings.length ? <ul className="warning-list">{analytics.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p className="ok">Amostra mínima disponível para recomendações.</p>}<p className="muted">Recomendações automáticas: {analytics?.recommendations_enabled ? "habilitadas pela amostra" : "bloqueadas por segurança"}.</p></article></div>
          <article className="panel"><h3>Desempenho por fonte</h3>{!analytics || analytics.sources.length === 0 ? <p className="muted">Nenhuma fonte possui dados persistidos.</p> : <div className="analytics-list">{analytics.sources.map((item) => <div key={item.source}><span><strong>{item.source}</strong><small>{item.jobs} vagas · {item.applications} candidaturas</small></span><b>{item.progressed} avançaram</b></div>)}</div>}</article>
        </>}
        {view === "inbox" && (
          <article className="panel">
            <div className="section-header">
              <div>
                <h3>Recrutamento no Gmail</h3>
                <p className={googleStatus.connected ? "ok" : "danger-text"}>
                  {googleStatus.connected
                    ? `Conectado: ${googleStatus.email} · Agenda ativa`
                    : "Google desconectado"}
                </p>
              </div>
              <button className="primary" onClick={() => void scanCareerMail()}>
                VERIFICAR AGORA
              </button>
            </div>
            <p>
              {googleStatus.alerts} alerta(s) aguardando análise. O
              monitoramento automático ocorre a cada 10 minutos.
            </p>
            {googleStatus.last_items.length === 0 ? (
              <p className="muted">
                Nenhum e-mail de recrutamento classificado nos últimos 30 dias.
              </p>
            ) : (
              <div className="job-list">
                {googleStatus.last_items.map((mail) => (
                  <div className="mail-card" key={mail.message_id}>
                    <span className="badge">{mail.category}</span>
                    <strong>{mail.subject}</strong>
                    <small>
                      {mail.sender} ·{" "}
                      {new Date(mail.received_at).toLocaleString("pt-BR")} ·
                      confiança {mail.confidence}%
                    </small>
                    <small>{mail.reason}</small>
                    <p>{mail.snippet}</p>
                    {mail.category === "QUESTIONNAIRE" && (
                      <>
                        <small
                          className={
                            mail.questionnaire_status?.startsWith("COMPLETED")
                              ? "ok"
                              : "danger-text"
                          }
                        >
                          Questionário:{" "}
                          {mail.questionnaire_status?.startsWith("COMPLETED")
                            ? "concluído"
                            : mail.questionnaire_url
                              ? "pendente — link disponível"
                              : "situação não confirmada — link não localizado"}
                        </small>
                        <div className="mail-actions">
                          {mail.questionnaire_url &&
                            !mail.questionnaire_status?.startsWith(
                              "COMPLETED",
                            ) && (
                              <a
                                className="primary"
                                href={mail.questionnaire_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Abrir questionário
                              </a>
                            )}
                          {!mail.questionnaire_status?.startsWith(
                            "COMPLETED",
                          ) && (
                            <button
                              onClick={() =>
                                void markQuestionnaireComplete(mail.message_id)
                              }
                            >
                              Marcar como concluído
                            </button>
                          )}
                        </div>
                      </>
                    )}
                    {mail.suggested_reply && (
                      <button
                        disabled={Boolean(mail.draft_id)}
                        onClick={() => void createMailDraft(mail.message_id)}
                      >
                        {mail.draft_id
                          ? "Rascunho criado"
                          : "Criar rascunho no Gmail"}
                      </button>
                    )}
                    {mail.event_candidate && (
                      <>
                        <small>
                          Agenda:{" "}
                          {new Date(mail.event_candidate.start).toLocaleString(
                            "pt-BR",
                          )}
                        </small>
                        <button
                          disabled={Boolean(mail.calendar_event_id)}
                          onClick={() =>
                            void scheduleCareerEvent(mail.message_id)
                          }
                        >
                          {mail.calendar_event_id
                            ? "Compromisso criado"
                            : "Adicionar à Agenda"}
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </article>
        )}
        {view === "automation" && (
          <article className="panel">
            <h3>Agente automático</h3>
            <p>
              Status:{" "}
              <strong
                className={agent.status === "offline" ? "danger-text" : "ok"}
              >
                {agent.status.toUpperCase()}
              </strong>
            </p>
            <p>{agent.message}</p>
            {agent.platform && (
              <p>
                Agora: {agent.role} em {agent.platform}
              </p>
            )}
            <p>
              Encontradas: <strong>{agent.found}</strong> · Gupy bloqueadas:{" "}
              <strong>{agent.blocked}</strong>
            </p>
            <div className="automation-actions">
              <button onClick={() => void openManualLogin()}>
                Login Google (Chrome normal)
              </button>
              <button onClick={() => void beginWork()}>
                Retomar Chrome automático
              </button>
              <button onClick={() => void openLogin()}>
                Abrir logins comuns
              </button>
              <button
                className="primary"
                onClick={() => void runSearch()}
                disabled={["running", "applying", "preparing"].includes(
                  agent.status,
                )}
              >
                PLAY — FAZER TUDO AGORA
              </button>
            </div>
            <p className="muted">
              O Play executa busca, análise, score, preparação, preenchimento e
              envio seguro. CAPTCHA, MFA, testes e campos não comprovados são
              encaminhados para intervenção manual.
            </p>
          </article>
        )}
        {view === "settings" && (
          <form className="panel form" onSubmit={saveSettings}>
            <h3>Preferências de busca</h3>
            <label>
              Cargos, um por linha
              <textarea
                value={roles}
                onChange={(event) => setRoles(event.target.value)}
                rows={8}
              />
            </label>
            <label>
              Localização e modalidade
              <input
                value={location}
                onChange={(event) => setLocation(event.target.value)}
              />
            </label>
            <label className="readonly">
              Meta diária
              <input value="20 candidaturas qualificadas" readOnly />
            </label>
            <button className="primary" type="submit">
              Salvar configurações
            </button>
            {saved && <span className="ok">Configurações salvas.</span>}
          </form>
        )}
        {view === "logs" && (
          <article className="panel">
            <h3>Atividade local</h3>
            {logs.length === 0 ? (
              <p className="muted">Nenhuma atividade registrada.</p>
            ) : (
              <div className="log-list">
                {logs.map((entry, index) => (
                  <p key={`${entry.at}-${index}`}>
                    <time>{entry.at}</time>
                    {entry.message}
                  </p>
                ))}
              </div>
            )}
          </article>
        )}
        {view === "security" && (
          <article className="panel">
            <h3>Proteções ativas</h3>
            <ul>
              <li>Nenhuma senha é solicitada ou armazenada.</li>
              <li>
                Login, CAPTCHA e MFA permanecem sob seu controle no Chrome.
              </li>
              <li>Gupy está bloqueada.</li>
              <li>
                Somente vagas com score mínimo de 75% entram no autoenvio.
              </li>
              <li>Campos sem resposta comprovada interrompem a candidatura.</li>
            </ul>
          </article>
        )}
      </section>
    </main>
  );
}
