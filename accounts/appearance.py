"""Persist the authenticated application's appearance independently of other settings."""

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.models import UserPreference


@login_required
@require_POST
@never_cache
def update_appearance(request):
    theme = request.POST.get("theme", "").upper()
    font_scale = request.POST.get("font_scale", "").upper()
    valid_themes = {choice for choice, _ in UserPreference.THEME_CHOICES}
    valid_scales = {choice for choice, _ in UserPreference.FONT_SCALE_CHOICES}
    if theme not in valid_themes or font_scale not in valid_scales:
        response = HttpResponseBadRequest("Préférence d'affichage invalide.")
        response["HX-Trigger"] = json.dumps({
            "ui:toast": {"message": "Préférence d'affichage invalide.", "tone": "danger"}
        }, ensure_ascii=False)
        return response

    preference, _ = UserPreference.objects.get_or_create(user=request.user)
    preference.theme = theme
    preference.font_scale = font_scale
    preference.save(update_fields=["theme", "font_scale", "updated_at"])

    if request.headers.get("HX-Request") != "true":
        return redirect("accounts:edit_preferences")
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "account:preferences-updated": {"theme": theme, "font_scale": font_scale},
        "ui:toast": {"message": "Préférence d'affichage enregistrée.", "tone": "success"},
    }, ensure_ascii=False)
    return response
