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
    Prints out a YAML string of any unapplied migrations, along with their accompanying application name *and*
    the initial migration state of every application with unapplied migrations.
    For example:

    migrations:
      - [app1, 0001_initial]
      - [app2, 0012_otherthing]
      - [app1, 0002_somthing]
    initial_states: {app1: zero, app2: 0011_thisthing}

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

    def _gather_unapplied_migrations(self, loader):
        """
        Output a dictionary of unapplied migrations in the form {'app1': ['migration1', migration2']}.
        This implementation is mostly copied from the Django 'showmigrations' mgmt command.
        https://github.com/django/django/blob/stable/1.8.x/django/core/management/commands/showmigrations.py
        """
        unapplied = []
        graph = loader.graph
        plan = []
        seen = set()

        # Generate the plan, in the order that migrations have been/should be applied.
        for target in graph.leaf_nodes():
            for migration in graph.forwards_plan(target):
                if migration not in seen:
                    plan.append(graph.nodes[migration])
                    seen.add(migration)

        # Remove the migrations that have already been applied.
        for migration in plan:
            if not (migration.app_label, migration.name) in loader.applied_migrations:
                # NOTE: Unicode Django application names are unsupported.
                unapplied.append([migration.app_label, str(migration.name)])
        return unapplied

    def _gather_current_migration_state(self, loader, apps):
        """
        Extract the most recent migrations from the relevant apps.
        If no migrations have been performed, return 'zero' as the most recent migration for the app.
        """
        # Only care about applied migrations for the passed-in apps.
        apps = set(apps)
        relevant_applied = [migration for migration in loader.applied_migrations if migration[0] in apps]
        # Sort them by the most recent migration and convert to a dictionary,
        # leaving apps as keys and most recent migration as values.
        most_recents = dict(sorted(relevant_applied, key=lambda m: m[1], reverse=True))
        # Fill in the apps with no migrations with 'zero'.
        # NOTE: Unicode Django application names are unsupported.
        most_recents = [[app, 'zero' if not app in most_recents else str(most_recents[app])] for app in apps]
        return most_recents

    def _gather_migration_info(self, *args, **kwargs):
        """
        Return:
            - the unapplied migrations from each app
            - the initial migration state of any app with unapplied migrations
        """
        db = kwargs['database']
        connection = connections[db]
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        unapplied = self._gather_unapplied_migrations(loader)
        currents = self._gather_current_migration_state(loader, [u[0] for u in unapplied])
        return {'migrations': unapplied, 'initial_states': currents}

    def handle(self, *args, **kwargs):
        migration_info = self._gather_migration_info(self, *args, **kwargs)

        # Compose the output YAML.
        yaml_output = yaml.dump(migration_info)

        # Output the composed YAML.
        self.stdout.write(yaml_output)
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(yaml_output)

        if kwargs['fail_on_unapplied'] and migration_info['migrations']:
            sys.exit(1)
        else:
            sys.exit(0)
