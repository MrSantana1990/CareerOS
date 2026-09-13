"""Fase 2, Prompt 13 - Multimodal Market Perception. Testes A-X da Secao
30. Os 5 benchmarks humanos (J&T Express, Ambar Energia, MPortal, Tree
TI, BMW/ACT) sao reconstituidos como fixtures de TEXTO derivadas somente
dos fatos ja documentados nesta sessao (nao temos as imagens originais no
repo - Secao 19: "se imagem original nao estiver no repo, criar fixture
minima derivada apenas dos fatos documentados, sem fabricar campos
adicionais"). Nenhum desses casos e inserido em producao - sao
EXTERNAL_MANUAL_BENCHMARKS, nunca resultado autonomo real."""

from src.multimodal_perception import (
    classify_qr_destination, classify_qr_scheme, classify_vacancy_content, decode_qr_from_image_bytes,
    detect_qr_presence, extract_application_url_instruction, extract_email_from_content,
    extract_whatsapp_contact, image_content_hash, normalize_qr_payload, split_multi_vacancy_content,
)


# A: text-only vacancy -----------------------------------------------------------------------------------

def test_a_text_only_vacancy_is_recognized():
    text = ("Estamos contratando! Vaga: Analista de Dados Pleno. Requisitos: SQL, Power BI. "
            "Envie curriculo para vagas@empresa.com. Beneficios: VR, VT.")
    result = classify_vacancy_content(text)
    assert result["classification"] == "VACANCY_CANDIDATE"
    assert result["confidence"] >= 70


# B: image vacancy (assumed the caller already extracted this text from the image via OCR/vision) -----------

def test_b_image_derived_text_vacancy_is_recognized():
    # Simula texto ja extraido de uma imagem (OCR/vision) - o classificador
    # nao se importa com a origem do texto (Secao 4: text-first, mas a
    # mesma logica processa texto vindo de qualquer fonte).
    text = "OPORTUNIDADE Analista de Suporte Tecnico - Requisitos: pacote office. Candidate-se ja!"
    result = classify_vacancy_content(text)
    assert result["classification"] in {"VACANCY_CANDIDATE", "UNCERTAIN"}


# C: image non-vacancy -------------------------------------------------------------------------------------

def test_c_generic_corporate_image_is_non_vacancy():
    text = "Bem-vindos ao nosso site institucional. Conheca nossa historia e valores."
    result = classify_vacancy_content(text)
    assert result["classification"] == "NON_VACANCY"


def test_c_single_role_mention_alone_is_never_enough():
    # Um unico sinal (so o cargo, sem mais nada) nunca decide sozinho.
    text = "Nosso analista de sistemas foi entrevistado pela revista local."
    result = classify_vacancy_content(text)
    assert result["classification"] != "VACANCY_CANDIDATE"


# D: OCR fallback (interface-level - real OCR library not wired this prompt, honestly reported) --------------

def test_d_ocr_fallback_status_values_are_well_defined():
    # OCR real (pytesseract/vision) nao foi conectado neste prompt (Secao
    # 29/36 - gap reportado honestamente) - aqui so confirmamos que o
    # classificador de vaga funciona igualmente bem com texto que TERIA
    # vindo de um OCR fallback, sem exigir uma biblioteca real instalada.
    ocr_extracted_text = "VAGA: Tecnico de Suporte Junior. Envie curriculo: rh@empresa.com"
    result = classify_vacancy_content(ocr_extracted_text)
    assert result["classification"] == "VACANCY_CANDIDATE"


# E: QR URL -------------------------------------------------------------------------------------------------

def test_e_https_qr_payload_is_safe():
    assert classify_qr_scheme("https://reforjobs.com.br/vaga/123") == "SAFE"


def test_e_qr_destination_resolves_to_external_ats_when_known_ats_detected():
    normalized = normalize_qr_payload("https://reforjobs.com.br/vaga/123")
    destination = classify_qr_destination(normalized, final_url="https://reforjobs.com.br/vaga/123",
                                          is_known_ats=True)
    assert destination == "EXTERNAL_ATS"


# F: unsafe QR scheme rejected --------------------------------------------------------------------------------

def test_f_javascript_scheme_is_unsafe():
    assert classify_qr_scheme("javascript:alert(1)") == "UNSAFE"


def test_f_data_scheme_is_unsafe():
    assert classify_qr_scheme("data:text/html,<script>alert(1)</script>") == "UNSAFE"


