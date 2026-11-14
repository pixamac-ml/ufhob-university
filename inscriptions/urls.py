# inscriptions/urls.py

from django.urls import path
from .views import inscription_contact_administration, inscription_public_detail

app_name = "inscriptions"

urlpatterns = [
    path(
        "dossier/<str:token>/",
        inscription_public_detail,
        name="public_detail"
    ),
    path("dossier/<str:token>/contact/", inscription_contact_administration, name="contact_administration"),
]
