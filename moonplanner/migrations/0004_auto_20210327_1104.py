# Generated by Django 3.1.6 on 2021-03-27 11:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("moonplanner", "0003_miningcorporation_last_update_ok"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="general",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": (
                    ("basic_access", "Can access the moonplanner app"),
                    (
                        "extractions_access",
                        "Can access extractions and view owned moons",
                    ),
                    ("reports_access", "Can access reports"),
                    ("view_all_moons", "Can view all known moons"),
                    ("upload_moon_scan", "Can upload moon scans"),
                    ("add_corporation", "Can add mining corporations"),
                ),
            },
        ),
    ]