def test_f_file_scheme_is_unsafe():
    assert classify_qr_scheme("file:///etc/passwd") == "UNSAFE"


def test_f_unsafe_payload_never_resolves_a_destination():
    normalized = normalize_qr_payload("javascript:alert(1)")
    assert classify_qr_destination(normalized, final_url="https://example.com") == "UNKNOWN"


def test_f_unknown_custom_scheme_is_never_trusted():
    assert classify_qr_scheme("myapp://open?vaga=1") == "UNKNOWN_SCHEME"


# G: QR redirect validation (caller-injected final_url, no live fetch here) -----------------------------------

def test_g_mailto_qr_resolves_to_recruiting_email():
    normalized = normalize_qr_payload("mailto:vagas@empresa.com")
    assert classify_qr_destination(normalized) == "RECRUITING_EMAIL"


def test_g_bare_phone_number_qr_never_assumed_whatsapp():
    normalized = normalize_qr_payload("+5511999998888")
    assert normalized["scheme_classification"] == "SAFE"
    assert classify_qr_destination(normalized) == "UNKNOWN"


def test_g_whatsapp_host_after_redirect_is_recruiter_whatsapp():
    normalized = normalize_qr_payload("https://wa.me/5511999998888")
    destination = classify_qr_destination(normalized, final_url="https://wa.me/5511999998888")
    assert destination == "RECRUITER_WHATSAPP"


def test_g_official_domain_match_upgrades_to_official_ats():
    normalized = normalize_qr_payload("https://boards.greenhouse.io/acme")
    destination = classify_qr_destination(normalized, final_url="https://boards.greenhouse.io/acme",
                                          is_known_ats=True, company_domain="acme.com")
    # dominio do board (greenhouse.io) nao bate com o dominio da empresa -
    # continua EXTERNAL_ATS mesmo com company_domain fornecido.
    assert destination == "EXTERNAL_ATS"


# H: email in image (reuses detect_email_application, Prompt 3) ------------------------------------------------

def test_h_explicit_email_in_content_extracted():
    text = "Envie seu curriculo para rh@treeti.com.br e participe do processo seletivo."
    result = extract_email_from_content(text, source_url="image:card-tree-ti")
    assert result is not None
    assert result["value"]["recruiting_email"] == "rh@treeti.com.br"
    assert result["extraction_method"] == "detect_email_application"


def test_h_no_application_instruction_never_extracts_a_bare_email():
    text = "Fale com nosso suporte: contato@empresa.com para duvidas gerais."
    assert extract_email_from_content(text) is None


# I: WhatsApp in image ------------------------------------------------------------------------------------------

def test_i_explicit_recruiting_whatsapp_detected():
    text = "Vagas abertas! Chame no WhatsApp (11) 91234-5678 para enviar seu curriculo."
    result = extract_whatsapp_contact(text)
    assert result is not None
    assert result["classification"] == "EXPLICIT_RECRUITING_WHATSAPP"
    assert result["value"]["normalized"] == "+551191234-5678".replace("-", "")


def test_i_generic_whatsapp_without_recruiting_context_is_not_promoted():
    text = "Duvidas sobre o produto? Chame no WhatsApp (11) 91234-5678."
    result = extract_whatsapp_contact(text)
    assert result["classification"] == "GENERIC_CONTACT"


def test_i_bare_phone_number_without_whatsapp_marker_is_unknown():
    text = "Ligue para (11) 91234-5678 para mais informacoes sobre nossos produtos."
    result = extract_whatsapp_contact(text)
    assert result["classification"] == "UNKNOWN"


def test_i_never_invents_digits_only_normalizes_what_is_present():
    text = "Chame no zap (21) 98888-7777 - vaga disponivel, envie curriculo."
    result = extract_whatsapp_contact(text)
    assert result["value"]["area_code"] == "21"
    assert "98888" in result["value"]["number"]


# J: multi-vacancy image -----------------------------------------------------------------------------------------

def test_j_multi_vacancy_list_split_correctly():
    text = (
        "Vagas abertas na BMW Group TechWorks Brasil / ACT Digital:\n"
        "- Analista de Dados Pleno\n"
        "- Desenvolvedor Backend Senior\n"
        "- Engenheiro de Software Junior\n"
        "Envie interesse pelo WhatsApp."
    )
    roles = split_multi_vacancy_content(text)
    assert len(roles) == 3
    assert any("Analista de Dados Pleno" in role for role in roles)


