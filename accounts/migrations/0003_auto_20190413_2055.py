# Generated by Django 2.0.2 on 2019-04-13 15:25

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20190413_1705'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='cash',
            field=models.DecimalField(decimal_places=2, default=Decimal('5000'), max_digits=20),
        ),
    ]
