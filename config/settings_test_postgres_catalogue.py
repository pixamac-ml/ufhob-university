"""Disposable PostgreSQL cluster; never uses the owner's PostgreSQL service."""
from .settings_test_campaign import *

UFHOB_CATALOGUE_ISOLATED_TEST = True
DATABASES = {'default': {
    'ENGINE':'django.db.backends.postgresql',
    'NAME':'test_ufhob_catalogue_vide',
    'USER':'postgres', 'PASSWORD':'', 'HOST':'127.0.0.1', 'PORT':'55439',
    'TEST':{'NAME':'test_ufhob_catalogue_suite'},
}}
