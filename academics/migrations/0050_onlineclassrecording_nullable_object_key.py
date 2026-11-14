from django.db import migrations, models


def replace_empty_object_keys(apps, schema_editor):
    OnlineClassRecording = apps.get_model("academics", "OnlineClassRecording")
    OnlineClassRecording.objects.filter(object_key="").update(object_key=None)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0049_onlineclassrecording"),
    ]

    operations = [
        migrations.AlterField(
            model_name="onlineclassrecording",
            name="object_key",
            field=models.CharField(blank=True, max_length=1024, null=True, unique=True),
        ),
        migrations.RunPython(replace_empty_object_keys, migrations.RunPython.noop),
    ]
