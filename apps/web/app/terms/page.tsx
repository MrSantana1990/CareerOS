import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: { absolute: "CareerOS — Termos de Uso" },
  description: "Condições de uso da plataforma de apoio e automação de carreira CareerOS.",
};

export default function TermsOfService() {
  return (
    <main className="legal-shell">
      <article className="legal-card">
        <p className="eyebrow">HELPSYSTEM CARREIRA · CAREEROS</p>
        <h1>Termos de Uso — CareerOS</h1>
        <p className="legal-updated">Última atualização: 14 de setembro de 2026</p>

        <section>
          <h2>Natureza do serviço</h2>
          <p>
            O CareerOS é uma plataforma de apoio e automação de carreira. Ele ajuda a organizar seu perfil
            profissional, descobrir oportunidades e preparar candidaturas. O CareerOS não garante contratação,
            entrevista ou resposta de qualquer empresa — é uma ferramenta de apoio à sua busca, não um serviço de
            colocação de emprego.
          </p>
        </section>

        <section>
          <h2>Uso permitido</h2>
          <p>
            O acesso ao CareerOS é pessoal. Você concorda em usá-lo apenas para gerenciar sua própria carreira e
            candidaturas, e não para fins abusivos, fraudulentos ou que violem os termos de uso de terceiros
            (plataformas de vagas, provedores de e-mail, redes profissionais, etc.).
          </p>
        </section>

        <section>
          <h2>Responsabilidade sobre os dados fornecidos</h2>
          <p>
            Você é responsável pela exatidão das informações de currículo e perfil profissional que fornece ao
            CareerOS. O sistema usa essas informações para buscar vagas compatíveis e preparar candidaturas em seu
            nome — informações incorretas ou desatualizadas podem afetar a qualidade dos resultados.
          </p>
        </section>

        <section>
          <h2>Automação assistida e seus limites</h2>
          <p>
            O CareerOS automatiza tarefas de apoio — como buscar vagas, organizar informações e preparar candidaturas
            — mas etapas sensíveis dependem de aprovação humana antes de qualquer envio. O envio de candidaturas em
            massa ou totalmente automático não ocorre sem configuração e autorização explícitas. O CareerOS nunca
            contorna CAPTCHA, autenticação multifator (MFA) ou qualquer outro mecanismo de segurança de terceiros —
            quando esses mecanismos aparecem, a ação é interrompida e devolvida para você concluir manualmente.
          </p>
        </section>

        <section>
          <h2>Nenhuma garantia de contratação</h2>
          <p>
            O uso do CareerOS não garante entrevistas, propostas ou contratação. Os resultados dependem de fatores
            fora do controle da plataforma, incluindo decisões de terceiros (empresas, recrutadores) e a
            disponibilidade real de vagas.
          </p>
        </section>

        <section>
          <h2>Dependência de plataformas externas</h2>
          <p>
            O funcionamento do CareerOS depende de serviços de terceiros — sites de vagas, sistemas de recrutamento
            (ATS), provedores de e-mail e serviços de identidade como o Google. Mudanças, instabilidades ou
            indisponibilidade nessas plataformas externas podem afetar o funcionamento do CareerOS, sem que isso
            represente uma falha do serviço.
          </p>
        </section>

        <section>
          <h2>Disponibilidade do serviço</h2>
          <p>
            O CareerOS é operado em regime de melhor esforço. Não garantimos disponibilidade ininterrupta (100%) —
            manutenções, atualizações ou instabilidades técnicas podem causar indisponibilidade temporária.
          </p>
        </section>

        <section>
          <h2>Uso proibido</h2>
          <p>
            É proibido usar o CareerOS para tentar acessar contas de terceiros sem autorização, sobrecarregar
            deliberadamente sistemas externos, contornar controles de segurança, ou qualquer outro uso que viole a
            lei ou os termos de serviços de terceiros integrados.
          </p>
        </section>

        <section>
          <h2>Suspensão e encerramento</h2>
          <p>
            O acesso ao CareerOS pode ser suspenso ou encerrado em caso de uso abusivo, violação destes termos, ou a
            pedido do próprio usuário.
          </p>
        </section>

        <section>
          <h2>Marcas de terceiros</h2>
          <p>
            Google, Gmail, Google Calendar, LinkedIn, InfoJobs, Gupy e quaisquer outras marcas ou plataformas
            mencionadas pertencem aos seus respectivos titulares. O CareerOS não possui vínculo, parceria ou
            endosso oficial de nenhuma dessas empresas — a integração descrita é feita através de mecanismos
            públicos e oficiais de autenticação/API oferecidos por cada plataforma.
          </p>
        </section>

        <section>
          <h2>Alterações nestes termos</h2>
          <p>
            Estes termos podem ser atualizados conforme o CareerOS evolui. A data no topo desta página sempre
            reflete a versão mais recente.
          </p>
        </section>

        <section>
          <h2>Privacidade</h2>
          <p>
            O tratamento de dados pessoais é descrito em detalhes na nossa{" "}
            <Link href="/privacy">Política de Privacidade</Link>.
          </p>
        </section>

        <section>
          <h2>Contato</h2>
          <p>
            Dúvidas sobre estes termos podem ser enviadas para{" "}
            <a href="mailto:helpsystempro@gmail.com">helpsystempro@gmail.com</a>.
          </p>
        </section>

        <nav className="legal-nav" aria-label="Navegação">
          <Link href="/">← Voltar para o CareerOS</Link>
          <div className="legal-footer-links">
            <Link href="/privacy">Política de Privacidade</Link>
          </div>
        </nav>
      </article>
    </main>
  );
}
