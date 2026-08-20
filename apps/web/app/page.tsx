"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

type View = "overview" | "profile" | "platforms" | "jobs" | "applications" | "inbox" | "automation" | "settings" | "logs" | "security";
type LogEntry = { at: string; message: string };
type AgentStatus = { status: string; platform?: string; role?: string; found: number; blocked: number; message: string };
type Job = { source: string; title: string; url: string; search_role: string; status: string; score?: number; decision?: string };
type Application = { id: string; title: string; source: string; score: number; status: string; reason: string; job_url: string; created_at?: string; submitted_at?: string | null; attempts?: number; ai_answers?: Array<{name: string; answer: string; evidence: string}>; region?: string; salary_brl?: number | null; recommendation?: string; feedback?: string };
type AIStatus = { available: boolean; model?: string | null; privacy: string };
type CareerMail = { message_id: string; subject: string; sender: string; received_at: string; category: string; confidence: number; reason: string; snippet: string; status: string; suggested_reply?: string; draft_id?: string | null; calendar_event_id?: string | null; event_candidate?: { title: string; start: string; end: string; timezone: string } | null; questionnaire_url?: string | null; questionnaire_status?: string | null };
type GoogleStatus = { connected: boolean; email?: string | null; calendar: boolean; alerts: number; last_items: CareerMail[] };
type Profile = { full_name: string; email: string; phone: string; city: string; state: string; linkedin_url: string; salary_expectation: string; work_models: string[]; target_roles: string[]; skills: string[]; approved_answers: Record<string, string>; resume_path: string };
const AGENT_URL = "/agent";

const nav: Array<[View, string]> = [
  ["profile", "Perfil e Currículo"],
  ["overview", "Visão Geral"], ["platforms", "Plataformas"], ["jobs", "Vagas"],
  ["applications", "Candidaturas"], ["inbox", "E-mails e Agenda"], ["automation", "Automação"],
  ["settings", "Configurações"], ["logs", "Logs"], ["security", "Segurança"],
];

const platforms = [
  { name: "InfoJobs", priority: "Prioridade 1", home: "https://www.infojobs.com.br/", search: (q: string) => `https://www.infojobs.com.br/vagas-de-emprego-${encodeURIComponent(q.toLowerCase().replaceAll(" ", "-"))}.aspx` },
  { name: "Indeed", priority: "Prioridade 2", home: "https://br.indeed.com/", search: (q: string) => `https://br.indeed.com/jobs?q=${encodeURIComponent(q)}&l=Brasil` },
  { name: "Catho", priority: "Prioridade 3", home: "https://www.catho.com.br/vagas/", search: (q: string) => `https://www.catho.com.br/vagas/?q=${encodeURIComponent(q)}` },
  { name: "LinkedIn", priority: "Prioridade 4", home: "https://www.linkedin.com/jobs/", search: (q: string) => `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(q)}&location=Brasil` },
];

const defaultRoles = "Analista de Sustentação\nAnalista de Suporte N3\nAnalista de Sistemas\nDBA SQL Server\nEngenheiro de Dados";

