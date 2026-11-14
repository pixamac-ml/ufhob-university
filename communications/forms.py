from django import forms
from django.core.validators import FileExtensionValidator
import zipfile


class MessageForm(forms.Form):
    body = forms.CharField(max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Écrivez votre message…", "class": "w-full resize-none rounded-ui-input border border-ui-border bg-ui-surface px-3 py-2 text-sm text-ui-text"}))
    attachment = forms.FileField(required=False, validators=[FileExtensionValidator(["pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png", "webp"])])

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment and attachment.size > 10 * 1024 * 1024:
            raise forms.ValidationError("La pièce jointe ne doit pas dépasser 10 Mo.")
        allowed_types = {
            "application/pdf", "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "image/jpeg", "image/png", "image/webp",
        }
        if attachment:
            extension = attachment.name.rsplit(".", 1)[-1].lower() if "." in attachment.name else ""
            mime_by_extension = {
                "pdf": "application/pdf", "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
            }
            claimed_mime = getattr(attachment, "content_type", "")
            if claimed_mime and (claimed_mime not in allowed_types or claimed_mime != mime_by_extension.get(extension)):
                raise forms.ValidationError("Ce type de fichier n'est pas autorisé.")
            header = attachment.read(16)
            attachment.seek(0)
            signatures = {
                "pdf": header.startswith(b"%PDF-"),
                "jpg": header.startswith(b"\xff\xd8\xff"), "jpeg": header.startswith(b"\xff\xd8\xff"),
                "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
                "webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
                "doc": header.startswith(b"\xd0\xcf\x11\xe0"), "xls": header.startswith(b"\xd0\xcf\x11\xe0"),
                "docx": zipfile.is_zipfile(attachment), "xlsx": zipfile.is_zipfile(attachment),
            }
            attachment.seek(0)
            if not signatures.get(extension, False):
                raise forms.ValidationError("La signature du fichier ne correspond pas à son format.")
            if extension in {"docx", "xlsx"}:
                with zipfile.ZipFile(attachment) as archive:
                    expected = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
                    if expected not in archive.namelist():
                        raise forms.ValidationError("Ce document Office n'est pas valide.")
                attachment.seek(0)
        return attachment

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("body") or cleaned.get("attachment")):
            raise forms.ValidationError("Écrivez un message ou ajoutez une pièce jointe.")
        return cleaned
