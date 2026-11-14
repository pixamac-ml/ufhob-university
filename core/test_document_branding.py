from types import SimpleNamespace

from django.test import SimpleTestCase

from core.pdf_documents import OFFICIAL_UNIVERSITY_NAME, _render_html, get_document_branding_context


def _academic_context(school_name, campus_name, year_name):
    institution = SimpleNamespace(address="Adresse UFHOB", city="Bamako", phone="", email="")
    school = SimpleNamespace(
        official_name=school_name,
        short_name=school_name,
        code=school_name,
        institution=institution,
        logo=None,
    )
    programme = SimpleNamespace(
        title=f"Programme {school_name}",
        school=school,
        cycle=SimpleNamespace(name="Licence"),
    )
    academic_class = SimpleNamespace(
        programme=programme,
        branch=SimpleNamespace(name=campus_name),
        academic_year=SimpleNamespace(name=year_name),
        display_name=f"L1 {school_name}",
    )
    enrollment = SimpleNamespace(
        programme=programme,
        academic_class=academic_class,
        branch=academic_class.branch,
        academic_year=academic_class.academic_year,
    )
    return enrollment


class DocumentBrandingContextTests(SimpleTestCase):
    def test_each_document_uses_its_own_school_and_campus(self):
        school_a = get_document_branding_context(
            _academic_context("ESMED", "Campus A", "2025-2026"),
            institution=SimpleNamespace(name="UFHOB", address="", city="", phone="", email=""),
        )
        school_b = get_document_branding_context(
            _academic_context("ESGA", "Campus B", "2026-2027"),
            institution=SimpleNamespace(name="UFHOB", address="", city="", phone="", email=""),
        )

        self.assertEqual(school_a["institution_official_name"], OFFICIAL_UNIVERSITY_NAME)
        self.assertEqual((school_a["school_name"], school_a["branch_name"]), ("ESMED", "Campus A"))
        self.assertEqual((school_b["school_name"], school_b["branch_name"]), ("ESGA", "Campus B"))
        self.assertEqual(school_a["cycle_name"], "Licence")
        self.assertEqual(school_a["academic_year_name"], "2025-2026")

    def test_historical_enrollment_context_is_not_replaced_by_current_context(self):
        old_enrollment = _academic_context("ESMED", "Ancien campus", "2023-2024")

        branding = get_document_branding_context(
            old_enrollment,
            institution=SimpleNamespace(name="UFHOB", address="", city="", phone="", email=""),
        )

        self.assertEqual(branding["school_name"], "ESMED")
        self.assertEqual(branding["branch_name"], "Ancien campus")
        self.assertEqual(branding["academic_year_name"], "2023-2024")

    def test_canonical_receipt_template_renders_dynamic_school_and_campus(self):
        enrollment = _academic_context("ESGA", "Campus B", "2026-2027")
        programme = enrollment.programme
        html = _render_html(
            "esfe_receipt",
            {
                "document_context": enrollment,
                "institution": programme.school.institution,
                "school_object": programme.school,
                "branch": enrollment.branch,
                "programme_object": programme,
                "school": "ESGA",
                "school_name": "ESGA",
                "branch_name": "Campus B",
                "programme": programme.title,
                "academic_year": "2026-2027",
                "student_name": "Test Student",
                "items": [],
            },
        )

        self.assertIn(OFFICIAL_UNIVERSITY_NAME, html)
        self.assertIn("ESGA", html)
        self.assertIn("Campus B", html)
        self.assertNotIn("ESFé", html)
