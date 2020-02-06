import os
import tempfile

import django
from django.conf import settings
from django.apps import apps
import pytest
import yaml

from ..reserved_keyword_checker import (
    check_model_for_violations,
    collect_concrete_models,
    Config,
    ConfigurationException,
    get_fields_per_model
)

@pytest.fixture
def django_setup():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'reserved_keyword_checker.tests.test_app.test_app.settings'
    django.setup()


def load_apps(app_names):
    settings.INSTALLED_APPS = app_names
    apps.ready = False
    apps.apps_ready = apps.models_ready = apps.loading = apps.ready = False
    apps.app_configs = {}
    apps.populate(settings.INSTALLED_APPS)


def test_concrete_model_collection(django_setup):
    load_apps(['reserved_keyword_checker.tests.test_app.local_app'])
    models = collect_concrete_models()
    expected_model_names = ['BasicModel', 'ChildModel', 'GrandchildModel']
    assert sorted([m._meta.concrete_model.__name__ for m in models]) == expected_model_names


def test_model_collection_with_non_concrete_models(django_setup):
    load_apps(['reserved_keyword_checker.tests.test_app.non_concrete_app'])
    models = collect_concrete_models()
    expected_model_names = ['BasicModel', 'MixedModel', 'ModelWithAbstractParent']
    assert sorted([m._meta.concrete_model.__name__ for m in models]) == expected_model_names


def test_field_collection_with_inheritance(django_setup):
    from .test_app.local_app import models as local_models
    model = local_models.GrandchildModel
    model_fields = get_fields_per_model(model)
    expected_field_names = [
        'end', 'first_name', 'last_name', 'middle_name', 'nick_name', 'start'
    ]
    assert sorted(model_fields) == expected_field_names


def test_field_collection_with_non_concrete_parents(django_setup):
    from .test_app.non_concrete_app import models as non_concrete_models
    model = non_concrete_models.ModelWithAbstractParent
    model_fields = get_fields_per_model(model)
    expected_field_names = [
        'end_date', 'start_date'
    ]
    assert sorted(model_fields) == expected_field_names


def test_missing_config():
    with pytest.raises(ConfigurationException) as exception:
        Config('tests/test_files/missing_config.yml', None, 'reports')

    exc_msg = str(exception.value)
    assert "Unable to load config file:" in exc_msg


def test_invalid_override_config():
    with pytest.raises(ConfigurationException) as exception:
        Config(
            'reserved_keyword_checker/tests/test_files/reserved_keywords.yml',
            'reserved_keyword_checker/tests/test_files/invalid_overrides.yml',
            'reports'
        )
    exc_msg = str(exception.value)
    assert "Invalid value in override file: BasicModel. second_field" in exc_msg


def test_reserved_keyword_detection(django_setup):
    from .test_app.local_app import models as local_models
    model = local_models.GrandchildModel
    config = Config('reserved_keyword_checker/tests/test_files/reserved_keywords.yml', None, 'reports')
    violations = check_model_for_violations(model, config)
    violation_strings = map(lambda v: v.report_string(), violations)
    expected_violations = [
        'MYSQL,Local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,end,Defined here',
        'MYSQL,Local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,nick_name,Inherited',
        'MYSQL,Local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,start,Inherited',
        'STITCH,Local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,end,Defined here',
        'STITCH,Local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,start,Inherited',
    ]
    assert sorted(violation_strings) == expected_violations


def test_overrides(django_setup):
    from .test_app.local_app import models as local_models
    model = local_models.GrandchildModel
    config = Config(
        'reserved_keyword_checker/tests/test_files/reserved_keywords.yml',
        'reserved_keyword_checker/tests/test_files/overrides.yml',
        'reports'
    )
    violations = check_model_for_violations(model, config)
    assert len(violations) == 5
    overridden_violations = [str(v) for v in violations if v.override]
    assert overridden_violations == [
        'STITCH conflict in local_app:reserved_keyword_checker/tests/test_app/local_app/models.py:GrandchildModel.end'
    ]
