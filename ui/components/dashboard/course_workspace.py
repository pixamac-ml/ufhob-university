from django_components import component


@component.register("course_workspace")
class CourseWorkspace(component.Component):
    """Responsive two-zone learning workspace used by course readers."""

    template_name = "dashboard/course_workspace.html"

    def get_context_data(self, title="Cours", subtitle="", collapsible=False, fullscreen=False, **kwargs):
        return {
            "title": title,
            "subtitle": subtitle,
            "collapsible": bool(collapsible),
            "fullscreen": bool(fullscreen),
            **kwargs,
        }
