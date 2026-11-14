from pathlib import Path

from django import forms

from formations.models import RequiredDocument


class ManagerCandidatureDocumentForm(forms.Form):
    document_type = forms.ModelChoiceField(queryset=RequiredDocument.objects.none(), label="Type de document")
    file = forms.FileField(label="Document", help_text="PDF, JPG, PNG, DOC ou DOCX — 10 Mo maximum.")

    def __init__(self, *args, candidature, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document_type"].queryset = RequiredDocument.objects.filter(
            programmerequireddocument__programme=candidature.programme
        ).exclude(candidaturedocument__candidature=candidature)
        for field in self.fields.values():
            field.widget.attrs["class"] = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm"

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if Path(uploaded.name).suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}:
            raise forms.ValidationError("Format non autorisé.")
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Chaque document doit peser au maximum 10 Mo.")
        return uploaded
