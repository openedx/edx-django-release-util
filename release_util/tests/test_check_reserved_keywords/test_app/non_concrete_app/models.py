# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class BasicModel(models.Model):
    class Meta:
        app_label = 'non_concrete_app'

    first_name = models.CharField(max_length=20)


class ModelMixin(object):
    age = 100


class MixedModel(BasicModel, ModelMixin):
    class Meta:
        app_label = 'non_concrete_app'

    last_name = models.CharField(max_length=20)


class AbstractModel(models.Model):
    class Meta:
        app_label = 'non_concrete_app'
        abstract = True

    start_date = models.CharField(max_length=20)


class ModelWithAbstractParent(AbstractModel):
    class Meta:
        app_label = 'non_concrete_app'

    end_date = models.CharField(max_length=20)


class ProxyModel(BasicModel):
    class Meta:
        app_label = 'non_concrete_app'
        proxy = True
