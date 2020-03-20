"""
check_reserved_keywords.py

A utility for analyzing a Django application to see if any of the model fields
have names that are on a list of reseverd keywords. Certain tools used for downstream
data storage and analysis, like Stitch, have restrictions for which column names they
allow. Modifying existing field names in a live Django application is a complicated,
long and potentially risky operation. This tool allows you to prevent new fields from
being added to the application that would break these rules. It does so by loading the
app and inspecting the models of both the locally defined models and third party
installed apps.

EXAMPLE USAGE:

python manage.py check_reserved_keywords.py --reserved_keyword_file reserved_keywords.yml \
--override_file overrides.yml --report_path reports

OPTIONS:

* --reserved_keyword_file: pass a yaml file containing a mapping of tool (i.e. Snowflake) to a
  list of reserved keywords for that technology
* --override_file: pass a yaml file containing a list of model fields to ignore when scanning
  for reserved keyword violations.
* --report_path: pass a path in which to write a csv report of the violations found with this script.
"""

import argparse
import inspect
import io
import logging
import os
import sys
from os.path import dirname

import django
import six
import yaml
from django.apps import apps
from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import models

if six.PY2:
    FileNotFoundError = IOError

log = logging.getLogger(__name__)


class Violation(object):
    """
    A Django model field name that is in conflict with a defined list of reserved keywords
    """

    def __init__(self, model, field_name, system, override=False):
        self.model = model
        self.field = field_name
        self.system = system
        self.override = override

    def __str__(self):
        return "{} conflict in {}:{}:{}.{}".format(
            self.system,
            self.model._meta.app_label,
            self.module_name,
            self.model._meta.concrete_model.__name__,
            self.field
        )

    def report_string(self):
        """
        Generate a comma-separated string used for creating a report of the reserved
        keywords that were found. Output should be returned with the following fields:
        - system: the system/tool that has the restriction that triggered the violation
        - app source: was the violation detected in a locally defined or third party installed
          application
        - app_name: name of the Django app that contains the violation
        - module_name: the file path of the Python module containing the violation
        - model_name: name of the Django model that contains the violation
        - field: the actual offending field name that triggered the violation
        - source: is this module/model where the offending field was defined, or was it
          inherited from another model.
        """
        model_name = self.model._meta.concrete_model.__name__
        app_name = self.model._meta.app_label
        if self.local_app:
            app_source = "Local"
        else:
            app_source = "3rd party"
        if not self.inherited:
            source = "Class Definition"
        else:
            source = "Inherited"
        if self.override:
            override_string = "Overridden"
        else:
            override_string = ""
        keyword_data_string = (
            self.system, app_source, app_name, self.module_name, model_name, self.field,
            source, override_string
        )
        return ",".join(keyword_data_string)

    @property
    def module_name(self):
        """
        The path to the module containing the reserved keyword violation
        """
        module_string = self.model._meta.concrete_model.__module__.replace('.', '/')
        return "{}.py".format(module_string)

    @property
    def inherited(self):
        """
        Return whether or not this violation is defined in a parent model of the model
        in which it was found
        """
        return self.field not in [f.name for f in self.model._meta.local_fields]

    @property
    def local_app(self):
        """
        Return whether or not this violation was found in a local source file or a package
        installed in the Python environment running this code. In this case, 'local' means
        in the source code files in the directory that this is being run in. This can be
        determined by checking if the Django app containing this violation is in env
        """
        # This will return the path to the virtualenv/python installation being used to
        # run this django app (i.e. /edx/app/credentials/venvs/credentials)
        env_base_path = dirname(dirname(sys.executable))
        app_path = apps.get_app_config(self.model._meta.app_label).path
        return env_base_path not in app_path


class ConfigurationException(Exception):
    pass


class Config(object):
    """
    A collection of configuration data used throughout this script
    """

    def __init__(self, reserved_keyword_config_file, override_file, report_path, system):
        reserved_keyword_config = self.read_config_file(reserved_keyword_config_file)
        if system:
            try:
                self.reserved_keyword_config = {system: reserved_keyword_config[system]}
            except KeyError:
                raise ConfigurationException(
                    "Parameter {} missing from config file {}".format(system, reserved_keyword_config_file)
                )
        else:
            self.reserved_keyword_config = reserved_keyword_config
        if override_file:
            self.overrides = self.read_config_file(override_file)
        else:
            self.overrides = {}
        self.validate_override_config()
        self.report_path = report_path
        self.report_file = os.path.join(report_path, "reserved_keyword_report.csv")

    @staticmethod
    def read_config_file(config_file_path):
        log.info("Loading config file: {}".format(config_file_path))
        try:
            config_dict = yaml.safe_load(config_file_path)
            # for ease of use later in this script, change keys without values from None to empty lists
            for key in config_dict.keys():
                if not config_dict[key]:
                    config_dict[key] = []
        except (yaml.parser.ParserError, FileNotFoundError):
            raise ConfigurationException("Unable to load config file: {}".format(config_file_path))
        if not config_dict:
            raise ConfigurationException("Config file is empty: {}".format(config_file_path))
        return config_dict

    def validate_override_config(self):
        invalid_chars = [' ', ',', '-']
        def check(s): return any([c in invalid_chars for c in s])
        for system, override_list in self.overrides.items():
            for pattern in override_list:
                try:
                    model_name, field_name = pattern.split('.')
                    if not model_name[0].isupper():
                        log.error('Model names must be camel case')
                        raise ValueError()
                    if check(field_name) or check(model_name):
                        log.error('Invalid character found')
                        raise ValueError()
                except ValueError:
                    raise ConfigurationException("Invalid value in override file: {}".format(pattern))


