# Generated by Django 4.0.2 on 2022-02-24 01:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hkzh', '0007_alter_payment_amount_alter_payment_payat'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='allow_today',
            field=models.BooleanField(default=False),
        ),
    ]
