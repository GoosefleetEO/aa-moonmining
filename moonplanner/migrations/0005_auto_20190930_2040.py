# Generated by Django 2.2.5 on 2019-09-30 20:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("moonplanner", "0004_auto_20190930_1800"),
    ]

    operations = [
        migrations.RenameField(
            model_name="extrationproduct",
            old_name="amount",
            new_name="volume",
        ),
    ]
