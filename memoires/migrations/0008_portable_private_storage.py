import memoires.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memoires", "0007_memoire_document_is_public_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="memoire",
            name="fichier_source",
            field=models.FileField(
                blank=True,
                storage=memoires.storage.get_memoire_private_storage,
                upload_to="memoires/sources/",
            ),
        ),
        migrations.AlterField(
            model_name="pagememoire",
            name="image",
            field=models.ImageField(
                storage=memoires.storage.get_memoire_private_storage,
                upload_to="memoires/pages/",
            ),
        ),
    ]
