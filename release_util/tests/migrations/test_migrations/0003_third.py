# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("release_util", "0002_second"),
    ]

    operations = [

        migrations.RemoveField("Author", "age"),

        migrations.AddField("Author", "birthplace", models.CharField(max_length=255)),

        migrations.AddField("Book", "isbn", models.CharField(max_length=255)),

        migrations.CreateModel(
            "Bookstore",
            [
                ("id", models.AutoField(primary_key=True)),
                ("address", models.CharField(max_length=255)),
            ],
        )

    ]
