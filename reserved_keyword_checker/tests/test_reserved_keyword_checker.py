import os
import tempfile

import django
import yaml

from ..reserved_keyword_checker import (
    collect_concrete_models,
    get_fields_per_model,
    check_model_for_violations,
    Config
)


def my_setup(config_path):
    os.environ['DJANGO_SETTINGS_MODULE'] = config_path
    django.setup()


def test_concrete_model_collection():
    my_setup('reserved_keyword_checker.tests.test_app.test_app.settings')
    models = collect_concrete_models()

    expected_model_names = ['BasicModel', 'ChildModel', 'GrandchildModel']

    assert sorted(models['local_app'].keys()) == expected_model_names


def test_model_collection_with_non_concrete_models():
    my_setup('reserved_keyword_checker.tests.test_app.test_app.settings')
    models = collect_concrete_models()

    expected_model_names = ['BasicModel', 'MixedModel', 'ModelWithAbstractParent']

    assert sorted(models['non_concrete_app'].keys()) == expected_model_names

def test_model_collection_with_third_party_app():
    assert False


def test_field_collection_with_inheritance():
    my_setup('reserved_keyword_checker.tests.test_app.test_app.settings')
    from test_app.local_app import models as local_models
    model = local_models.GrandchildModel
    model_fields = get_fields_per_model(model)
    expected_field_names = [
        'end', 'first_name', 'last_name', 'middle_name', 'nick_name', 'start'
    ]
    assert sorted(model_fields) == expected_field_names


def test_field_collection_with_non_concrete_parents():
    my_setup('reserved_keyword_checker.tests.test_app.test_app.settings')
    from test_app.non_concrete_app import models as non_concrete_models
    model = non_concrete_models.ModelWithAbstractParent
    model_fields = get_fields_per_model(model)
    expected_field_names = [
        'end_date', 'start_date'
    ]
    assert sorted(model_fields) == expected_field_names


def test_field_collection_from_third_party_app():
    assert False


def test_reserved_keyword_detection():
    my_setup('reserved_keyword_checker.tests.test_app.test_app.settings')
    from test_app.local_app import models as local_models
    reserved_keywords = {
        'MYSQL': ['start', 'end', 'nick_name'],
        'STITCH': ['start', 'end', 'password']
    }
    model = local_models.GrandchildModel
    violations = check_model_for_violations(model, reserved_keywords)
    violation_strings = map(lambda v: v.report_string(), violations)
    expected_violations = [
        'MYSQL,local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,end,Source',
        'MYSQL,local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,nick_name,',
        'MYSQL,local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,start,',
        'STITCH,local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,end,Source',
        'STITCH,local,local_app,reserved_keyword_checker/tests/test_app/local_app/models.py,GrandchildModel,start,',
    ]
    assert sorted(violation_strings) == expected_violations
