from django import template

from notification_center.presentation import get_safe_action_url


register = template.Library()


@register.simple_tag(takes_context=True)
def notification_action_url(context, notification):
    return get_safe_action_url(notification, context.get("request"))


@register.filter
def notification_category(notification):
    if notification.event_type == "new_human_message":
        return "Messagerie"
    source = getattr(getattr(notification, "event", None), "source_app", "")
    if source in {"payments", "finance", "accounts.finance"}:
        return "Finance"
    if source in {"academics", "academic_cycle", "formations", "grades"}:
        return "Académique"
    if source in {"admissions", "inscriptions", "secretary", "portal"}:
        return "Administration"
    if source in {"accounts", "auth", "security"}:
        return "Sécurité"
    return "Système"
