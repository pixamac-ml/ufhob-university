from django_components import component


@component.register("dashboard_mini_calendar")
class DashboardMiniCalendar(component.Component):
    """Compact, role-agnostic calendar for certified dashboards."""

    template_name = "dashboard/mini_calendar.html"

    def get_context_data(
        self,
        title="Calendrier",
        action_label="Ouvrir le calendrier",
        action_url="",
        action_target="",
        action_push_url="true",
        **kwargs,
    ):
        return {
            "title": title,
            "action_label": action_label,
            "action_url": action_url,
            "action_target": action_target,
            "action_push_url": action_push_url,
            **kwargs,
        }
