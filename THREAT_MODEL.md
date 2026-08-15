# Threat Model

Ativos: identidade, sessão das plataformas, currículos, respostas, histórico e evidências. Ameaças principais: vazamento local, dependência comprometida, prompt injection em descrição de vaga, formulário malicioso, redirecionamento para Gupy, submissão indevida e logs sensíveis.

Controles iniciais: loopback, secrets fora do Git, allowlist CORS, headers, autoaplicação off, Gupy bloqueada, confirmação humana, adapters isolados, trilha auditável e sanitização planejada. Criptografia local, CSP completa, autenticação local e política de retenção serão fechadas antes de dados reais.

