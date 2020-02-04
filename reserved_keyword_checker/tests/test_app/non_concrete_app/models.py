# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class BasicModel(models.Model):
    first_name = models.CharField(max_length=20)


class ModelMixin(object):
    age = 100


class MixedModel(BasicModel, ModelMixin):
    last_name = models.CharField(max_length=20)


class AbstractModel(models.Model):
    start_date = models.CharField(max_length=20)

    class Meta:
        abstract = True


class ModelWithAbstractParent(AbstractModel):
    end_date = models.CharField(max_length=20)


class ProxyModel(BasicModel):
    
    class Meta:
        proxy = True
