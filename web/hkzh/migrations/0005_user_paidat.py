# Generated by Django 4.0.2 on 2022-02-17 13:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hkzh', '0004_auto_20220217_1703'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='paidAt',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
