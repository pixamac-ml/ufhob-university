from django_components import component


@component.register("ui_core.django_form_field")
class DjangoFormField(component.Component):
    """Render a Django BoundField with the certified UI Core field contract."""

    template_name = "ui_core/forms/django_form_field.html"

    def get_context_data(self, field=None, **kwargs):
        widget = getattr(getattr(field, "field", None), "widget", None)
        widget_name = widget.__class__.__name__ if widget else ""
        field_id = getattr(field, "id_for_label", "")
        has_help = bool(getattr(field, "help_text", ""))
        has_errors = bool(getattr(field, "errors", None))
        described_by = []
        if has_help:
            described_by.append(f"{field_id}-help")
        if has_errors:
            described_by.append(f"{field_id}-errors")
        widget_attrs = {}
        if described_by:
            widget_attrs["aria-describedby"] = " ".join(described_by)
        if has_errors:
            widget_attrs["aria-invalid"] = "true"
        return {
            "field": field,
            "rendered_field": field.as_widget(attrs=widget_attrs) if field else "",
            "field_id": field_id,
            "has_errors": has_errors,
            "is_checkbox": widget_name == "CheckboxInput",
            "is_percentage": getattr(field, "name", "") in {"amo_rate", "inps_rate"},
            "is_wide": widget_name in {
                "Textarea",
                "ClearableFileInput",
                "FileInput",
                "SelectMultiple",
                "CheckboxInput",
            },
            **kwargs,
        }
