# Generated by Django 2.2.5 on 2019-09-26 23:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moonstuff', '0002_auto_20190926_2328'),
    ]

    operations = [
        migrations.AlterField(
            model_name='marketprice',
            name='last_updated',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
