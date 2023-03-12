# Generated by Django 4.0.3 on 2022-04-21 20:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("moonmining", "0004_add_permission_moon_ledgers"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="eveoretypeextras",
            name="refined_price",
        ),
        migrations.AddField(
            model_name="eveoretypeextras",
            name="current_price",
            field=models.FloatField(
                default=None,
                help_text="price used all price calculations with this type",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="eveoretypeextras",
            name="pricing_method",
            field=models.CharField(
                choices=[
                    ("UN", "Unknown"),
                    ("EC", "Eve client"),
                    ("RP", "Reprocessed materials"),
                ],
                default="UN",
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="moon",
            name="rarity_class",
            field=models.PositiveIntegerField(
                choices=[
                    (0, ""),
                    (4, "R 4"),
                    (8, "R 8"),
                    (16, "R16"),
                    (32, "R32"),
                    (64, "R64"),
                ],
                default=0,
            ),
        ),
    ]