export default function Home() {
  const [view, setView] = useState<View>("overview");
  const [roles, setRoles] = useState(defaultRoles);
  const [location, setLocation] = useState("Remoto Brasil; Campinas e região");
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [saved, setSaved] = useState(false);
  const [agent, setAgent] = useState<AgentStatus>({ status: "offline", found: 0, blocked: 0, message: "Conectando ao agente local..." });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [profile, setProfile] = useState<Profile>({ full_name: "", email: "", phone: "", city: "Campinas", state: "SP", linkedin_url: "", salary_expectation: "", work_models: ["REMOTE", "HYBRID"], target_roles: [], skills: [], approved_answers: {}, resume_path: "" });
  const [skillsText, setSkillsText] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [aiStatus, setAiStatus] = useState<AIStatus>({ available: false, privacy: "local-only" });
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>({ connected: false, calendar: false, alerts: 0, last_items: [] });
  const appliedCount = applications.filter((application) => application.status === "APPLIED").length;
  const pendingCount = applications.filter((application) => ["INSPECTING", "READY_TO_PREPARE", "READY_FOR_REVIEW"].includes(application.status)).length;

  useEffect(() => {
    const storedRoles = localStorage.getItem("careeros.roles");
    const storedLocation = localStorage.getItem("careeros.location");
    const storedLogs = localStorage.getItem("careeros.logs");
    if (storedRoles) setRoles(storedRoles);
    if (storedLocation) setLocation(storedLocation);
    if (storedLogs) setLogs(JSON.parse(storedLogs) as LogEntry[]);
    void fetch(`${AGENT_URL}/profile`).then(async (response) => {
      if (response.ok) {
        const nextProfile = await response.json() as Profile;
        setProfile(nextProfile);
        setSkillsText(nextProfile.skills.join(", "));
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    async function refresh() {
      try {
        const statusResponse = await fetch(`${AGENT_URL}/status`);
        if (!statusResponse.ok) throw new Error("agent-status");
        if (statusResponse.ok) setAgent(await statusResponse.json() as AgentStatus);
        const [jobsResult, applicationsResult, aiResult, googleResult] = await Promise.allSettled([
          fetch(`${AGENT_URL}/jobs`), fetch(`${AGENT_URL}/applications`), fetch(`${AGENT_URL}/ai/status`), fetch(`${AGENT_URL}/google/status`),
        ]);
        if (jobsResult.status === "fulfilled" && jobsResult.value.ok) setJobs(await jobsResult.value.json() as Job[]);
        if (applicationsResult.status === "fulfilled" && applicationsResult.value.ok) setApplications(await applicationsResult.value.json() as Application[]);
        if (aiResult.status === "fulfilled" && aiResult.value.ok) setAiStatus(await aiResult.value.json() as AIStatus);
        if (googleResult.status === "fulfilled" && googleResult.value.ok) setGoogleStatus(await googleResult.value.json() as GoogleStatus);
      } catch {
        setAgent((current) => ({ ...current, status: "offline", message: "Sem comunicação com o computador. Verifique o Wi-Fi; o painel tentará reconectar automaticamente." }));
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 2500);
    return () => window.clearInterval(timer);
  }, []);

  const roleList = useMemo(() => roles.split("\n").map((role) => role.trim()).filter(Boolean), [roles]);
  const mainRole = roleList[0] ?? "Analista de Sustentação";

  function record(message: string) {
    const next = [{ at: new Date().toLocaleTimeString("pt-BR"), message }, ...logs].slice(0, 100);
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
    const response = await fetch(`${AGENT_URL}/browser/login`, { method: "POST" });
    if (!response.ok) { record("Não foi possível abrir o Chrome exclusivo."); return; }
    setRunning(true);
    record("Chrome exclusivo aberto para autenticação nas plataformas.");
  }

  async function openManualLogin() {
    const response = await fetch(`${AGENT_URL}/browser/manual-login`, { method: "POST" });
    if (!response.ok) { record("Não foi possível iniciar o modo de login Google."); return; }
    setRunning(false);
    record("Chrome normal aberto para login Google. Feche-o ao terminar.");
  }

  async function runSearch() {
    const response = await fetch(`${AGENT_URL}/play`, { method: "POST" });
    if (!response.ok) { record("A operação diária não iniciou: já existe uma execução ou o agente está indisponível."); return; }
    setRunning(true);
    record("Operação diária completa iniciada: busca, análise, preparação e candidatura.");
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    const nextProfile = { ...profile, target_roles: roleList, skills: skillsText.split(",").map((item) => item.trim()).filter(Boolean) };
    const response = await fetch(`${AGENT_URL}/profile`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(nextProfile) });
    if (!response.ok) { setProfileMessage("Falha ao salvar o perfil."); return; }
    setProfile(await response.json() as Profile);
    setProfileMessage("Perfil salvo.");
    record("Perfil profissional atualizado.");
  }

  async function uploadResume(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setProfileMessage("Enviando currículo...");
    const response = await fetch(`${AGENT_URL}/profile/resume`, { method: "POST", body });
    if (!response.ok) { setProfileMessage("Falha ao importar currículo. Use PDF ou DOCX de até 10 MB."); return; }
    const data = await response.json() as { resume_path: string };
    setProfile((current) => ({ ...current, resume_path: data.resume_path }));
    setProfileMessage("Currículo importado com segurança.");
    record("Currículo importado.");
  }

  async function analyzeJobs() {
    const response = await fetch(`${AGENT_URL}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ minimum_score: 75, limit: 500 }) });
    if (!response.ok) { record("Falha ao analisar vagas."); return; }
    const data = await response.json() as { approved: number; review: number; ignored: number };
    record(`Análise concluída: ${data.approved} aprovadas, ${data.review} para revisão e ${data.ignored} ignoradas.`);
  }

  async function prepareApplications() {
    const response = await fetch(`${AGENT_URL}/applications/prepare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: 20 }) });
    if (!response.ok) { record("Não foi possível preparar candidaturas. Verifique perfil e currículo."); return; }
    setRunning(true);
    record("Preparação de até 20 candidaturas iniciada.");
  }

  async function scanCareerMail() {
    record("Verificando novos e-mails de processos seletivos...");
    const response = await fetch(`${AGENT_URL}/google/scan`, { method: "POST" });
    if (!response.ok) { record("Falha ao consultar o Gmail."); return; }
    const data = await response.json() as { discovered: number; items: CareerMail[] };
    setGoogleStatus((current) => ({ ...current, alerts: data.items.filter((item) => item.status === "NEW").length, last_items: data.items.slice(0, 20) }));
    record(`Gmail analisado: ${data.discovered} novos alertas relevantes.`);
  }

  async function createMailDraft(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/draft`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: messageId }) });
    if (!response.ok) { record("Não foi possível criar o rascunho seguro."); return; }
    record("Rascunho criado no Gmail para sua revisão; nenhuma mensagem foi enviada.");
    await scanCareerMail();
  }

  async function scheduleCareerEvent(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/calendar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: messageId }) });
    if (!response.ok) { record("Não foi possível criar o compromisso; confira data e horário do convite."); return; }
    record("Compromisso criado na Agenda Google com lembretes de 24 horas e 1 hora.");
    await scanCareerMail();
  }

  async function markQuestionnaireComplete(messageId: string) {
    const response = await fetch(`${AGENT_URL}/google/questionnaire/complete`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: messageId }) });
    if (!response.ok) { record("Não foi possível atualizar o questionário."); return; }
    record("Questionário marcado como concluído.");
    setGoogleStatus((current) => ({ ...current, last_items: current.last_items.map((item) => item.message_id === messageId ? { ...item, questionnaire_status: "COMPLETED_MANUALLY", status: "COMPLETED" } : item) }));
  }

  function saveSettings(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem("careeros.roles", roles);
    localStorage.setItem("careeros.location", location);
    setSaved(true);
    record("Configurações de busca atualizadas.");
    setTimeout(() => setSaved(false), 2500);
  }

  return <main className="shell">
    <aside className="sidebar">
      <h1>HelpSystem<span> Carreira</span></h1>
      <p>CareerOS · motor inteligente</p>
      <nav>{nav.map(([id, label]) => <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>{label}</button>)}</nav>
    </aside>
    <section className="content">
      <header className="topbar">
        <div><h2>{nav.find(([id]) => id === view)?.[1]}</h2><p>Decisões de carreira com automação responsável</p></div>
        <button className="danger" onClick={stopWork} disabled={!running}>PARAR AUTOMAÇÃO</button>
      </header>

      {view === "overview" && <>
        <div className="notice"><strong>Seu radar de oportunidades</strong><span>O CareerOS trabalha nos bastidores; você acompanha, aprova e controla tudo pelo HelpSystem Carreira.</span></div>
        <div className="metrics">{[["Vagas coletadas", String(jobs.length)], ["Candidaturas confirmadas", `${appliedCount} / 20`], ["Em processamento", String(pendingCount)], ["Links Gupy bloqueados", String(agent.blocked ?? 0)]].map(([label, value]) => <article key={label}><small>{label}</small><b>{value}</b></article>)}</div>
        <div className="grid two">
          <article className="panel"><h3>Começar agora</h3><p>Inicie uma sessão e escolha a plataforma. As páginas abrirão em novas abas deste mesmo Chrome, preservando seus logins existentes.</p><button className="primary" onClick={beginWork}>{running ? "Continuar trabalho" : "INICIAR TRABALHO"}</button></article>
          <article className="panel"><h3>Estado do sistema</h3><p className={agent.status === "offline" ? "danger-text" : "ok"}>● Agente: {agent.status}</p><p>{agent.message}</p><p className={aiStatus.available ? "ok" : "muted"}>● Copiloto local: {aiStatus.available ? `ativo (${aiStatus.model})` : "inicializando ou indisponível"}</p><p>Privacidade da IA: ambiente controlado</p><p>Candidaturas: modo assistido com confirmação</p><p>Gupy: bloqueada</p></article>
        </div>
      </>}

      {view === "profile" && <form className="panel form" onSubmit={saveProfile}>
        <h3>Perfil profissional obrigatório</h3>
        <p>Somente estes dados aprovados poderão ser usados nos formulários.</p>
        <label>Nome completo<input required value={profile.full_name} onChange={(event) => setProfile({ ...profile, full_name: event.target.value })} /></label>
        <label>E-mail<input required type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} /></label>
        <label>Telefone<input value={profile.phone} onChange={(event) => setProfile({ ...profile, phone: event.target.value })} /></label>
        <div className="form-row"><label>Cidade<input value={profile.city} onChange={(event) => setProfile({ ...profile, city: event.target.value })} /></label><label>Estado<input value={profile.state} onChange={(event) => setProfile({ ...profile, state: event.target.value })} /></label></div>
        <label>LinkedIn<input value={profile.linkedin_url} onChange={(event) => setProfile({ ...profile, linkedin_url: event.target.value })} /></label>
        <label>Pretensão salarial<input value={profile.salary_expectation} onChange={(event) => setProfile({ ...profile, salary_expectation: event.target.value })} /></label>
        <label>Competências, separadas por vírgula<textarea rows={5} value={skillsText} onChange={(event) => setSkillsText(event.target.value)} /></label>
        <label>Currículo PDF ou DOCX<input type="file" accept=".pdf,.docx" onChange={(event) => void uploadResume(event)} /></label>
        <p className={profile.resume_path ? "ok" : "danger-text"}>{profile.resume_path ? "Currículo importado." : "Currículo ainda não importado."}</p>
        <button className="primary" type="submit">Salvar perfil</button>
        {profileMessage && <span className="ok">{profileMessage}</span>}
      </form>}

      {view === "platforms" && <>
        <div className="notice"><strong>Acesso centralizado</strong><span>Se uma plataforma pedir login, autentique-se na aba aberta. O Chrome manterá a sessão como já faz normalmente.</span></div>
        <div className="platform-grid">{platforms.map((platform) => <article className="platform" key={platform.name}>
          <div><span className="badge">{platform.priority}</span><h3>{platform.name}</h3><p>Buscar por: <strong>{mainRole}</strong></p></div>
          <div className="actions"><button onClick={() => openPlatform(platform.name, platform.home)}>Abrir / entrar</button><button className="primary" onClick={() => openPlatform(platform.name, platform.search(mainRole))}>Buscar vagas</button></div>
        </article>)}</div>
        <div className="blocked"><strong>Gupy bloqueada</strong><span>Links para gupy.io não são oferecidos pelo HelpSystem Carreira.</span></div>
      </>}

      {view === "jobs" && <article className="panel"><div className="section-header"><h3>Vagas coletadas ({jobs.length})</h3><button className="primary" onClick={() => void analyzeJobs()}>Analisar e calcular score</button></div>{jobs.length === 0 ? <p className="muted">Execute uma busca automática para preencher esta lista.</p> : <div className="job-list">{jobs.slice().reverse().map((job) => <a key={job.url} href={job.url} target="_blank" rel="noreferrer"><span className="badge">{job.source}</span><strong>{job.title}</strong><small>{job.score !== undefined ? `${job.score}% · ${job.decision}` : `${job.search_role} · ${job.status}`}</small></a>)}</div>}</article>}
      {view === "applications" && <article className="panel"><div className="section-header"><h3>Status e feedback ({applications.length})</h3><button className="primary" onClick={() => void prepareApplications()}>Preparar até 20 qualificadas</button></div>{applications.length === 0 ? <p className="muted">Nenhuma candidatura preparada. Complete o perfil, analise as vagas e inicie a preparação.</p> : <div className="job-list">{applications.slice().sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""))).map((application) => <a key={application.id} href={application.job_url} target="_blank" rel="noreferrer"><span className="badge">{application.source}</span><strong>{application.title}</strong><small>{application.status === "APPLIED" ? "✅ Enviada e confirmada" : application.status === "CLOSED" ? "⛔ Encerrada" : application.status === "MANUAL_REQUIRED" ? "⚠️ Precisa de ação" : application.status === "FAILED" ? "❌ Falhou" : "⏳ Em processamento"} · {application.reason}</small>{application.feedback && <small>Recomendação: {application.recommendation} · {application.feedback}</small>}<small>{application.region ? `Região: ${application.region} · ` : ""}{application.salary_brl ? `Salário informado: ${application.salary_brl.toLocaleString("pt-BR", {style:"currency", currency:"BRL"})} · ` : "Salário não publicado · "}Tentativas: {application.attempts ?? 0}{application.submitted_at ? ` · Confirmada em ${new Date(application.submitted_at).toLocaleString("pt-BR")}` : ""}</small>{application.ai_answers && application.ai_answers.length > 0 && <small>IA respondeu: {application.ai_answers.map((item) => `${item.answer} (${item.evidence})`).join("; ")}</small>}</a>)}</div>}</article>}
      {view === "inbox" && <article className="panel"><div className="section-header"><div><h3>Recrutamento no Gmail</h3><p className={googleStatus.connected ? "ok" : "danger-text"}>{googleStatus.connected ? `Conectado: ${googleStatus.email} · Agenda ativa` : "Google desconectado"}</p></div><button className="primary" onClick={() => void scanCareerMail()}>VERIFICAR AGORA</button></div><p>{googleStatus.alerts} alerta(s) aguardando análise. O monitoramento automático ocorre a cada 10 minutos.</p>{googleStatus.last_items.length === 0 ? <p className="muted">Nenhum e-mail de recrutamento classificado nos últimos 30 dias.</p> : <div className="job-list">{googleStatus.last_items.map((mail) => <div className="mail-card" key={mail.message_id}><span className="badge">{mail.category}</span><strong>{mail.subject}</strong><small>{mail.sender} · {new Date(mail.received_at).toLocaleString("pt-BR")} · confiança {mail.confidence}%</small><small>{mail.reason}</small><p>{mail.snippet}</p>{mail.category === "QUESTIONNAIRE" && <><small className={mail.questionnaire_status?.startsWith("COMPLETED") ? "ok" : "danger-text"}>Questionário: {mail.questionnaire_status?.startsWith("COMPLETED") ? "concluído" : mail.questionnaire_url ? "pendente — link disponível" : "situação não confirmada — link não localizado"}</small><div className="mail-actions">{mail.questionnaire_url && !mail.questionnaire_status?.startsWith("COMPLETED") && <a className="primary" href={mail.questionnaire_url} target="_blank" rel="noreferrer">Abrir questionário</a>}{!mail.questionnaire_status?.startsWith("COMPLETED") && <button onClick={() => void markQuestionnaireComplete(mail.message_id)}>Marcar como concluído</button>}</div></>}{mail.suggested_reply && <button disabled={Boolean(mail.draft_id)} onClick={() => void createMailDraft(mail.message_id)}>{mail.draft_id ? "Rascunho criado" : "Criar rascunho no Gmail"}</button>}{mail.event_candidate && <><small>Agenda: {new Date(mail.event_candidate.start).toLocaleString("pt-BR")}</small><button disabled={Boolean(mail.calendar_event_id)} onClick={() => void scheduleCareerEvent(mail.message_id)}>{mail.calendar_event_id ? "Compromisso criado" : "Adicionar à Agenda"}</button></>}</div>)}</div>}</article>}
      {view === "automation" && <article className="panel"><h3>Agente automático</h3><p>Status: <strong className={agent.status === "offline" ? "danger-text" : "ok"}>{agent.status.toUpperCase()}</strong></p><p>{agent.message}</p>{agent.platform && <p>Agora: {agent.role} em {agent.platform}</p>}<p>Encontradas: <strong>{agent.found}</strong> · Gupy bloqueadas: <strong>{agent.blocked}</strong></p><div className="automation-actions"><button onClick={() => void openManualLogin()}>Login Google (Chrome normal)</button><button onClick={() => void beginWork()}>Retomar Chrome automático</button><button onClick={() => void openLogin()}>Abrir logins comuns</button><button className="primary" onClick={() => void runSearch()} disabled={["running","applying","preparing"].includes(agent.status)}>PLAY — FAZER TUDO AGORA</button></div><p className="muted">O Play executa busca, análise, score, preparação, preenchimento e envio seguro. CAPTCHA, MFA, testes e campos não comprovados são encaminhados para intervenção manual.</p></article>}
      {view === "settings" && <form className="panel form" onSubmit={saveSettings}><h3>Preferências de busca</h3><label>Cargos, um por linha<textarea value={roles} onChange={(event) => setRoles(event.target.value)} rows={8} /></label><label>Localização e modalidade<input value={location} onChange={(event) => setLocation(event.target.value)} /></label><label className="readonly">Meta diária<input value="20 candidaturas qualificadas" readOnly /></label><button className="primary" type="submit">Salvar configurações</button>{saved && <span className="ok">Configurações salvas.</span>}</form>}
      {view === "logs" && <article className="panel"><h3>Atividade local</h3>{logs.length === 0 ? <p className="muted">Nenhuma atividade registrada.</p> : <div className="log-list">{logs.map((entry, index) => <p key={`${entry.at}-${index}`}><time>{entry.at}</time>{entry.message}</p>)}</div>}</article>}
      {view === "security" && <article className="panel"><h3>Proteções ativas</h3><ul><li>Nenhuma senha é solicitada ou armazenada.</li><li>Login, CAPTCHA e MFA permanecem sob seu controle no Chrome.</li><li>Gupy está bloqueada.</li><li>Somente vagas com score mínimo de 75% entram no autoenvio.</li><li>Campos sem resposta comprovada interrompem a candidatura.</li></ul></article>}
    </section>
  </main>;
}
