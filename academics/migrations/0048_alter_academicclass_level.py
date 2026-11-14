from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0047_university_access_scope"),
    ]

    operations = [
        migrations.AlterField(
            model_name="academicclass",
            name="level",
            field=models.CharField(
                help_text="Libellé libre : L1, Licence 1, 1ère année, Deuxième année, etc.",
                max_length=40,
            ),
        ),
    ]
