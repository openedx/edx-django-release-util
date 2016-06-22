import sys
import traceback
import yaml
from cStringIO import StringIO
from timeit import default_timer
from collections import defaultdict

from django.core.management import call_command, CommandError
from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError


class MigrationSession(object):
    """
    Class which is initialized with Django app/model migrations to perform.
    Performs migrations while keeping track of the state of each migration.
    Provides the state of all migrations on demand.
    """
    def __init__(self, input_yaml, stderr):
        self.to_apply = []
        self.migration_state = {
            'success': [],
            'failure': None,
            'unapplied': [],
            'rollback_commands': [],
        }
        self.timer = default_timer
        self.stderr = stderr

        # Load the passed-in YAML into a dictionary.
        self.input_migrations = yaml.safe_load(input_yaml)

        # Build a list of migrations to apply in order.
        for migration in self.input_migrations['migrations']:
            self.to_apply.append(migration)

    def more_to_apply(self):
        """
        Returns True if more migrations remain to apply in this session, else False.
        """
        return len(self.to_apply) > 0

    def _add_rollback_commands(self):
        """
        Generate rollback commands for the apps that have had migrations applied.
        If an app's migration has failed, include that rollback command as well.
        """
        apps_to_rollback = set()
        # Add the apps with successfully applied migrations.
        apps_to_rollback.update([m['migration'][0] for m in self.migration_state['success']])
        # If an app migration failed, include that rollback also.
        if self.migration_state['failure']:
            apps_to_rollback.add(self.migration_state['failure']['migration'][0])
        for app in apps_to_rollback:
            initial_app_state = None
            for initial in self.input_migrations['initial_states']:
                if app == initial[0]:
                    initial_app_state = initial
                    break
            if not initial_app_state:
                raise CommandError('App "{}" not found in initial migration states.'.format(app))
            self.migration_state['rollback_commands'].append(
                [
                    'python', 'manage.py', 'migrate',
                    app,
                    initial_app_state[1]
                ]
            )

    def _apply_next(self):
        """
        Applies the next-in-line Django model migration.
        """
        if not self.more_to_apply():
            return

        app, migration = self.to_apply.pop(0)

        out = StringIO()
        start = self.timer()
        try:
            call_command("migrate", app_label=app, migration_name=migration, noinput=True, stdout=out)
        except (CommandError, DatabaseError) as e:
            time_to_fail = self.timer() - start
            exc_type, exc_value, exc_traceback = sys.exc_info()
            # Assumed that only a single migration failure will occur.
            self.migration_state['failure'] = {
                'migration': [app, migration],
                'duration': time_to_fail,
                'output': out.getvalue(),
                'traceback': repr(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            }
            # Add the remaining migrations to the unapplied status.
            while self.more_to_apply():
                app_migration = self.to_apply.pop(0)
                self.migration_state['unapplied'].append(app_migration)
            # Find the apps that have been applied -or- failed.
            # Include their initial migrations as commands.
            self._add_rollback_commands()
            raise CommandError("Migration failed for app '{}' - migration '{}'.\n".format(app, migration))

        time_to_apply = self.timer() - start
        self.migration_state['success'].append({
            'migration': [app, migration],
            'duration': time_to_apply,
            'output': out.getvalue(),
        })

    def apply_all(self):
        """
        Apply all the migrations.
        """
        while self.more_to_apply():
            self._apply_next()
        self._add_rollback_commands()

    def state(self):
        """
        Returns the current state as a YAML string.
        """
        return yaml.dump(self.migration_state)


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
      duration: 3.45
      output: All good!
    failure:
      migration: [app2, 0012_otherthing]
      output: This migration has failed!!!!
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
            type=unicode,
            nargs='?',
            help="Filename from which apps/migrations will be read."
        )
        parser.add_argument(
            '--output_file',
            dest='output_file',
            default=None,
            help="Filename to which migration results will be written."
        )

    def handle(self, *args, **kwargs):
        with open(kwargs['input_file'], 'r') as f:
            input_yaml = f.read()
        migrator = MigrationSession(input_yaml, self.stderr)

        failure = False
        try:
            migrator.apply_all()
        except CommandError as e:
            self.stderr.write("Migration error: {}".format(e.message))
            failure = True

        self.stdout.write(migrator.state())
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(migrator.state())

        sys.exit(int(failure))
