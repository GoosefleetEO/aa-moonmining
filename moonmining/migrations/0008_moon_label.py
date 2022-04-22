# Generated by Django 4.0.3 on 2022-04-22 11:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("moonmining", "0007_alter_label_style"),
    ]

    operations = [
        migrations.AddField(
            model_name="moon",
            name="label",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_DEFAULT,
                to="moonmining.label",
            ),
        ),
    ]
