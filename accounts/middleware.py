import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from accounts.access_context import get_request_access_context
from accounts.shadow_access import compare_access_classification
from accounts.session_policy import (
    SESSION_ID_KEY,
    close_session_record,
    initialize_system_session,
    record_meaningful_activity,
    session_deadline_state,
)
from accounts.models import AccountSecurityEvent, AccountSessionRecord


logger = logging.getLogger("accounts.access_shadow")


class AccessContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.access_context = SimpleLazyObject(
            lambda: get_request_access_context(request)
        )
        from accounts.scoping import access_scope

        with access_scope(request.access_context):
            response = self.get_response(request)
        if (
            settings.AUTH_POLICY_V2_SHADOW_ENABLED
            and getattr(request.user, "is_authenticated", False)
        ):
            divergence = compare_access_classification(
                request.user,
                context=get_request_access_context(request),
            )
            if divergence:
                logger.warning("access_policy_shadow_divergence", extra=divergence)
        return response


class PresenceMiddleware:
    """Persist a recent activity marker at most once every five minutes."""

    session_key = "accounts_presence_touched_at"
    interval = timedelta(minutes=5)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            from django.utils import timezone
            from accounts.models import Profile

            now = timezone.now()
            previous = request.session.get(self.session_key)
            try:
                should_touch = previous is None or now.timestamp() - float(previous) >= self.interval.total_seconds()
            except (TypeError, ValueError):
                should_touch = True
            if should_touch:
                Profile.objects.filter(user=user).update(last_seen=now)
                request.session[self.session_key] = now.timestamp()
        return self.get_response(request)


