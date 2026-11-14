from django_components import component


@component.register("course_studio")
class CourseStudio(component.Component):
    """Fullscreen teacher workspace for authoring one academic subject."""

    template_name = "dashboard/course_studio.html"

    def get_context_data(self, title="Course Studio", subtitle="", **kwargs):
        return {"title": title, "subtitle": subtitle, **kwargs}
