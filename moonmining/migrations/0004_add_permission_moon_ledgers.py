# Generated by Django 3.2.9 on 2021-11-22 21:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("moonmining", "0003_mining_ledger_reports"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="general",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": (
                    ("basic_access", "Can access the moonmining app"),
                    (
                        "extractions_access",
                        "Can access extractions and view owned moons",
                    ),
                    ("reports_access", "Can access reports"),
                    ("view_all_moons", "Can view all known moons"),
                    ("upload_moon_scan", "Can upload moon scans"),
                    ("add_refinery_owner", "Can add refinery owner"),
                    ("view_moon_ledgers", "Can view moon ledgers"),
                ),
            },
        ),
    ]