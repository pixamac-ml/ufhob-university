"""Bounded first-party campaign attribution for the existing admission tunnel."""
from urllib.parse import urlencode

from django.urls import reverse

UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def capture_tracking(request):
    source = request.POST if request.method == "POST" else request.GET
    supplied = {key: source.get(key, "")[:255].strip() for key in UTM_KEYS if key in source}
    # A new tagged visit replaces old attribution; ordinary navigation preserves it.
    if supplied and any(supplied.values()):
        request.session["admission_campaign_tracking"] = supplied
    return {key: str(value)[:255] for key, value in request.session.get("admission_campaign_tracking", {}).items() if key in UTM_KEYS}


def admission_url(request, programme):
    return reverse("admissions:admission_tunnel") + "?" + urlencode({"formation": programme.slug, **capture_tracking(request)})


def tracked_redirect_url(request, url):
    tracking = capture_tracking(request)
    return url + ("&" if "?" in url else "?") + urlencode(tracking) if tracking else url
