# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class BasicModel(models.Model):
    class Meta:
        app_label = 'local_app'

    first_name = models.CharField(max_length=20)
    start = models.DateField()


class ChildModel(BasicModel):
    class Meta:
        app_label = 'local_app'

    last_name = models.CharField(max_length=20)
    nick_name = models.CharField(max_length=20)


class GrandchildModel(ChildModel):
    class Meta:
        app_label = 'local_app'

    _middle_name_field = models.CharField(max_length=20, db_column='middle_name')
    end = models.DateField()