class SystemSessionSecurityMiddleware:
    """Expiration autoritative des sessions SYSTEM, avant toute vue metier."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_htmx(request):
        return request.headers.get("HX-Request", "").lower() == "true"

    @staticmethod
    def _wants_json(request):
        return (
            "application/json" in request.headers.get("Accept", "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.content_type == "application/json"
        )

    @staticmethod
    def _safe_next_path(candidate, fallback="/portal/"):
        """Retourne un chemin local sûr pour le paramètre ``next``."""
        if not candidate:
            return fallback
        path = candidate.split("?", 1)[0] if "?" in candidate else candidate
        if not path.startswith("/") or path.startswith("//"):
            return fallback
        # Ne jamais renvoyer l'utilisateur vers la page de connexion elle-même.
        try:
            login_path = reverse(settings.LOGIN_URL)
        except Exception:
            login_path = "/accounts/login/"
        if path == login_path:
            return fallback
        return candidate

    def _login_url(self, request, reason):
        try:
            base = reverse(settings.LOGIN_URL)
        except Exception:
            base = reverse("accounts:login")
        # Pour une requête HTMX, ``request.get_full_path()`` désigne l'endpoint
        # du fragment, pas la page affichée. Après reconnexion, l'utilisateur
        # doit revenir sur la page complète (fournie par HX-Current-URL).
        if self._is_htmx(request):
            current_url = request.headers.get("HX-Current-URL", "")
            try:
                from urllib.parse import urlsplit

                parsed = urlsplit(current_url)
                next_path = parsed.path or ""
                if parsed.query:
                    next_path = f"{next_path}?{parsed.query}"
            except Exception:
                next_path = ""
            next_path = self._safe_next_path(next_path)
        else:
            next_path = self._safe_next_path(request.get_full_path())
        return f"{base}?{urlencode({'next': next_path, 'session_expired': reason.lower()})}"

    def _is_login_redirect(self, request, response):
        """Détecte une redirection vers la page de connexion (login_required…)."""
        if response.status_code not in {301, 302, 303, 307, 308}:
            return False
        location = response.headers.get("Location", "")
        if not location:
            return False
        try:
            login_path = reverse(settings.LOGIN_URL)
        except Exception:
            login_path = "/accounts/login/"
        return location.startswith(login_path)

    def _expired_response(self, request, reason):
        identifier = request.session.get(SESSION_ID_KEY)
        event_type = (
            AccountSecurityEvent.ABSOLUTE_TIMEOUT
            if reason == AccountSecurityEvent.ABSOLUTE_TIMEOUT
            else AccountSecurityEvent.IDLE_TIMEOUT
        )
        end_reason = (
            AccountSessionRecord.END_ABSOLUTE_TIMEOUT
            if event_type == AccountSecurityEvent.ABSOLUTE_TIMEOUT
            else AccountSessionRecord.END_IDLE_TIMEOUT
        )
        expired_user = request.user
        close_session_record(
            user=expired_user,
            identifier=identifier,
            reason=end_reason,
            request=request,
            event_type=event_type,
        )
        from accounts.session_security import notify_websocket_revocation

        request._suppress_security_logout_signal = True
        logout(request)
        from django.db import transaction

        transaction.on_commit(
            lambda user=expired_user: notify_websocket_revocation(user, reason=end_reason, identifier=identifier)
        )
        login_url = self._login_url(request, event_type)
        messages.warning(request, "Votre session a expire. Reconnectez-vous pour continuer.")

        if self._is_htmx(request):
            response = HttpResponse(status=401)
            response["HX-Redirect"] = login_url
            response["X-ESFE-Session-Expired"] = event_type
            return response
        if self._wants_json(request):
            return JsonResponse(
                {
                    "error": "session_expired",
                    "reason": event_type,
                    "login_url": login_url,
                },
                status=401,
            )
        return redirect(login_url)

    def _unauthenticated_async_response(self, request):
        protected_prefixes = (
            "/portal/",
            "/accounts/dashboard/",
            "/accounts/htmx/",
            "/secretary/",
            "/superadmin/",
            "/marketing/",
        )
        if not request.path.startswith(protected_prefixes):
            return None
        login_url = self._login_url(request, "SESSION_REQUIRED")
        if self._is_htmx(request):
            response = HttpResponse(status=401)
            response["HX-Redirect"] = login_url
            response["X-ESFE-Session-Expired"] = "SESSION_REQUIRED"
            return response
        if self._wants_json(request):
            return JsonResponse(
                {"error": "session_expired", "reason": "SESSION_REQUIRED", "login_url": login_url},
                status=401,
            )
        return None

    def __call__(self, request):
        user = getattr(request, "user", None)
        context = getattr(request, "access_context", None)
        if not user or not user.is_authenticated:
            async_response = self._unauthenticated_async_response(request)
            if async_response is not None:
                return async_response
            response = self.get_response(request)
            # Filet de sécurité : un endpoint protégé par ``login_required``
            # hors des préfixes ci-dessus répond 302 vers le login. Suivi par
            # HTMX, ce 302 injecterait la page de connexion complète dans un
            # fragment du dashboard. On le convertit en redirection propre.
            if self._is_htmx(request) and self._is_login_redirect(request, response):
                login_url = self._login_url(request, "SESSION_REQUIRED")
                converted = HttpResponse(status=401)
                converted["HX-Redirect"] = login_url
                converted["X-ESFE-Session-Expired"] = "SESSION_REQUIRED"
                return converted
            return response
        if not context or context.context_type != "SYSTEM":
            return self.get_response(request)

        initialize_system_session(request)
        state = session_deadline_state(request.session, context.position)
        if state is None:
            initialize_system_session(request)
            state = session_deadline_state(request.session, context.position)
        if state and state["reason"]:
            return self._expired_response(request, state["reason"])

        meaningful_header = request.headers.get("X-ESFE-Meaningful-Activity") == "1"
        automated_request = request.headers.get("X-ESFE-Automated-Request") == "1"
        meaningful_mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"} and not automated_request
        if meaningful_mutation or meaningful_header:
            state = record_meaningful_activity(request)

        response = self.get_response(request)
        if state:
            response["X-ESFE-Session-Remaining"] = str(state["remaining_seconds"])
        return response


class MandatoryPasswordChangeMiddleware:
    """Empêche un mot de passe temporaire de donner accès au logiciel."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            state = getattr(user, "support_state", None)
            if state and state.must_change_password:
                allowed_paths = {
                    reverse("accounts:password_change"),
                    reverse("accounts:password_change_done"),
                    reverse("accounts_portal:system_change_password"),
                    reverse("accounts_portal:system_session_status"),
                    reverse("accounts_portal:system_session_activity"),
                    reverse("accounts:logout"),
                }
                if request.path not in allowed_paths:
                    return redirect("accounts:password_change")
        return self.get_response(request)
