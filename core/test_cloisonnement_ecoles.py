"""Cloisonnement ESGA / FATEC sur un même campus ; le DG voit les deux écoles."""
from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicClass
from accounts.access_context import build_access_context
from accounts.scoping import access_scope, scoped, scoped_get_object_or_404
from admissions.models import Candidature
from core import test_ufhob_phase2 as fixtures
from django.http import Http404
from inscriptions.models import Inscription
from students.models import Student


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class CloisonnementEcolesTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        _esmed, cls.esga, cls.fatec = cls.schools
        cls.p_esga, cls.p_fatec = cls.programmes[1], cls.programmes[2]
        cls.class_esga, cls.class_fatec = cls.classes[1], cls.classes[2]
        cls.c_esga = cls._candidature(cls.p_esga, "esga.candidat@example.invalid")
        cls.c_fatec = cls._candidature(cls.p_fatec, "fatec.candidat@example.invalid")
        cls.s_fatec = cls._student(cls.c_fatec)
        cls.users = {
            "esga": cls.make_user("gest-esga", "admissions", cls.a, cls.esga, "SCHOOL_BRANCH"),
            "fatec": cls.make_user("gest-fatec", "admissions", cls.a, cls.fatec, "SCHOOL_BRANCH"),
        }
        cls.dg = cls.global_user

    @classmethod
    def _candidature(cls, programme, email):
        return Candidature.objects.create(
            programme=programme, branch=cls.a, academic_year=cls.year.name, birth_date=date(2000, 1, 1),
            first_name="Candidat", last_name=programme.school.code, email=email, gender="female",
            phone=f"7{programme.pk:07d}", birth_place="Bamako", status="submitted",
        )

    @classmethod
    def _student(cls, candidature):
        candidature.status = "accepted"
        candidature.save(update_fields=["status"])
        inscription = Inscription.objects.create(candidature=candidature, amount_due=1, amount_paid=0)
        return Student.objects.filter(inscription=inscription).first() or Student.objects.create(
            user=cls.make_user(f"etu-{candidature.pk}", "student"), inscription=inscription,
            matricule=f"T{candidature.pk:05d}",
        )

    def pairs(self):
        return (("esga", self.c_esga, self.c_fatec), ("fatec", self.c_fatec, self.c_esga))

    def test_selecteur_central_ne_compte_que_son_ecole(self):
        for key, own, foreign in self.pairs():
            with self.subTest(key):
                user = self.users[key]
                visible = scoped(Candidature, user=user)
                self.assertTrue(visible.filter(pk=own.pk).exists())
                self.assertFalse(visible.filter(pk=foreign.pk).exists())
                self.assertEqual(visible.count(), 1)
                with self.assertRaises(Http404):
                    scoped_get_object_or_404(Candidature, user=user, pk=foreign.pk)
        self.assertEqual(scoped(Candidature, user=self.dg).filter(pk__in=[self.c_esga.pk, self.c_fatec.pk]).count(), 2)
        self.assertEqual(scoped_get_object_or_404(Candidature, user=self.dg, pk=self.c_fatec.pk), self.c_fatec)

    def test_liste_detail_action_et_export_par_ecole(self):
        for key, own, foreign in self.pairs():
            with self.subTest(key):
                self.client.force_login(self.users[key])
                listing = self.client.get(reverse("accounts_portal:portal_admissions"))
                self.assertContains(listing, own.email)
                self.assertNotContains(listing, foreign.email)
                for route in ("accounts:htmx_candidature_detail", "accounts:htmx_candidature_under_review"):
                    method = self.client.get if route.endswith("detail") else self.client.post
                    self.assertEqual(method(reverse(route, args=[foreign.pk]), HTTP_HX_REQUEST="true").status_code, 404, route)
                export = self.client.get(reverse("accounts:export_candidatures_csv"))
                if export.status_code == 200:
                    body = b"".join(export.streaming_content) if export.streaming else export.content
                    self.assertIn(own.email.encode(), body)
                    self.assertNotIn(foreign.email.encode(), body)
        foreign_status = Candidature.objects.get(pk=self.c_fatec.pk).status
        self.assertEqual(foreign_status, "accepted", "aucune action croisée n'a modifié la FATEC")

    def test_rapport_excel_ne_compte_que_son_ecole(self):
        from accounts.services import excel_reports

        captured = {}

        def capture(**kwargs):
            captured.update(kwargs["admissions_stats"])
            return object()

        period = {"start": date(2000, 1, 1), "end": date(2100, 1, 1), "key": "custom", "label": "Test"}
        with patch.object(excel_reports, "build_branch_xlsx_report", side_effect=capture), \
                patch("accounts.dashboards.manager_dashboard._resolve_report_period", return_value=period):
            with access_scope(build_access_context(self.users["esga"])):
                excel_reports.export_branch_report_xlsx(
                    branch=self.a, report_period=period, branch_staff_profiles=[], branch_teacher_profiles=[],
                )
        self.assertEqual(captured["candidatures_total"], 1)

    def test_vues_presence_classe_et_etudiant_autre_ecole_404(self):
        self.client.force_login(self.users["esga"])
        self.assertEqual(self.client.get(reverse("students:class_attendance_summary", args=[self.class_fatec.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("students:student_attendance_history", args=[self.s_fatec.pk])).status_code, 404)
        self.assertNotEqual(self.client.get(reverse("students:class_attendance_summary", args=[self.class_esga.pk])).status_code, 404)

    def test_structure_academique_filtre_l_ecole(self):
        from portal.services.academic_structure_service import build_academic_structure_context

        with access_scope(build_access_context(self.users["esga"])):
            context = build_academic_structure_context(branch=self.a)
            ids = {c.pk for c in context["classes_page"].object_list} if "classes_page" in context else set()
            self.assertIn(self.class_esga.pk, ids)
            self.assertNotIn(self.class_fatec.pk, ids)
            self.assertFalse(scoped(AcademicClass).filter(pk=self.class_fatec.pk).exists())
