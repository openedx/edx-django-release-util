import sys

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from release_util.management.commands import MigrationSession


class Command(BaseCommand):
    """
    Given a YAML file containing apps and migrations, apply those app migrations.
    The YAML format for the apps/migrations is:

    migrations:
      - [app1, 0001_initial]
      - [app2, 0012_otherthing]
      - [app1, 0002_somthing]
    initial_states:
      - app1:
        - zero
      - app2:
        - 0011_beforetheotherthing

    If an error occurs in any of the migrations, the migrations are halted at that point
        and the status is recorded in an artifact.
    The output of the command is in YAML format and specifies the following:
        - migrations that run successfully and how long they took
        - migrations that failed and how long the failure took
        - migrations that unapplied due to previous failures
    The output YAML format:

    success:
    - migration: [app1, 0001_initial]
      output: Applying app1.0001_initial... OK
    failure:
      migration: [app2, 0012_otherthing]
      duration: 43.39
      output: <All migration output>
      traceback: <Entire traceback>
    unapplied:
    - [app1, 0002_something]
    rollback_commands:
    - [python, manage.py, migrate, app1, zero]

    If an output file is specified, the YAML output is also directed to that file.

    Rollbacks due to migration failures are left to the mgmt command user.
    """
    help = "Given a YAML file containing apps and migrations, apply those app migrations."

    def add_arguments(self, parser):
        parser.add_argument(
            'input_file',
            type=str,
            nargs='?',
            help="DEPRECATED (unused): Filename from which apps/migrations will be read."
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
            help="Filename to which migration results will be written."
        )

    def handle(self, *args, **kwargs):
        migrator = MigrationSession(self.stderr, kwargs['database'])

        failure = False
        try:
            migrator.apply_all()
        except CommandError as e:
            self.stderr.write("Migration error: {}".format(e))
            failure = True

        self.stdout.write(migrator.state())
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(migrator.state())

        sys.exit(int(failure))
