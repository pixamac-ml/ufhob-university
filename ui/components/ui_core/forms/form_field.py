from django_components import component


@component.register("ui_core.form_field")
class FormField(component.Component):
    template_name = "ui_core/forms/form_field.html"

    def get_context_data(
        self,
        id="ui-core-field",
        name="field",
        label="",
        value="",
        type="text",
        placeholder="",
        help_text="",
        error="",
        success="",
        accept="",
        autocomplete="",
        inputmode="",
        min_value="",
        max_value="",
        step="",
        required=False,
        disabled=False,
        readonly=False,
        options=None,
        loading=False,
        prefix="",
        suffix="",
        **kwargs,
    ):
        allowed_types = {"text", "email", "password", "number", "search", "date", "time", "datetime-local", "tel", "url", "file", "textarea", "select"}
        return {
            "id": id,
            "name": name,
            "label": label,
            "value": value,
            "type": type if type in allowed_types else "text",
            "placeholder": placeholder,
            "help_text": help_text,
            "error": error,
            "success": success,
            "accept": accept,
            "autocomplete": autocomplete,
            "inputmode": inputmode,
            "min_value": min_value,
            "max_value": max_value,
            "step": step,
            "required": bool(required),
            "disabled": bool(disabled),
            "readonly": bool(readonly),
            "options": options or [],
            "loading": bool(loading),
            "prefix": prefix,
            "suffix": suffix,
            **kwargs,
        }
