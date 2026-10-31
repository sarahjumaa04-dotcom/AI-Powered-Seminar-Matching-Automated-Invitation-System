import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _int_env(name, default):
    raw = os.environ.get(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "database", "app.db"))

INVITATION_DELIVERY_MODE = os.environ.get("INVITATION_DELIVERY_MODE", "local").lower()
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "sendinblue").lower()
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY") or os.environ.get("SENDINBLUE_API_KEY")
EMAIL_FROM_EMAIL = os.environ.get("EMAIL_FROM_EMAIL")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "BAU Seminar & Summit Management Team")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = _int_env("SMTP_PORT", 587)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "noreply@local")
