import sys

import yaml
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from release_util.management.commands import MigrationSession


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
    initial_states:
      - [app1, zero]
      - [app2, 0011_thisthing]

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

    def handle(self, *args, **kwargs):
        session = MigrationSession(None, kwargs['database'])
        unapplied, current = session.list_migrations()

        # Compose the output YAML.
        yaml_output = yaml.safe_dump({'migrations': unapplied, 'initial_states': current})

        # Output the composed YAML.
        self.stdout.write(yaml_output)
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(yaml_output)

        if kwargs['fail_on_unapplied'] and unapplied:
            sys.exit(1)
        else:
            sys.exit(0)