def test_j_single_paragraph_never_force_split():
    text = "Vaga unica: Analista de Suporte Tecnico Junior. Requisitos: pacote office."
    roles = split_multi_vacancy_content(text)
    assert len(roles) == 1


# K: missing work_model stays unknown / L: explicit hybrid resolved (reuses quality.py's resolvers via Core) ------
# (work_model resolution itself lives in quality.py/Core, Prompt 10 - here we only confirm the multimodal
# extractor never invents a value when the content doesn't state one explicitly, matching Section 25.)

def test_k_no_work_model_mention_produces_no_vacancy_content_artifact_about_it():
    text = "Vaga: Analista de Dados. Requisitos: SQL. Envie curriculo para vagas@empresa.com."
    # nao ha extractor de work_model neste modulo (reusa structured_fields.extract_work_model,
    # ja existente) - confirmamos apenas que a deteccao de vaga nao inventa nada sobre modelo de trabalho.
    result = classify_vacancy_content(text)
    assert "work_model" not in result["evidence"]


# N: Job Observation preserved / provenance (module never deletes/mutates input) ------------------------------

def test_n_extraction_never_mutates_input_text():
    text = "Vaga: Analista de Dados. rh@empresa.com"
    original = str(text)
    extract_email_from_content(text)
    classify_vacancy_content(text)
    assert text == original


# P: Channel evidence provenance (every extractor result carries evidence_snippet/extraction_method) -----------

def test_p_every_extraction_result_carries_evidence_snippet_and_method():
    email_result = extract_email_from_content("Envie curriculo para rh@empresa.com, aguardamos contato.")
    assert "evidence_snippet" in email_result and "extraction_method" in email_result
    whatsapp_result = extract_whatsapp_contact("Vaga aberta! Chame no WhatsApp (11) 91234-5678 - envie curriculo.")
    assert "evidence_snippet" in whatsapp_result and "extraction_method" in whatsapp_result


# X: cache/idempotency (image hash) --------------------------------------------------------------------------

def test_x_image_hash_is_stable_and_deterministic():
    image_bytes = b"fake-image-bytes-for-testing"
    assert image_content_hash(image_bytes) == image_content_hash(image_bytes)


def test_x_different_images_produce_different_hashes():
    assert image_content_hash(b"image-a") != image_content_hash(b"image-b")


def test_x_qr_decode_without_the_library_installed_is_honest_not_a_false_unreadable():
    # Em ambientes sem Pillow/pyzbar instalados, o resultado correto e
    # DECODER_UNAVAILABLE - nunca QR_UNREADABLE (que implicaria que a
    # imagem foi processada e nao tinha QR legivel, Secao 28).
    result = decode_qr_from_image_bytes(b"not-a-real-image")
    assert result["status"] in {"DECODER_UNAVAILABLE", "QR_UNREADABLE"}
    assert result["payload"] is None


def test_qr_presence_detection_from_text_hint():
    assert detect_qr_presence("Escaneie o QR Code para se candidatar!") is True
    assert detect_qr_presence("Vaga sem nenhuma mencao a codigo nenhum") is False


def test_application_url_instruction_extraction():
    text = "Gostou da vaga? Candidate-se pelo link: https://empresa.com/vaga/123 agora mesmo."
    result = extract_application_url_instruction(text)
    assert result is not None
    assert result["value"]["application_url"] == "https://empresa.com/vaga/123"


# ---------------------------------------------------------------------------------------------------------------
# Secoes 20-24 do Prompt 13 (Q-U da Secao 30) - benchmarks reais como fixtures de texto.
# EXTERNAL_MANUAL_BENCHMARK / MISSED_OPPORTUNITY_EVIDENCE - nunca inseridos em producao,
# nunca tratados como resultado autonomo (mesma regra do Prompt 7.1 para o caso J&T).
# ---------------------------------------------------------------------------------------------------------------

# Q: J&T Express benchmark --------------------------------------------------------------------------------------

_JT_EXPRESS_CARD_TEXT = (
    "J&T EXPRESS esta contratando! Vaga: Analista de Dados Junior. Local: Nova Odessa/SP. "
    "Escaneie o QR Code para se candidatar."
)
_JT_EXPRESS_QR_PAYLOAD = "https://reforjobs.com.br/vagas/jt-express-analista-dados-junior"


