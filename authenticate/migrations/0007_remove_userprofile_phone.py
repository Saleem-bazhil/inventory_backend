from django.db import migrations


def drop_phone_if_exists(apps, schema_editor):
    connection = schema_editor.connection
    cursor = connection.cursor()
    # Check if the column exists before trying to drop it
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'authenticate_userprofile' AND column_name = 'phone'"
    )
    if cursor.fetchone():
        cursor.execute("ALTER TABLE authenticate_userprofile DROP COLUMN phone;")


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0006_add_engineer_model'),
    ]

    operations = [
        migrations.RunPython(drop_phone_if_exists, migrations.RunPython.noop),
    ]
