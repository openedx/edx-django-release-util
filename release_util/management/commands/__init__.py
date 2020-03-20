"""
Common release_util code used by management commands.
"""
import re
import sys
import traceback
from copy import deepcopy
from timeit import default_timer

import yaml
from django.core.management import CommandError, call_command
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from six import StringIO


def dump_migration_session_state(raw):
    """
    Serialize a migration session state to yaml using nicer formatting

    Args:
        raw: object to serialize
    Returns: string (of yaml)

    Specifically, this forces the "output" member of state step dicts (e.g.
    state[0]['output']) to use block formatting. For example, rather than this:

    - migration: [app, migration_name]
      output: "line 1\nline2\nline3"

    You get this:

    - migration: [app, migration_name]
      output: |
        line 1
        line 2
        line 3
    """
    class BlockStyle(str):
        pass

    class SessionDumper(yaml.SafeDumper):
        pass

    def str_block_formatter(dumper, data):
        return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='|')
    SessionDumper.add_representer(BlockStyle, str_block_formatter)

    raw = deepcopy(raw)
    for step in raw:
        step['output'] = BlockStyle(step['output'])
        step['traceback'] = BlockStyle(step['traceback'])
    return yaml.dump(raw, Dumper=SessionDumper)


def _remove_escape_characters(s):
    """
    Returns a string identical to the intput (s) but with escape characters removed
    """
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', s)


class MigrationSessionError(ValueError):
    pass


