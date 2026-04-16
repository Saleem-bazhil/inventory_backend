from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0006_add_engineer_model'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE authenticate_userprofile DROP COLUMN phone;",
            reverse_sql="ALTER TABLE authenticate_userprofile ADD COLUMN phone varchar(20) NOT NULL DEFAULT '';",
        ),
    ]
