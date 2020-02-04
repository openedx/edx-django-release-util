# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class BasicModel(models.Model):
    first_name = models.CharField(max_length=20)
    start = models.DateField()


class ChildModel(BasicModel):
    last_name = models.CharField(max_length=20)
    nick_name = models.CharField(max_length=20)


class GrandchildModel(ChildModel):
    middle_name = models.CharField(max_length=20)
    end = models.DateField()
