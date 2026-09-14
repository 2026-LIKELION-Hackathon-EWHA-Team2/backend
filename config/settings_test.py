"""Isolated settings for local tests and CI; never use for deployment."""

import os
from unittest.mock import patch

# Import-time API clients use dummy credentials and cannot reach the real API.
os.environ['OPENAI_API_KEY'] = 'ci-placeholder-not-a-real-key'
os.environ['OPENAI_BASE_URL'] = 'http://127.0.0.1:9/v1'

# Import the application's settings without loading .env or production services.
with patch.dict(os.environ, {
    "APP_ENV": "development",
    "DEBUG": "false",
    "SECRET_KEY": "django-ci-only-key-not-for-production-use",
    "DATABASE_URL": "",
    "RENDER": "",
    "RENDER_EXTERNAL_HOSTNAME": "",
    "CLOUDINARY_URL": "",
    "CLOUDINARY_CLOUD_NAME": "",
    "CLOUDINARY_API_KEY": "",
    "CLOUDINARY_API_SECRET": "",
}), patch("dotenv.load_dotenv"):
    from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}