from django.test import SimpleTestCase

from academics.services.academic_positioning import get_programme_year_number_for_level


class AcademicPositioningLevelTests(SimpleTestCase):
    def test_real_world_level_labels_map_to_programme_years(self):
        cases = {
            "L1": 1,
            "Licence 2": 2,
            "1ère année": 1,
            "2ème année": 2,
            "deuxième année": 2,
            "Année III": 3,
            "M2": 2,
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(get_programme_year_number_for_level(label), expected)

    def test_bare_cycle_name_stays_ambiguous(self):
        self.assertIsNone(get_programme_year_number_for_level("Licence"))
