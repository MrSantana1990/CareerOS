from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


ROOT = Path(__file__).resolve().parents[1]
GOOGLE_DIR = ROOT / ".runtime" / "google"
CREDENTIALS = GOOGLE_DIR / "google-credentials.json"
TOKEN = GOOGLE_DIR / "google-token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


def main() -> None:
    if not CREDENTIALS.exists():
        raise SystemExit(f"Credencial não encontrada: {CREDENTIALS}")
    GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        authorization_prompt_message="Autorize o CareerOS na janela do Google.",
        success_message="CareerOS autorizado. Você pode fechar esta janela e voltar ao painel.",
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )
    TOKEN.write_text(credentials.to_json(), encoding="utf-8")
    print("GOOGLE_AUTHORIZED")


if __name__ == "__main__":
    main()
