from django.db import migrations


def correct_official_school_display_names(apps, schema_editor):
    """Keep historical codes while enforcing the UFHOB-Mali public labels."""
    School = apps.get_model("core", "School")
    display_names = {
        "ESMED": "ESMed",
        "ESGA": "ESGA",
        "FATEC": "FATEC",
        # Both legacy technical codes are retained if they exist.
        "ESV": "ESFé Sup",
        "ESFÉ": "ESFé Sup",
    }
    for code, display_name in display_names.items():
        School.objects.filter(code__iexact=code).update(short_name=display_name)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_normalize_official_school_display_names"),
    ]

    operations = [
        migrations.RunPython(correct_official_school_display_names, migrations.RunPython.noop),
    ]