def collect_concrete_models():
    """
    Walk through all of the INSTALLED_APPS in a Django project, gathering all
    of the 'concrete' models. In this case, 'concrete' refers to the fact
    that a model has a corresponding table within a database (as opposed to
    an abstract model, which does not). For more information, see:
    https://openedx.atlassian.net/wiki/spaces/PLAT/pages/895287378/OEP-30+Implementation
    """
    def is_concrete(model):
        return (
            issubclass(model, models.Model) and
            model is not models.Model and
            not model._meta.abstract and
            not model._meta.proxy
        )

    concrete_models = set()

    log.info("Collecting all concrete models in installed apps")
    for app in django.apps.apps.get_app_configs():
        log.info("Inspecting app: {}".format(app.label))
        app_models = []
        for root_model in app.get_models():

            model_hierarchy = inspect.getmro(root_model)
            for model in model_hierarchy:
                if is_concrete(model):
                    model_name = model._meta.object_name
                    concrete_models.add(model)
                    app_models.append(model_name)
        if app_models:
            log.info("Found models: {}".format(','.join(app_models)))

    log.info("Collected {} concrete models".format(len(concrete_models)))
    return list(concrete_models)


def get_fields_per_model(model):
    """
    Given a model, return a list of all of the field names on the model,
    regardless of whether they are explicitly present or present through
    inheritance. Do not include hidden fields, as these are not created
    in app code.
    """
    def _get_db_field_name(field):
        """
        Get the actual name that will be used to name the column for this
        model field. These can be overridden with the 'db_column' field.
        """
        if hasattr(field, 'db_column') and field.db_column is not None:
            return field.db_column
        else:
            return field.column

    return [
        _get_db_field_name(f)
        for f in model._meta.get_fields(include_hidden=False)
        if not f.auto_created
    ]


def check_model_for_violations(model, config):
    """
    See if any of the fields in a given model are in conflict with the list
    of reserved keyword names. Return a list of any such violations.
    """
    violations = []

    for field in get_fields_per_model(model):
        for system in config.reserved_keyword_config.keys():
            reserved_keywords = [rkw.lower() for rkw in config.reserved_keyword_config[system]]
            if field in reserved_keywords:
                full_field_name = "{}.{}".format(
                    model._meta.concrete_model.__name__,
                    field
                )
                if system in config.overrides.keys() and full_field_name in config.overrides[system]:
                    override = True
                else:
                    override = False
                violation = Violation(model, field, system, override)
                violations.append(violation)
                if override:
                    log.warn("Violation detected but on whitelist: {}".format(violation))
                else:
                    log.error("Violation detected: {}".format(violation))
    return violations


def generate_report(violations, config):
    """
    Generate a csv file report for the violations that were detected.
    """
    if not os.path.isdir(config.report_path):
        os.mkdir(config.report_path)
    log.info("Writing report to {}".format(config.report_file))
    with io.open(config.report_file, 'w') as report_file:
        for violation in violations:
            report_file.write("{}\n".format(violation.report_string()))
    log.info(
        "Successfully wrote {} violations to report".format(len(violations))
    )


def set_status(violations, config):
    """
    set the exit code of this script, depending on whether or not there are
    any reserved keyword Violations detected that are not on the override
    list
    """
    valid_violations = list(
        filter(lambda v: v not in config.overrides, violations)
    )
    if len(valid_violations) > 0:
        raise CommandError("Found reserved keyword conflicts!")
    else:
        log.info("No reserved keyword conflicts detected")


class writable_dir(argparse.Action):
    """
    A custom argparse action to check that a given argument value represents a writable directory.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("{} is not a valid path".format(prospective_dir))
        elif not os.access(prospective_dir, os.W_OK):
            raise argparse.ArgumentTypeError("{} is not a readable dir".format(prospective_dir))
        else:
            setattr(namespace, self.dest, prospective_dir)


class Command(BaseCommand):
    help = (
        'Check a Django application to see if any of the model fields have names that are on a list of reseverd '
        'keywords.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reserved_keyword_file',
            default=os.path.join(os.path.dirname(__file__), 'default_reserved_keywords.yml'),
            help='Path to the configuration file containing the lists of reserved keywords to check for.',
            type=argparse.FileType('r', encoding='UTF-8'),
        )
        parser.add_argument(
            '--override_file',
            default=None,
            help=(
                'Path to the configuration file containing the lists of '
                'reserved keywords that can be excluded from analysis'
            ),
            type=argparse.FileType('r', encoding='UTF-8'),
        )
        parser.add_argument(
            '--report_path',
            default='reports',
            help='Path to write a report file containing all of the reserved keyword violations',
            action=writable_dir,
        )
        parser.add_argument(
            '--system',
            default=None,
            help="Specific system list in 'reserved_keyword_file' to check for (i.e. MYSQL)"
        )

    def handle(self, *args, **options):
        config = Config(
            options['reserved_keyword_file'], options['override_file'], options['report_path'], options['system']
        )
        concrete_models = collect_concrete_models()
        violations = []
        log.info("Checking models for reserved keyword violations")
        for model in concrete_models:
            violations += check_model_for_violations(model, config)
        generate_report(violations, config)
        set_status(violations, config)
