# Generated by Django 4.0.2 on 2022-02-28 01:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hkzh', '0008_user_allow_today'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='paymentExpireAt',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]