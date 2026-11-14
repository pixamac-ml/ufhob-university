from django.db import migrations


def normalize_school_display_names(apps, schema_editor):
    """Normalize user-facing labels without changing stable school codes/IDs."""
    School = apps.get_model("core", "School")
    for code, display_name in {
        "ESMED": "EsMed",
        "ESV": "ESVé-SUP",
        "ESGA": "ESGA",
        "FATEC": "FATEC",
    }.items():
        School.objects.filter(code__iexact=code).update(short_name=display_name)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_directorgeneralmessage"),
    ]

    operations = [
        migrations.RunPython(normalize_school_display_names, migrations.RunPython.noop),
    ]
