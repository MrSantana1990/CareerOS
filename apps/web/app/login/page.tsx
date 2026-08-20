"use client";

import { FormEvent, useState } from "react";

export default function Login() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setMessage("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); setMessage(data.message ?? "Não foi possível entrar."); setLoading(false); return; }
    const next = new URLSearchParams(window.location.search).get("next");
    window.location.assign(next?.startsWith("/") ? next : "/");
  }
  return <main className="login-shell"><section className="login-card"><div className="login-brand">H</div><p className="eyebrow">HELPSYSTEM CARREIRA</p><h1>Acesso ao portal</h1><p>Entre com sua conta administrativa para continuar.</p><form onSubmit={submit}><label>E-mail<input name="email" type="email" autoComplete="username" required /></label><label>Senha<input name="password" type="password" autoComplete="current-password" required /></label>{message && <div className="login-error" role="alert">{message}</div>}<button type="submit" disabled={loading}>{loading ? "Verificando…" : "Entrar com segurança"}</button></form><small>Sessão protegida e válida por até 8 horas.</small></section></main>;
}
