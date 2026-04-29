from django.db import migrations, models


def drop_phone_if_exists(apps, schema_editor):
    UserProfile = apps.get_model("authenticate", "UserProfile")
    connection = schema_editor.connection
    
    # Check if the column exists before trying to drop it
    with connection.cursor() as cursor:
        table_description = connection.introspection.get_table_description(
            cursor, UserProfile._meta.db_table
        )
        column_exists = any(column.name == "phone" for column in table_description)

    if column_exists:
        # Create a dummy field instance to pass to remove_field
        # This is safer than raw SQL as it handles SQLite's lack of DROP COLUMN in older versions
        field = models.CharField(max_length=20, null=True)
        field.set_attributes_from_name("phone")
        schema_editor.remove_field(UserProfile, field)


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0006_add_engineer_model'),
    ]

    operations = [
        migrations.RunPython(drop_phone_if_exists, migrations.RunPython.noop),
    ]
