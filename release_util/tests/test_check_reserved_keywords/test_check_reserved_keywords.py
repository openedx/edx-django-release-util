import io
import os
import tempfile

import django
import pytest
import yaml
from django.apps import apps
from django.conf import settings

from release_util.management.commands.check_reserved_keywords import (
    Config,
    ConfigurationException,
    Violation,
    check_model_for_violations,
    collect_concrete_models,
    get_fields_per_model,
)


@pytest.fixture
def django_setup():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'release_util.tests.test_check_reserved_keywords.test_app.test_app.settings'
    django.setup()


def load_apps(app_names):
    settings.INSTALLED_APPS = app_names
    apps.ready = False
    apps.apps_ready = apps.models_ready = apps.loading = apps.ready = False
    apps.app_configs = {}
    apps.populate(settings.INSTALLED_APPS)


def test_concrete_model_collection(django_setup):
    load_apps(['release_util.tests.test_check_reserved_keywords.test_app.local_app'])
    models = collect_concrete_models()
    expected_model_names = ['BasicModel', 'ChildModel', 'GrandchildModel']
    assert sorted([m._meta.concrete_model.__name__ for m in models]) == expected_model_names


def test_concrete_model_collection_with_third_party_apps(django_setup):
    load_apps([
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'waffle'
    ])
    models = collect_concrete_models()
    expected_model_names = [
        'ContentType', 'Flag', 'Group', 'Permission', 'Sample', 'Switch', 'User'
    ]
    assert sorted([m._meta.concrete_model.__name__ for m in models]) == expected_model_names


def test_model_collection_with_non_concrete_models(django_setup):
    load_apps(['release_util.tests.test_check_reserved_keywords.test_app.non_concrete_app'])
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


def test_field_collection_with_third_party_app(django_setup):
    load_apps([
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'waffle'
    ])
    from waffle.models import Switch
    model_fields = get_fields_per_model(Switch)
    expected_field_names = ['active', 'created', 'modified', 'name', 'note']
    assert sorted(model_fields) == expected_field_names


def test_local_app_location_detection(django_setup):
    from .test_app.local_app import models as local_models
    load_apps(['release_util.tests.test_check_reserved_keywords.test_app.local_app'])
    violation = Violation(local_models.GrandchildModel, None, None, None)
    assert violation.local_app


def test_third_party_app_location_detection(django_setup):
    """
    django-waffle is considered to be not-local, that is, it is not defined within
    the local source code of this application, but is installed in its Python
    environment
    """
    load_apps([
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'waffle'
    ])
    from waffle.models import Switch
    violation = Violation(Switch, None, None, None)
    assert not violation.local_app


def test_invalid_override_config():
    with pytest.raises(ConfigurationException) as exception:
        keyword_file = io.open(
            'release_util/tests/test_check_reserved_keywords/test_files/reserved_keywords.yml', 'r'
        )
        override_file = io.open(
            'release_util/tests/test_check_reserved_keywords/test_files/invalid_overrides.yml', 'r'
        )
        Config(keyword_file, override_file, 'reports', None)
    exc_msg = str(exception.value)
    assert "Invalid value in override file: BasicModel. second_field" in exc_msg


def test_reserved_keyword_detection(django_setup):
    from .test_app.local_app import models as local_models
    load_apps(['release_util.tests.test_check_reserved_keywords.test_app.local_app'])
    model = local_models.GrandchildModel
    keyword_file = io.open('release_util/tests/test_check_reserved_keywords/test_files/reserved_keywords.yml', 'r')
    config = Config(keyword_file, None, 'reports', None)
    violations = check_model_for_violations(model, config)
    violation_strings = map(lambda v: v.report_string(), violations)
    expected_violations = [
        (
            'MYSQL,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,end,Class Definition,'
        ), (
            'MYSQL,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,nick_name,Inherited,'
        ), (
            'MYSQL,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,start,Inherited,'
        ), (
            'STITCH,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,end,Class Definition,'
        ), (
            'STITCH,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,start,Inherited,'
        ),
    ]
    assert sorted(violation_strings) == expected_violations


def test_reserved_keyword_detection_specific_system(django_setup):
    from .test_app.local_app import models as local_models
    load_apps(['release_util.tests.test_check_reserved_keywords.test_app.local_app'])
    model = local_models.GrandchildModel
    keyword_file = io.open('release_util/tests/test_check_reserved_keywords/test_files/reserved_keywords.yml', 'r')
    config = Config(keyword_file, None, 'reports', 'STITCH')
    violations = check_model_for_violations(model, config)
    violation_strings = map(lambda v: v.report_string(), violations)
    expected_violations = [
        (
            'STITCH,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,end,Class Definition,'
        ), (
            'STITCH,Local,local_app,release_util/tests/test_check_reserved_keywords/test_app/'
            'local_app/models.py,GrandchildModel,start,Inherited,'
        ),
    ]
    assert sorted(violation_strings) == expected_violations


def test_overrides(django_setup):
    from .test_app.local_app import models as local_models
    model = local_models.GrandchildModel
    keyword_file = io.open('release_util/tests/test_check_reserved_keywords/test_files/reserved_keywords.yml', 'r')
    override_file = io.open('release_util/tests/test_check_reserved_keywords/test_files/overrides.yml', 'r')
    config = Config(keyword_file, override_file, 'reports', None)
    violations = check_model_for_violations(model, config)
    assert len(violations) == 5
    overridden_violations = [str(v) for v in violations if v.override]
    assert overridden_violations == [
        (
            'STITCH conflict in local_app:release_util/tests/test_check_reserved_keywords/'
            'test_app/local_app/models.py:GrandchildModel.end'
        )
    ]
