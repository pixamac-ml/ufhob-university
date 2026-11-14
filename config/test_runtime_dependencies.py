"""Functional checks for the security-updated document and ASGI stack."""
from io import BytesIO

from django.contrib.auth.hashers import check_password, make_password
from django.test import SimpleTestCase, override_settings


class RuntimeDependencyTests(SimpleTestCase):
    def test_pdf_roundtrip_and_existing_memoire_webp_conversion(self):
        import fitz
        from PIL import Image
        from pypdf import PdfReader
        from weasyprint import HTML
        from memoires.services.rendering import _pixmap_to_webp

        pdf = HTML(string="<html><body><h1>UFHOB</h1><p>Document de validation.</p></body></html>").write_pdf()
        self.assertTrue(pdf.startswith(b"%PDF-"))
        reader = PdfReader(BytesIO(pdf))
        self.assertEqual(len(reader.pages), 1)
        self.assertIn("UFHOB", reader.pages[0].extract_text())
        with fitz.open(stream=pdf, filetype="pdf") as document:
            self.assertIn("UFHOB", document[0].get_text())
            webp = _pixmap_to_webp(document[0].get_pixmap(matrix=fitz.Matrix(0.25, 0.25)))
        with Image.open(BytesIO(webp)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertGreater(image.width, 0)

    def test_qrcode_and_pillow_image_resize_roundtrip(self):
        import qrcode
        from PIL import Image, ImageOps

        qr = qrcode.make("UFHOB-local-validation").convert("RGB")
        resized = ImageOps.exif_transpose(qr).resize((128, 128), Image.Resampling.LANCZOS)
        for image_format in ("PNG", "JPEG", "WEBP"):
            with self.subTest(format=image_format):
                buffer = BytesIO()
                resized.save(buffer, format=image_format)
                with Image.open(BytesIO(buffer.getvalue())) as restored:
                    restored.load()
                    self.assertEqual(restored.size, (128, 128))

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_django_password_hashes_keep_their_authentication_contract(self):
        encoded = make_password("only-a-test-fixture-password")
        self.assertTrue(check_password("only-a-test-fixture-password", encoded))
        self.assertFalse(check_password("incorrect-fixture-password", encoded))

    def test_daphne_and_application_asgi_import(self):
        from daphne.server import Server
        from config.asgi import application

        self.assertTrue(callable(Server))
        self.assertTrue(callable(application))

    def test_private_storage_migration_state_contains_no_machine_path(self):
        from django.conf import settings
        from django.db.migrations.writer import MigrationWriter
        from memoires.models import Memoire, PageMemoire

        for model, name in [(Memoire, "fichier_source"), (PageMemoire, "image")]:
            serialized, _imports = MigrationWriter.serialize(model._meta.get_field(name))
            self.assertIn("get_memoire_private_storage", serialized)
            self.assertNotIn(str(settings.BASE_DIR), serialized)
            self.assertNotIn(str(settings.MEMOIRES_PRIVATE_ROOT), serialized)