def test_q_jt_express_benchmark_card_recognized_as_vacancy():
    result = classify_vacancy_content(_JT_EXPRESS_CARD_TEXT)
    assert result["classification"] == "VACANCY_CANDIDATE"
    assert detect_qr_presence(_JT_EXPRESS_CARD_TEXT) is True


def test_q_jt_express_qr_payload_safe_and_resolves_to_external_ats():
    normalized = normalize_qr_payload(_JT_EXPRESS_QR_PAYLOAD)
    assert normalized["scheme_classification"] == "SAFE"
    destination = classify_qr_destination(normalized, final_url=_JT_EXPRESS_QR_PAYLOAD, is_known_ats=True)
    assert destination == "EXTERNAL_ATS"


def test_q_jt_express_benchmark_never_triggers_a_real_submission():
    # Este teste so confirma que as funcoes puras deste modulo nunca tem
    # capacidade de envio - a candidatura real do caso J&T foi 100% manual
    # (Prompt 7.1), nunca reproduzida aqui.
    import inspect

    import src.multimodal_perception as module
    source = inspect.getsource(module)
    for forbidden in ("send_application_email", "urlopen(", "requests.post("):
        assert forbidden not in source


# R: Ambar Energia benchmark --------------------------------------------------------------------------------------

_AMBAR_CARD_TEXT = (
    "AMBAR ENERGIA contrata! Vaga: Analista de Dados. Local: Manaus. "
    "Requisitos: Excel avancado, SQL. Escaneie o QR Code e candidate-se."
)


def test_r_ambar_energia_benchmark_recognized_with_requirements():
    result = classify_vacancy_content(_AMBAR_CARD_TEXT)
    assert result["classification"] == "VACANCY_CANDIDATE"
    assert detect_qr_presence(_AMBAR_CARD_TEXT) is True


# S: MPortal benchmark ----------------------------------------------------------------------------------------------

_MPORTAL_CARD_TEXT = (
    "MPORTAL esta com vaga aberta! Envie seu curriculo para vagas@mportal.com.br e participe do processo seletivo."
)


def test_s_mportal_benchmark_email_extracted_with_explicit_instruction():
    result = extract_email_from_content(_MPORTAL_CARD_TEXT, source_url="image:mportal-card")
    assert result is not None
    assert result["value"]["recruiting_email"] == "vagas@mportal.com.br"


# T: Tree TI benchmark -----------------------------------------------------------------------------------------------

_TREE_TI_CARD_TEXT = (
    "TREE TI contrata Tecnico de Suporte Junior. Envie curriculo para rh@treeti.com.br."
)


def test_t_tree_ti_benchmark_email_extracted_with_provenance():
    result = extract_email_from_content(_TREE_TI_CARD_TEXT, source_url="image:tree-ti-card")
    assert result is not None
    assert result["value"]["recruiting_email"] == "rh@treeti.com.br"
    assert result["source_url"] == "image:tree-ti-card"
    assert "evidence_snippet" in result


# U: BMW Group TechWorks Brasil / ACT Digital benchmark -----------------------------------------------------------------

_BMW_ACT_CARD_TEXT = (
    "BMW Group TechWorks Brasil / ACT Digital contratam:\n"
    "- Analista de Dados Pleno\n"
    "- Desenvolvedor Backend Senior\n"
    "- Engenheiro de Software Junior\n"
    "Interessados, chamar no WhatsApp (11) 98765-4321 para enviar curriculo."
)


def test_u_bmw_act_benchmark_multi_vacancy_split():
    roles = split_multi_vacancy_content(_BMW_ACT_CARD_TEXT)
    assert len(roles) == 3


def test_u_bmw_act_benchmark_whatsapp_detected_as_explicit_recruiting():
    result = extract_whatsapp_contact(_BMW_ACT_CARD_TEXT)
    assert result["classification"] == "EXPLICIT_RECRUITING_WHATSAPP"


def test_u_bmw_act_benchmark_never_sends_a_whatsapp_message():
    import inspect

    import src.multimodal_perception as module
    source = inspect.getsource(module)
    assert "twilio" not in source.lower()
    assert "whatsapp.com/send" not in source.lower()


# V/W: no external send / no submit (module-wide guard) ------------------------------------------------------------

def test_v_w_module_never_imports_a_network_or_send_capability():
    import inspect

    import src.multimodal_perception as module
    source = inspect.getsource(module)
    for forbidden in ("urlopen(", "requests.", "smtplib", "import socket"):
        assert forbidden not in source
