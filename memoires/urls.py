from django.urls import path

from . import views

app_name = "memoires"

urlpatterns = [
    path("travaux-scientifiques/", views.MemoireListView.as_view(), name="liste"),
    path("travaux-scientifiques/<slug:slug>/", views.MemoireDetailView.as_view(), name="detail"),
    path("travaux-scientifiques/<slug:slug>/document/", views.servir_document, name="document"),
    path("", views.legacy_list_redirect, name="legacy_liste"),
    path("favoris/", views.favoris_liste, name="favoris"),
    path("<slug:slug>/page/<int:numero>/", views.servir_page, name="page"),
    path("<slug:slug>/favori/", views.toggle_favori, name="toggle_favori"),
    path("<slug:slug>/", views.legacy_detail_redirect, name="legacy_detail"),
]
