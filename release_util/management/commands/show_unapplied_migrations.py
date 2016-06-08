import re
import sys
import json
from cStringIO import StringIO
from collections import defaultdict
import yaml

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.utils import OperationalError
from django.db.migrations.loader import MigrationLoader
from django.db import DEFAULT_DB_ALIAS, connections

class Command(BaseCommand):
    """
    Checks for unapplied migrations.
    Prints out a YAML string of any unapplied migrations, along with their accompanying application name.
    For example:
    migrations:
      - app1:
        - 0001_initial
        - 0002_something
    If all migrations are applied, returns an empty YAML "migrations" dict.
    This command can be used in a couple of ways:
    1) To generate a list of unapplied migrations
    2) To detect if any unapplied migrations exist and failing if so (by specifying '--fail_on_unapplied')
    """
    help = "Prints out a YAML string of any unapplied migrations, along with their accompanying application name."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail_on_unapplied',
            dest='fail_on_unapplied',
            action='store_true',
            help="If flag specified, command will exit with a non-zero value when unapplied migrations exist.",
        )
        parser.add_argument(
            '--database',
            dest='database',
            default=DEFAULT_DB_ALIAS,
            help='Nominates a database to synchronize. Defaults to the "default" database.',
        )
        parser.add_argument(
            '--output_file',
            dest='output_file',
            default=None,
            help="Filename to which output should be written."
        )

    def _gather_unapplied_migrations(self, *args, **kwargs):
        """
        Output a dictionary of unapplied migrations in the form {'app1': ['migration1', migration2']}.
        This implementation is mostly copied from the Django 'showmigrations' mgmt command.
        https://github.com/django/django/blob/stable/1.8.x/django/core/management/commands/showmigrations.py
        """
        unapplied = defaultdict(list)
        db = kwargs['database']
        connection = connections[db]
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        graph = loader.graph
        app_names = sorted(loader.migrated_apps)
        # For each app, print its migrations in order from oldest (roots) to
        # newest (leaves).
        for app_name in app_names:
            shown = set()
            for node in graph.leaf_nodes(app_name):
                for plan_node in graph.forwards_plan(node):
                    if plan_node not in shown and plan_node[0] == app_name:
                        if not plan_node in loader.applied_migrations:
                            unapplied[app_name].append(plan_node[1])
                        shown.add(plan_node)
        return dict(unapplied)

    def handle(self, *args, **kwargs):
        unapplied = self._gather_unapplied_migrations(self, *args, **kwargs)

        # Compose the output YAML.
        yaml_output = "migrations:\n  {}".format(yaml.dump(unapplied))

        # Output the composed YAML.
        self.stdout.write(yaml_output)
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(yaml_output)

        if kwargs['fail_on_unapplied'] and unapplied:
            sys.exit(1)
        else:
            sys.exit(0)
