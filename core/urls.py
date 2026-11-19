# core/urls.py

from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView
from . import views
from . import public_views
from .public_faq import faq
from memoires import views as memoire_views


app_name = "core"

urlpatterns = [

    # =====================================================
    # PUBLIC PAGES
    # =====================================================

    path("", views.home, name="home"),
    path("apropos/", views.about, name="about"),
    path("faq/", faq, name="faq"),
    path("universite/", public_views.university, name="university"),
    path("contact/", views.contact_view, name="contact"),
    # School codes are configurable institutional data and may contain accents.
    # ``str`` still excludes slashes while accepting every code stored in DB.
    path("ecoles/<str:code>/", public_views.school_detail, name="school_detail"),
    path("campus-vie-universitaire/", public_views.campus_life, name="campus_life"),
    path("campus/<slug:slug>/", public_views.campus_detail, name="campus_detail"),
    path("recherche-innovation/", public_views.research_innovation, name="research_innovation"),
    path("recherche/", RedirectView.as_view(pattern_name="core:research_innovation", permanent=True), name="research_alias"),
    path("recherche/travaux/", memoire_views.MemoireListView.as_view(), name="research_catalogue"),
    path("travaux-scientifiques/", memoire_views.MemoireListView.as_view(), name="scientific_work_list"),
    path("memoires/", memoire_views.MemoirePublicListView.as_view(), name="memoires"),
    path("theses/", memoire_views.ThesePublicListView.as_view(), name="theses"),
    path("travaux-scientifiques/<slug:slug>/", memoire_views.MemoireDetailView.as_view(), name="scientific_work_detail"),
    path("travaux-scientifiques/<slug:slug>/document/", memoire_views.servir_document, name="scientific_work_document"),
    path("plan-du-site/", views.sitemap, name="sitemap"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("cookies/consent/", views.set_cookie_preferences, name="cookie_consent"),


    # =====================================================
    # LEGAL PAGES
    # =====================================================

    path("mentions-legales/", views.legal_notice, name="legal_notice"),
    path("confidentialite/", views.privacy_policy, name="privacy_policy"),
    path("conditions-utilisation/", views.terms_of_service, name="terms_of_service"),

    path(
        "legal/<str:page_type>/pdf/",
        views.legal_page_pdf,
        name="legal_pdf"
    ),


    # =====================================================
    # INTERNAL / SUPERADMIN
    # =====================================================


]

if settings.DEBUG:
    urlpatterns.append(
        path("erreurs/<int:error_code>/", views.preview_error_page, name="error_page_preview"),
    )
