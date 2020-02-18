"""
reserved_keyword_checker.py

A utility for analyzing a Django application to see if any of the model fields
have names that are on a list of reseverd keywords. Certain tools used for downstream
data storage and analysis, like Stitch, have restrictions for which column names they
allow. Modifying existing field names in a live Django application is a complicated,
long and potentially risky operation. This tool allows you to prevent new fields from
being added to the application that would break these rules. It does so by loading the
app and inspecting the models of both the locally defined models and third party
installed apps.

EXAMPLE USAGE:

python reserved_keyword_checker.py --reserved_keyword_file reserved_keywords.yml --override_file overrides.yml --report_path reports

> reserved_keywords.yml: a yaml file containing a mapping of tool (i.e. Snowflake) to a
  list of reserved keywords for that technology
> overrides.yml: a yaml file containing a list of model fields to ignore when scanning
  for reserved keyword violations.
> reports: a path in which to write a csv report of the violations found with this script
"""

import inspect
import io
import re
import os
import sys

import click
import django
import yaml
from django.db import models


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
        keyword_data_string = (
            self.system, app_source, app_name, self.module_name, model_name, self.field, source
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
        Return whether or not this violation was found in a local source file or a third
        party installed app
        """
        return os.path.isfile(self.module_name)


class ConfigurationException(Exception):
    pass


class Config(object):
    """
    A collection of configuration data used throughout this script
    """

    def __init__(self, reserved_keyword_config_file, override_file, report_path):
        self.reserved_keyword_config = self.read_config_file(reserved_keyword_config_file)
        if override_file:
            self.overrides = self.read_config_file(override_file)
        else:
            self.overrides = {}
        self.validate_override_config()
        self.report_path = report_path
        self.report_file = os.path.join(report_path, "reserved_keyword_report.csv")

    @staticmethod
    def read_config_file(config_file_path):
        click.echo("Loading config file: {}".format(config_file_path))
        try:
            with io.open(config_file_path, 'r') as config_file:
                config_dict = yaml.safe_load(config_file)
        except:
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
                        click.secho('Model names must be camel case', fg="red")
                        raise ValueError()
                    if check(field_name) or check(model_name):
                        click.secho('Invalid character found', fg="red")
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
            not model is models.Model and
            not model._meta.abstract and
            not model._meta.proxy
        )

    concrete_models = set()

    click.echo("Collecting all concrete models in installed apps")
    for app in django.apps.apps.get_app_configs():
        click.echo("Inspecting app: {}".format(app))
        app_models = []
        for root_model in app.get_models():

            model_hierarchy = inspect.getmro(root_model)
            for model in model_hierarchy:
                if is_concrete(model):
                    model_name = model._meta.object_name
                    concrete_models.add(model)
                    app_models.append(model_name)
        if app_models:
            click.echo("Found models: {}".format(','.join(app_models)))

    click.echo("Collected {} concrete models".format(len(concrete_models)))
    return list(concrete_models)


def get_fields_per_model(model):
    """
    Given a model, return a list of all of the field names on the model,
    regardless of whether they are explicitly present or present through
    inheritance. Do not include hidden fields, as these are not created
    in app code.
    """
    return [
        f.column
        for f in  model._meta.get_fields(include_hidden=False)
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
            if field in config.reserved_keyword_config[system]:
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
                    click.secho("Violation detected but on whitelist: {}".format(violation), fg="yellow")
                else:
                    click.secho("Violation detected: {}".format(violation), fg="red")
    return violations


def generate_report(violations, config):
    """
    Generate a csv file report for the violations that were detected.
    """
    if not os.path.isdir(config.report_path):
        os.mkdir(config.report_path)
    click.echo("Writing report to {}".format(config.report_file))
    with io.open(config.report_file, 'w') as report_file:
        for violation in violations:
            report_file.write("{}\n".format(violation.report_string()))
    click.echo(
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
        click.secho("Found reserved keyword conflicts!", fg="red")
        sys.exit(1)
    else:
        click.echo("No reserved keyword conflicts detected")
        sys.exit(0)


@click.command()
@click.option(
    '--reserved_keyword_file',
    default='reserved_keywords.yml',
    help='Path to the configuration file containing the lists of reserved keywords to check for',
    type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
@click.option(
    '--override_file',
    default=None,
    help='Path to the configuration file containing the lists of reserved keywords that can be excluded from analysis',
    type=click.Path(exists=False, dir_okay=False, resolve_path=True)
)
@click.option(
    '--report_path',
    default='reports',
    help='Path to write a report file containing all of the reserved keyword violations',
    type=click.Path(dir_okay=True, resolve_path=True)
)
def cli(
    reserved_keyword_file,
    override_file,
    report_path,
):
    django.setup()
    config = Config(reserved_keyword_file, override_file, report_path)
    concrete_models = collect_concrete_models()
    violations = []
    click.echo("Checking models for reserved keyword violations")
    click.echo("#"*80)
    for model in concrete_models:
        violations += check_model_for_violations(model, config)
    click.echo("#"*80)
    generate_report(violations, config)
    set_status(violations, config)

if __name__ == '__main__':
    cli()
