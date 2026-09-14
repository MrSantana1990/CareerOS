import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: { absolute: "CareerOS — Política de Privacidade" },
  description: "Como o CareerOS trata os dados de perfil profissional, autenticação e integrações opcionais do usuário.",
};

export default function PrivacyPolicy() {
  return (
    <main className="legal-shell">
      <article className="legal-card">
        <p className="eyebrow">HELPSYSTEM CARREIRA · CAREEROS</p>
        <h1>Política de Privacidade — CareerOS</h1>
        <p className="legal-updated">Última atualização: 14 de setembro de 2026</p>

        <section>
          <h2>O que é o CareerOS</h2>
          <p>
            O CareerOS é uma plataforma de apoio e automação de carreira. Ele ajuda a organizar seu perfil
            profissional, acompanhar oportunidades de vaga e preparar candidaturas — sempre como uma ferramenta de
            apoio, nunca como uma garantia de resultado. Esta política explica quais dados o CareerOS trata e por quê.
          </p>
        </section>

        <section>
          <h2>Dados fornecidos pelo usuário</h2>
          <p>Ao usar o CareerOS, você pode fornecer:</p>
          <ul>
            <li>Dados de currículo e perfil profissional: nome, e-mail, telefone, cidade/estado, resumo de carreira, habilidades, experiências e preferências de vaga (modelo de trabalho, cargos desejados).</li>
            <li>Arquivos de currículo enviados para uso nas candidaturas.</li>
            <li>Dados de conta e autenticação: e-mail e senha (login tradicional) ou identidade do Google quando você opta por &quot;Continuar com Google&quot; (nome, e-mail, foto de perfil — apenas o necessário para autenticação, nunca sua caixa de entrada).</li>
          </ul>
        </section>

        <section>
          <h2>Integrações opcionais (Google/Gmail/Calendar)</h2>
          <p>
            Você pode, de forma totalmente opcional e separada do login, conectar sua conta do Gmail e/ou Google
            Calendar para que o CareerOS ajude a identificar respostas de recrutadores e organizar entrevistas. Essa
            integração é distinta do login com Google: exige um consentimento próprio, pode ser revogada a qualquer
            momento (veja &quot;Revogação de integrações&quot; abaixo) e nunca é usada como condição para acessar o restante da
            plataforma.
          </p>
        </section>

        <section>
          <h2>Finalidade de uso dos dados</h2>
          <p>Os dados fornecidos são usados para:</p>
          <ul>
            <li>Manter seu perfil profissional e permitir a montagem de candidaturas.</li>
            <li>Buscar, analisar e classificar oportunidades de vaga compatíveis com seu perfil.</li>
            <li>Acompanhar o andamento de candidaturas e comunicações relacionadas, quando a integração de e-mail estiver conectada.</li>
            <li>Autenticar seu acesso e manter sua sessão ativa com segurança.</li>
          </ul>
        </section>

        <section>
          <h2>Armazenamento e segurança</h2>
          <p>
            Os dados de perfil e candidaturas ficam armazenados no banco de dados do serviço, em infraestrutura
            dedicada ao CareerOS. Senhas nunca são armazenadas em texto puro. Sessões são protegidas por cookies
            assinados, marcados como HttpOnly e Secure. Credenciais de integrações externas (como o token de acesso ao
            Gmail) ficam isoladas do restante da aplicação e nunca são expostas em telas, respostas de API ou
            registros de log.
          </p>
        </section>

        <section>
          <h2>Compartilhamento com terceiros</h2>
          <p>
            O CareerOS não vende dados pessoais a terceiros. Dados são compartilhados apenas quando necessário ao
            funcionamento do serviço — por exemplo, com a API do Google quando você conecta o Gmail/Calendar, ou com
            o site de uma vaga/plataforma de recrutamento quando você decide se candidatar através dela. Essas
            plataformas externas têm suas próprias políticas de privacidade, sobre as quais o CareerOS não tem
            controle.
          </p>
        </section>

        <section>
          <h2>Cookies e sessão</h2>
          <p>
            O CareerOS usa um único cookie essencial para manter sua sessão de acesso autenticada. Esse cookie não é
            usado para publicidade, rastreamento entre sites ou perfis de anúncio.
          </p>
        </section>

        <section>
          <h2>Retenção</h2>
          <p>
            Os dados de perfil e candidaturas são mantidos enquanto sua conta estiver ativa e o serviço estiver em
            uso. Se você solicitar a remoção dos seus dados (veja &quot;Contato&quot;), o pedido será tratado manualmente pela
            equipe responsável — o CareerOS ainda não possui um mecanismo de exclusão automática de conta.
          </p>
        </section>

        <section>
          <h2>Seus direitos</h2>
          <p>
            Você pode solicitar, a qualquer momento e pelo contato abaixo, acesso aos dados que o CareerOS mantém
            sobre você, correção de informações incorretas, ou a remoção do seu perfil.
          </p>
        </section>

        <section>
          <h2>Revogação de integrações</h2>
          <p>
            A conexão com Google/Gmail/Calendar pode ser revogada a qualquer momento diretamente nas configurações da
            sua Conta Google (
            <Link href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">
              myaccount.google.com/permissions
            </Link>
            ) ou solicitando a desconexão pelo contato abaixo. Revogar a integração não afeta seu login no CareerOS.
          </p>
        </section>

        <section>
          <h2>Contato</h2>
          <p>
            Dúvidas sobre esta política ou sobre seus dados podem ser enviadas para{" "}
            <a href="mailto:helpsystempro@gmail.com">helpsystempro@gmail.com</a>.
          </p>
        </section>

        <section>
          <h2>Alterações nesta política</h2>
          <p>
            Esta política pode ser atualizada conforme o CareerOS evolui. A data no topo desta página sempre reflete
            a versão mais recente.
          </p>
        </section>

        <nav className="legal-nav" aria-label="Navegação">
          <Link href="/">← Voltar para o CareerOS</Link>
          <div className="legal-footer-links">
            <Link href="/terms">Termos de Uso</Link>
          </div>
        </nav>
      </article>
    </main>
  );
}
