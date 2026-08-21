"use client";

import { FormEvent, useEffect, useState } from "react";

export default function Login() {
  const [mode, setMode] = useState<"login" | "recovery">("login");
  const [step, setStep] = useState<"request" | "verify">("request");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState("");
  const [cookiesAccepted, setCookiesAccepted] = useState(false);
  useEffect(() => {
    if (window.location.protocol === "http:") { window.location.replace(`https://${window.location.host}${window.location.pathname}${window.location.search}`); return; }
    setCookiesAccepted(localStorage.getItem("careeros.essential-cookie") === "accepted");
  }, []);
  function acceptCookies() { localStorage.setItem("careeros.essential-cookie", "accepted"); setCookiesAccepted(true); setMessage(""); }
  function enterPortal() { const next = new URLSearchParams(window.location.search).get("next"); window.location.assign(next?.startsWith("/") ? next : "/"); }
  async function confirmSession() { const session = await fetch("/api/auth/session", { cache: "no-store", credentials: "same-origin" }); if (!session.ok) throw new Error("session-cookie"); enterPortal(); }
  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!cookiesAccepted) { setMessage("Aceite o cookie essencial para manter sua sessão no celular."); return; } setLoading(true); setMessage(""); const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); setMessage(data.message ?? "Não foi possível entrar."); setLoading(false); return; }
    try { await confirmSession(); } catch { setMessage("A senha foi aceita, mas o navegador bloqueou a sessão. Ative cookies para este site e tente novamente."); setLoading(false); }
  }
  async function requestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!cookiesAccepted) { setMessage("Aceite o cookie essencial antes de recuperar o acesso."); return; } setLoading(true); setMessage(""); setCode("");
    const response = await fetch("/api/auth/recovery/request", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email }) });
    const data = await response.json().catch(() => ({})); setMessage(data.message ?? "Não foi possível solicitar o código."); if (response.ok) setStep("verify"); setLoading(false);
  }
  async function verifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!cookiesAccepted) { setMessage("Aceite o cookie essencial para concluir o acesso."); return; } setLoading(true); setMessage("");
    const response = await fetch("/api/auth/recovery/verify", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, code }) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); setMessage(data.message ?? "Código inválido."); setLoading(false); return; }
    try { await confirmSession(); } catch { setMessage("O código foi aceito, mas o navegador bloqueou a sessão. Ative cookies e tente novamente."); setLoading(false); }
  }
  return <main className="login-shell"><section className="login-card"><div className="login-brand">H</div><p className="eyebrow">HELPSYSTEM CARREIRA</p><h1>{mode === "login" ? "Acesso ao portal" : "Recuperar acesso"}</h1><p>{mode === "login" ? "Entre com sua conta administrativa para continuar." : "Receba um código no e-mail administrativo e continue nesta tela."}</p>{!cookiesAccepted && <div className="cookie-consent" role="region" aria-label="Cookie essencial"><div><strong>Cookie essencial de acesso</strong><p>Precisamos salvar somente a sessão segura para manter você conectado. Não usamos este cookie para anúncios.</p></div><button type="button" onClick={acceptCookies}>Aceitar e continuar</button></div>}
    {mode === "login" ? <form onSubmit={submitLogin}><label>E-mail<input name="email" type="email" inputMode="email" autoCapitalize="none" autoCorrect="off" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Senha<div className="password-field"><input name="password" type={showPassword ? "text" : "password"} autoCapitalize="none" autoCorrect="off" autoComplete="current-password" required /><button type="button" className="password-toggle" onClick={() => setShowPassword((current) => !current)}>{showPassword ? "Ocultar" : "Mostrar"}</button></div></label>{message && <div className="login-error" role="alert">{message}</div>}<button type="submit" disabled={loading}>{loading ? "Verificando…" : "Entrar com segurança"}</button><button type="button" className="login-link" onClick={() => { setMode("recovery"); setMessage(""); }}>Esqueci minha senha</button></form>
    : step === "request" ? <form onSubmit={requestCode}><label>E-mail cadastrado<input type="email" inputMode="email" autoCapitalize="none" autoCorrect="off" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>{message && <div className="login-error" role="status">{message}</div>}<button type="submit" disabled={loading}>{loading ? "Solicitando…" : "Enviar código"}</button><button type="button" className="login-link" onClick={() => { setMode("login"); setMessage(""); }}>Voltar para senha</button></form>
    : <form key="recovery-code-form" onSubmit={verifyCode}><label>Código recebido<input key="recovery-code" name="recovery_access_code" type="text" inputMode="text" autoCapitalize="characters" autoCorrect="off" autoComplete="off" value={code} onChange={(event) => setCode(event.target.value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 8))} placeholder="Ex.: AB12CD34" minLength={8} maxLength={8} autoFocus required /></label><small className="field-hint">O e-mail permanece salvo acima; este campo começa vazio e aceita somente o código.</small>{message && <div className="login-error" role="status">{message}</div>}<button type="submit" disabled={loading}>{loading ? "Validando…" : "Entrar com o código"}</button><button type="button" className="login-link" onClick={() => { setStep("request"); setCode(""); setMessage(""); }}>Solicitar outro código</button></form>}
    <small>Sessão protegida e válida por até 8 horas.</small></section></main>;
}
