# Generated by Django 4.2.19 on 2025-04-24 12:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0065_delete_property'),
        ('publication', '0012_alter_publication_original_surface'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='publication',
            unique_together={('original_surface', 'version')},
        ),
    ]
