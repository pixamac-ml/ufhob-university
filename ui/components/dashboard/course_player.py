from django_components import component


@component.register("course_player")
class CoursePlayer(component.Component):
    """Dedicated fullscreen student learning player."""

    template_name = "dashboard/course_player.html"

    def get_context_data(self, title="Cours", subtitle="", collapsible=True, **kwargs):
        return {
            "title": title,
            "subtitle": subtitle,
            "collapsible": bool(collapsible),
            **kwargs,
        }
