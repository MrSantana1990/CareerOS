/**
 * Achado real em produção: `request.url` dentro de uma Route Handler
 * (`route.ts`) rodando via `next start` self-hosted reflete o endereço de
 * bind do próprio processo Node (`0.0.0.0:3000`), NUNCA o domínio público
 * real - mesmo atrás de um proxy (Cloudflare Tunnel) que preserva
 * corretamente `Host`/`X-Forwarded-*` (confirmado testando direto contra o
 * container, sem o proxy no meio: o resultado foi idêntico). Isso é
 * diferente do Middleware, que já resolve `request.nextUrl`/`request.url`
 * corretamente sem ajuda nenhuma - o bug afeta SOMENTE Route Handlers que
 * constroem uma URL absoluta same-origin via `new URL(path, request.url)`.
 *
 * `publicUrl` centraliza a correção: nunca usar `request.url` como base
 * para uma URL same-origin dentro de uma Route Handler - usar sempre os
 * headers de proxy (o mesmo fallback que middleware.ts já usa para o seu
 * próprio redirect de HTTP->HTTPS).
 */

const FALLBACK_HOST = "carreira.helpsystempro.site";

export function publicOrigin(request: Request): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? FALLBACK_HOST;
  const protocol = request.headers.get("x-forwarded-proto") ?? "https";
  return `${protocol}://${host}`;
}

export function publicUrl(path: string, request: Request): URL {
  return new URL(path, publicOrigin(request));
}