class MigrationSession(object):
    """
    Class which performs migrations while keeping track of the state of each migration.
    Provides the state of all migrations post-migration.

    If you want to run specific migrations, you can either initialize it with
    a list of migration tuples, or add migrations by calling add_migrations(),
    then call apply().

    If you want to run all migrations, simply call apply_all(). Calling
    apply_all() while a MigrationSession has migrations added to it will raise
    an error.

    Once either apply() or apply_all() has been called, calling apply(),
    apply_all(), or add_migrations() will raise a MigrationSessionError.

    MigrationSession.state is a list of "step" dicts of the following form:
    [
        {
            'migration': 'all' | (app: str, migration_name: str),
            'duration': float,
            'output': str,
            'success': [(app: str, migration_name: str), ...],
            'failure': (app: str, migration_name: str) | None,
            'traceback': str | None,
            'succeeded': bool,
        },
        ...
    ]

    migration: The tuple of the requested migration that triggered the step
    duration:  The amount of time in seconds it took to run the step
    output:    The stdout of the manage.py migrate command that applied the migrations
    succeeded_migrations:
               A list of migration tuples that succeeded
    failed_migration:
               The migration that failed if any
    traceback: The traceback with which the migration failed if any
    succeeded: Whether the step succeeded. Note a migration step can fail
               even when all the individual migrations succeed (thus
               traceback != None and failure == None)

    Even when applied with specific migrations, there's no guarantee that no
    other migrations will run because each migration might have dependencies.
    Thus, MigrationSession.state is a list of "steps", where each step is a
    single migration state that was requested.

    For example, if you run MigrationSession(None, database_name, (myapp, 0003)).apply()
    and myapp.0003 depends on myapp.0002, the state will consist of a single
    step with "migration" == ("myapp", "0003") and (hopefully)
    "success" = [("myapp", "0002"), ("myapp", "0003")].
    """
    def __init__(self, stderr, database_name, migrations=None):
        """
        Args:
            stderr: deprecated. This value is not used.
            database_name: the name of the database to use
            migrations: see add_migrations()
        """
        self._to_apply = []
        self._migration_state = []
        self._timer = default_timer
        self.__closed = False
        self._database_name = database_name

        if migrations:
            self.add_migrations(migrations)

        # Regex built to match migration output like this line:
        #    Applying release_util.0001_initial...  OK
        # Full output will look like:
        #     Operations to perform:
        #       Target specific migration: 0005_alter_user_last_login_null, from auth
        #     Running migrations:
        #       Rendering model states... DONE
        #       Applying contenttypes.0001_initial... OK
        #       Applying auth.0001_initial... OK
        #       Applying auth.0002_alter_permission_name_max_length... OK
        #       Applying auth.0003_alter_user_email_max_length... OK
        #       Applying auth.0004_alter_user_username_opts... OK
        #       Applying auth.0005_alter_user_last_login_null... OK
        # The last line might be missing the "OK" if it failed
        self.migration_regex = re.compile(
            r'Applying (?P<app_name>[^.]+)\.(?P<migration_name>[^.]+)[. ]+(?P<success>(OK)?)$'
        )

    def add_migrations(self, migrations):
        """
        Add migrations to be applied.

        Args:
            migrations: a list of migrations to add of the form [(app, migration_name), ...]
        Raises:
            MigrationSessionError if called on a closed MigrationSession
        """
        if self.__closed:
            raise MigrationSessionError("Can't change applied session")
        self._to_apply.extend(migrations)

    def _get_unapplied_migrations(self, loader):
        """
        Output a list of unapplied migrations in the form [['migration1', migration2'], ...].
        This implementation is mostly copied from the Django 'showmigrations' mgmt command.
        https://github.com/django/django/blob/stable/1.8.x/django/core/management/commands/showmigrations.py

        This should only be called from _get_current_migration_state().
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

    def _get_current_migration_state(self, loader, apps):
        """
        Extract the most recent migrations from the relevant apps.
        If no migrations have been performed, return 'zero' as the most recent migration for the app.

        This should only be called from list_migrations().
        """
        # Only care about applied migrations for the passed-in apps.
        # Remove duplicates and preserve order of the list.
        apps = [app for index, app in enumerate(apps) if app not in apps[:index]]
        relevant_applied = [migration for migration in loader.applied_migrations if migration[0] in apps]
        # Sort them by the most recent migration and convert to a dictionary,
        # leaving apps as keys and most recent migration as values.
        # NB: this is a dirty trick
        most_recents = dict(sorted(relevant_applied, key=lambda m: m[1]))
        # Fill in the apps with no migrations with 'zero'.
        # NOTE: Unicode Django application names are unsupported.
        most_recents = [[app, 'zero' if app not in most_recents else str(most_recents[app])] for app in apps]
        return most_recents

    def list_migrations(self):
        """
        Returns a tuple of unapplied, current

        "Unapplied" is a list of unapplied migrations. "Current" is a list of the current migration
        states for apps with unapplied migrations.

        Both are tuples of the form (app, migration_name).
        """
        connection = connections[self._database_name]
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        unapplied = self._get_unapplied_migrations(loader)
        currents = self._get_current_migration_state(loader, [u[0] for u in unapplied])
        return unapplied, currents

    def _parse_migrate_output(self, output):
        """
        Args:
            output: str, output of "manage.py migrate"
        Returns (succeeded: list(tuple), failed: tuple or None)
        Both tuples are of the form (app, migration)
        """
        failed = None
        succeeded = []

        # Mark migrations:
        # - before exception migration as success
        # - exception migration as failed
        for line in output.split('\n'):
            line = _remove_escape_characters(line).strip()
            line_match = self.migration_regex.match(line)
            if line_match:
                migration = (line_match.group('app_name'), line_match.group('migration_name'))
                if line_match.group('success') == 'OK':
                    # The migration succeeded
                    succeeded.append(migration)
                else:
                    # The migration failed
                    failed = migration
                    break
        return succeeded, failed

    def __apply(self, migration=None, run_all=False):
        """
        If a migration is supplied, runs that migration and appends to state.
        If run_all==True, runs all migrations.
        Raises a ValueError if neither "migration" nor "run_all" are provided.
        """
        out = StringIO()
        trace = None

        migrate_kwargs = {
            'interactive': False,
            'stdout': out,
            'database': self._database_name,
        }
        if migration is not None:
            migrate_kwargs.update({
                'app_label': migration[0],
                'migration_name': migration[1],
            })
        elif not run_all:
            raise ValueError('Either a migration must be provided or "run_all" must be True')

        start = self._timer()
        try:
            call_command("migrate", **migrate_kwargs)
        except Exception:
            trace = ''.join(traceback.format_exception(*sys.exc_info()))
        finally:
            end = self._timer()
            successes, failure = self._parse_migrate_output(out.getvalue())

            self._migration_state.append({
                'database': self._database_name,
                'migration': 'all' if run_all else (migration[0], migration[1]),
                'duration': end - start,
                'output': _remove_escape_characters(out.getvalue()),
                'succeeded_migrations': successes,        # [(app, migration), ...]
                'failed_migration': failure,              # (app, migration)
                'traceback': trace,
                'succeeded': failure is None and trace is None,
            })

        if failure is not None:
            raise CommandError("Migration failed for app '{}' - migration '{}'.\n".format(*failure))
        elif trace is not None:
            raise CommandError("Migrations failed unexpectedly. See self.state['traceback'] for details.")

    def apply(self):
        """
        Applies all migrations that have been added.
        Note that some migrations depend on others, so you might end up
        running more than one.
        """
        if self.__closed:
            raise MigrationSessionError("Can't apply applied session")
        try:
            while self._to_apply:
                self.__apply(migration=self._to_apply.pop(0))
        except:  # noqa
            raise
        finally:
            self.__closed = True

    def apply_all(self):
        """
        Applies all Django model migrations at once, recording the result.
        """
        if self.__closed:
            raise MigrationSessionError("Can't apply applied session")
        if self._to_apply:
            raise MigrationSessionError("Can't apply_all with migrations added to session")

        try:
            self.__apply(run_all=True)
        except:  # noqa
            raise
        finally:
            self.__closed = True

    @property
    def state(self):
        """
        Returns the current state
        """
        return self._migration_state
