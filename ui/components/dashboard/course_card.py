from django_components import component


@component.register("course_card")
class CourseCard(component.Component):
    """Shared, neutral course card backed by authoritative course metadata."""

    template_name = "dashboard/course_card.html"

    def get_context_data(self, course, detail_url="", **kwargs):
        return {
            "course": course,
            "detail_url": detail_url,
            **kwargs,
        }
