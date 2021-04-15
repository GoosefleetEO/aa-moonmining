# Generated by Django 3.1.6 on 2021-04-15 13:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("moonmining", "0005_auto_20210414_1408"),
    ]

    operations = [
        migrations.CreateModel(
            name="EveOreTypeExtra",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("refined_price", models.FloatField(default=None, null=True)),
                (
                    "ore_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extras",
                        to="moonmining.eveoretype",
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="EveOreTypeRefinedPrice",
        ),
    ]
