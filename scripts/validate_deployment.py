"""Offline production validation with ephemeral credentials and no database access."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Do not inherit local database, SMTP, BBB or storage credentials.
    env = {key: os.environ[key] for key in (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
        "WEASYPRINT_DLL_DIRECTORIES",
    ) if key in os.environ}
    env.update({
        "DJANGO_SETTINGS_MODULE": "config.settings_production",
        "UFHOB_ENVIRONMENT": "production", "DEBUG": "False",
        "SECRET_KEY": secrets.token_urlsafe(60),
        "CARD_SIGNING_KEY": secrets.token_urlsafe(60),
        "BASE_URL": "https://ufhob.example.com",
        "ALLOWED_HOSTS": "ufhob.example.com",
        "CSRF_TRUSTED_ORIGINS": "https://ufhob.example.com",
        "DATABASE_URL": "postgresql://ufhob_app:offline-only@127.0.0.1:9/ufhob_db",
        "DB_SSL_REQUIRE": "False", "REDIS_URL": "redis://127.0.0.1:9/2",
        "EMAIL_HOST": "smtp.example.test", "EMAIL_HOST_USER": "offline-only",
        "EMAIL_HOST_PASSWORD": secrets.token_urlsafe(30),
        "EMAIL_USE_TLS": "True", "EMAIL_USE_SSL": "False",
        "DEFAULT_FROM_EMAIL": "noreply@example.test",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": "False", "SECURE_HSTS_PRELOAD": "False",
        "SYSTEM_SESSION_MANUAL_TEST_MODE": "False", "ONLINE_CLASSROOM_TIME_BYPASS": "False",
        "ENABLE_BROWSER_RELOAD": "False",
    })
    code = '''
from pathlib import Path
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.files.storage import storages
from django.db.backends.base.base import BaseDatabaseWrapper
from unittest.mock import patch
from django.template import engines
from django.apps import apps
from weasyprint import HTML
settings.STATIC_ROOT = settings.BASE_DIR / ".tmp-deployment-audit" / "static"
with patch.object(BaseDatabaseWrapper, "ensure_connection", side_effect=AssertionError("Database access forbidden in offline validation")):
    call_command("check", deploy=True)
    call_command("collectstatic", interactive=False, verbosity=0)
    assert storages["staticfiles"].url("public/css/main.css").startswith("/static/")
    assert storages["staticfiles"].url("app/css/main.css").startswith("/static/")
    from config.asgi import application
    assert application is not None
    errors = []
    roots = [settings.BASE_DIR / "templates"] + [Path(a.path) / "templates" for a in apps.get_app_configs() if Path(a.path).is_relative_to(settings.BASE_DIR)]
    count = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.html"):
            name = path.relative_to(root).as_posix()
            try:
                engines["django"].get_template(name)
                count += 1
            except Exception as error:
                errors.append((str(path.relative_to(settings.BASE_DIR)), type(error).__name__, str(error)))
    print("Templates compiled:", count)
    if errors:
        for error in errors:
            print("TEMPLATE ERROR:", error)
        raise SystemExit(1)
    assert HTML(string="<html><body><p>Validation UFHOB</p></body></html>").write_pdf().startswith(b"%PDF-")
    print("Production checks, static manifest, ASGI import, template compilation and PDF rendering: OK")
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
