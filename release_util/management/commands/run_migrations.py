import sys

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS

from release_util.management.commands import MigrationSession, dump_migration_session_state


class Command(BaseCommand):
    """
    Runs all migrations for a database.

    If an error occurs in any of the migrations, the migrations are halted at that point
        and the status is recorded in an artifact.
    The output of the command is in YAML format and specifies the following:
        - migrations that run successfully and how long they took
        - migrations that failed and how long the failure took
    The output YAML format:

    - migration: "all"
      duration: float,
      output: str,
      success: [(app: str, migration_name: str), ...],
      failure: ("app": str, "migration_name": str) | !!null,
      traceback: str | !!null,
      succeeded: bool,

    migration: This will always be "all" for compatibility reasons
    duration:  The amount of time in seconds it took to run
    output:    The stdout of the manage.py migrate command that applied the migrations
    succeeded_migrations:
               A list of migration tuples that succeeded
    failed_migration:
               The migration that failed if any
    traceback: The traceback with which the migration failed if any
    succeeded: Whether the step succeeded. Note a migration step can fail
               even when all the individual migrations succeed (thus
               traceback != None and failure == None)

    The list will always have only one item.

    If an output file is specified, the YAML output is also directed to that file.

    Rollbacks due to migration failures are left to the mgmt command user.
    """
    help = "Run all migrations for a database"

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

        state = dump_migration_session_state(migrator.state)
        self.stdout.write(state)
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(state)

        sys.exit(int(failure))
