from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0003_bufferpart_region"),
    ]

    operations = [
        migrations.AddField(
            model_name="bufferpart",
            name="case_id",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Case ID"),
        ),
        migrations.AddField(
            model_name="bufferpart",
            name="engineer_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Engineer Name"),
        ),
        migrations.AddField(
            model_name="bufferpart",
            name="status",
            field=models.CharField(
                choices=[
                    ("BUFFER_IN", "BUFFER In"),
                    ("OUT", "Out"),
                    ("DEFECTIVE_RETURN", "Defective Return"),
                    ("REORDER", "Reorder"),
                    ("PART_RECEIVED", "Part Received"),
                    ("CLOSED", "Closed"),
                ],
                default="BUFFER_IN",
                max_length=30,
                verbose_name="Status",
            ),
        ),
        migrations.AddField(
            model_name="bufferpart",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, verbose_name="Transition History"),
        ),
    ]
