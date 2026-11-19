from django.urls import path
from . import views

app_name = "formations"

urlpatterns = [
    path("", views.formation_list, name="list"),
    path("<slug:school_code>/<slug:slug>/", views.formation_detail, name="school_detail"),

    path("<slug:slug>/", views.formation_detail, name="detail"),
]
