"""
Common release_util code used by management commands.
"""
import re
import sys
import traceback
from timeit import default_timer
import yaml
from django.core.management import call_command, CommandError
from django.db.utils import DatabaseError
from six import StringIO


class MigrationSessionDeprecated(object):
    """
    DEPRECATED:
    Class which is initialized with Django app/model migrations to perform.
    Performs migrations while keeping track of the state of each migration.
    Provides the state of all migrations on demand.
    """

    def __init__(self, input_yaml, stderr, database_name):
        self.to_apply = []
        self.migration_state = {
            'success': [],
            'failure': None,
            'unapplied': [],
            'rollback_commands': [],
        }
        self.timer = default_timer
        self.stderr = stderr
        self.database_name = database_name

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
        DEPRECATED:
        Applies the next-in-line Django model migration.
        """
        if not self.more_to_apply():
            return

        app, migration = self.to_apply.pop(0)

        out = StringIO()
        start = self.timer()
        try:
            call_command("migrate",
                         app_label=app,
                         migration_name=migration,
                         interactive=False,
                         stdout=out,
                         database=self.database_name)
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

    def apply_all_one_by_one(self):
        """
        DEPRECATED:
        Apply all the migrations, executing each migration individually.
        """
        while self.more_to_apply():
            self._apply_next()
        self._add_rollback_commands()

    def state(self):
        """
        Returns the current state as a YAML string.
        """
        return yaml.safe_dump(self.migration_state)


class MigrationSession(object):
    """
    Class which performs migrations while keeping track of the state of each migration.
    Provides the state of all migrations post-migration.
    """
    def __init__(self, stderr, database_name):
        self.to_apply = []
        self.migration_state = {
            'success': [],
            'failure': None,
            'unapplied': [],
            'rollback_commands': [],
        }
        self.timer = default_timer
        self.stderr = stderr
        self.database_name = database_name

        # Execute command to find/record the unapplied migrations.
        out = StringIO()
        call_command("show_unapplied_migrations",
                     interactive=False,
                     stdout=out,
                     database=self.database_name,
                     standalone=False)

        # Load the passed-in YAML into a dictionary.
        self.input_migrations = yaml.safe_load(out.getvalue())

        # Build a list of migrations that will be applied.
        for migration in self.input_migrations['migrations']:
            self.to_apply.append(migration)

        # Regex built to match migration output like this line:
        #    Applying release_util.0001_initial...  OK
        self.migration_regex = re.compile(r'Applying (?P<app_name>[^\.]+)\.(?P<migration_name>[^\.]+)[\. ]+(?P<success>[OK]*)$')

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

    def _apply_all(self):
        """
        Applies all Django model migrations at once, recording the result.
        """
        def _remove_escape_characters(s):
            ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
            return ansi_escape.sub('', s)

        out = StringIO()
        start = self.timer()
        try:
            call_command("migrate",
                         interactive=False,
                         stdout=out,
                         database=self.database_name)
        except (CommandError, DatabaseError) as e:
            time_to_fail = self.timer() - start
            exc_type, exc_value, exc_traceback = sys.exc_info()

            # Parse the output to discover the last migration being applied before the exception.
            # Mark migrations:
            # - before exception migration as success
            # - exception migration as failed
            # - any remaining exceptions as unapplied
            for line in out.getvalue().split('\n'):
                line = _remove_escape_characters(line).strip()
                line_match = self.migration_regex.match(line)
                if line_match:
                    migration = [line_match.group('app_name'), line_match.group('migration_name')]
                    if line_match.group('success') == 'OK':
                        # A migration succeeded.
                        self.migration_state['success'].append({
                            'migration': migration,
                            'output': line,
                        })
                    else:
                        # This migration failed.
                        failed_app, failed_migration = migration
                        self.migration_state['failure'] = {
                            'migration': migration,
                            'output': out.getvalue(),
                            'traceback': repr(traceback.format_exception(exc_type, exc_value, exc_traceback)),
                        }
                        # Save the total migration time until failure.
                        self.migration_state['duration'] = time_to_fail
                        break

            # Remove any migrations that succeeded -or- failed.
            # Any leftover migrations were *not* applied.
            succeeded = [status['migration'] for status in self.migration_state['success']]
            failed = []
            if failed_app and failed_migration:
                failed = [failed_app, failed_migration]
            for migration in self.to_apply:
                if migration not in succeeded and migration != failed:
                    self.migration_state['unapplied'].append(migration)

            # Find the apps that have been applied -or- failed.
            # Include their initial migrations as commands.
            self._add_rollback_commands()
            raise CommandError("Migration failed for app '{}' - migration '{}'.\n".format(failed_app, failed_migration))

        # All migrations succeeded. Record the total time for all migrations.
        time_to_apply = self.timer() - start
        self.migration_state['duration'] = time_to_apply

        # Parse the output to find all migrations that were applied successfully.
        for line in out.getvalue().split('\n'):
            line = _remove_escape_characters(line).strip()
            line_match = self.migration_regex.match(line)
            if line_match:
                migration = [line_match.group('app_name'), line_match.group('migration_name')]
                if line_match.group('success') == 'OK':
                    # A migration succeeded.
                    self.migration_state['success'].append({
                        'migration': migration,
                        'output': line,
                    })

    def apply_all(self):
        """
        Apply all the migrations together.
        """

        self._apply_all()
        self._add_rollback_commands()

    def state(self):
        """
        Returns the current state as a YAML string.
        """
        return yaml.safe_dump(self.migration_state)
