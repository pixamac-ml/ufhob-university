"""Same security controls as production, on separate staging infrastructure."""

import os

from django.core.exceptions import ImproperlyConfigured

if os.getenv("UFHOB_ENVIRONMENT") != "staging":
    raise ImproperlyConfigured("Staging requires UFHOB_ENVIRONMENT=staging.")

from .settings_production import *  # noqa: E402,F403
