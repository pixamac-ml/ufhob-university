"""Scope the existing technical admin using the same business selectors."""

from accounts.scoping import SCOPE_PATHS, scope_queryset, scoped
from accounts.scoping import resolve_context


class UniversityScopeAdminMixin:
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        context = resolve_context(user=request.user)
        if getattr(context, "school", None) or getattr(context, "branch", None):
            return scope_queryset(queryset, context=context)
        return queryset

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        model = db_field.remote_field.model
        if model._meta.label_lower in SCOPE_PATHS:
            kwargs["queryset"] = scoped(model, user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
