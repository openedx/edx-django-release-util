from cStringIO import StringIO
from mock import patch, Mock
import contextlib
from path import Path as path
import yaml
import tempfile

from django.test import TransactionTestCase
from django.core.management import call_command, CommandError
from django.db.utils import OperationalError
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
import release_util


@contextlib.contextmanager
def remove_and_restore_models(apps):
    """
    This context manager exists to remove application models from Django in order
    to simulate them not being present in the application's models.py file.
    It's used to test that missing migrations are properly detected.
    """
    def create_projectstate_wrapper(wrapped_func):
        # pylint: disable=missing-docstring
        wrapped_func = wrapped_func.__func__

        def _modify_app_models(*args, **kwargs):
            app_models = wrapped_func(*args, **kwargs)
            new_app_models = {}
            for model_key, model_value in app_models.models.iteritems():
                if model_key not in apps:
                    new_app_models[model_key] = model_value
            return ProjectState(new_app_models)

        return classmethod(_modify_app_models)

    old_from_apps = ProjectState.from_apps
    ProjectState.from_apps = create_projectstate_wrapper(ProjectState.from_apps)
    try:
        yield
    finally:
        ProjectState.from_apps = old_from_apps


class MigrationCommandsTests(TransactionTestCase):
    """
    Tests running the management commands related to migrations.
    """
    multi_db = True

    def _null_certain_fields(self, status):
        """
        When comparing the status of a migration run, some fields won't match the test data.
        So set those fields to None before comparing.
        """
        def _null_migration_values(status):
            if status:
                for key in status.keys():
                    if key in ('duration', 'output', 'traceback'):
                        status[key] = None
        for migration_data in status['success']:
            _null_migration_values(migration_data)
        _null_migration_values(status['failure'])
        return status

    def _check_command_output(self, cmd, cmd_args=(), cmd_kwargs={}, output='', err_output='', exit_value=0):
        """
        Run a mgmt command and perform comparisons on the output with what is expected.
        """
        out = StringIO()
        err = StringIO()
        # Run command.
        with patch('sys.exit') as exit_mock:
            call_command(cmd, stdout=out, stderr=err, verbosity=0, *cmd_args, **cmd_kwargs)
            self.assertTrue(exit_mock.called)
            exit_mock.assert_called_once_with(exit_value)
        # Check command output.
        if cmd in ('show_unapplied_migrations', 'run_migrations'):
            parsed_yaml = yaml.safe_load(out.getvalue())
            self.assertTrue(isinstance(parsed_yaml, dict))
            if cmd == 'show_unapplied_migrations':
                # Ensure the command output is parsable as YAML -and- is exactly the expected YAML.
                self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
            elif cmd == 'run_migrations':
                # Don't compare all the fields - some fields will have variable output values.
                parsed_yaml = self._null_certain_fields(parsed_yaml)
                self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
        else:
            self.assertEqual(output, out.getvalue().replace('\n', ''))
        # Check command error output.
        self.assertEqual(err_output, err.getvalue().replace('\n', ''))


    def test_showmigrations_list(self):
        """
        Tests output of the show_unapplied_output mgmt command.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        for fail_on_unapplied, exit_code in (
            (True, 1),
            (False, 0),
        ):
            self._check_command_output(
                cmd="show_unapplied_migrations",
                cmd_kwargs={'fail_on_unapplied': fail_on_unapplied},
                output={
                    'initial_states': [['release_util', 'zero']],
                    'migrations': [
                        ['release_util', '0001_initial'],
                        ['release_util', '0002_second'],
                    ]
                },
                exit_value=exit_code
            )

        call_command("migrate", "release_util", "0001", verbosity=0)

        for fail_on_unapplied, exit_code in (
            (True, 1),
            (False, 0),
        ):
            self._check_command_output(
                cmd="show_unapplied_migrations",
                cmd_kwargs={'fail_on_unapplied': fail_on_unapplied},
                output={
                    'initial_states': [['release_util', '0001_initial']],
                    'migrations': [
                        ['release_util', '0002_second']
                    ]
                },
                exit_value=exit_code
            )

        call_command("migrate", "release_util", "0002", verbosity=0)

        for fail_on_unapplied, exit_code in (
            (True, 0),
            (False, 0),
        ):
            self._check_command_output(
                cmd="show_unapplied_migrations",
                cmd_kwargs={'fail_on_unapplied': fail_on_unapplied},
                output={
                    'initial_states': [],
                    'migrations': []
                },
                exit_value=exit_code
            )

        # Cleanup by unmigrating everything
        call_command("migrate", "release_util", "zero", verbosity=0)

    def test_missing_migrations(self):
        """
        In the current repo state, there are no missing migrations.
        Make Django forget about the models in the release_util app's models.py file.
        Then verify that migrations are missing.
        """
        with remove_and_restore_models([('release_util', 'book'), ('release_util', 'author')]):
            self._check_command_output(
                cmd="detect_missing_migrations",
                output="Checking...Apps with model changes but no corresponding migration file: ['release_util']",
                exit_value=1
            )

    def test_no_missing_migrations(self):
        """
        In the current repo state, verify that there are no missing migrations.
        """
        self._check_command_output(
            cmd="detect_missing_migrations",
            output="Checking...All migration files present.",
        )

    def test_run_migrations_success(self):
        """
        Test the migration success path.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        input_yaml = """
        migrations:
          - [release_util, 0001_initial]
          - [release_util, 0002_second]
        initial_states:
          - [release_util, zero]
        """
        output = {
            'success': [
                {
                    'migration': ['release_util', '0001_initial'],
                    'duration': None,
                    'output': None
                },
                {
                    'migration': ['release_util', '0002_second'],
                    'duration': None,
                    'output': None
                },
            ],
            'failure': None,
            'unapplied': [],
            'rollback_commands': [
                ['python', 'manage.py', 'migrate', 'release_util', 'zero'],
            ],
        }

        out_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file.write(input_yaml)
        in_file.flush()

        # Check the stdout output against the expected output.
        self._check_command_output(
            cmd="run_migrations",
            cmd_args=(in_file.name,),
            cmd_kwargs={'output_file': out_file.name},
            output=output,
        )
        in_file.close()

        # Check the contents of the output file against the expected output.
        with open(out_file.name, 'r') as f:
            output_yaml = f.read()
        parsed_yaml = yaml.safe_load(output_yaml)
        self.assertTrue(isinstance(parsed_yaml, dict))
        parsed_yaml = self._null_certain_fields(parsed_yaml)
        self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
        out_file.close()

    def test_run_migrations_failure(self):
        """
        Test the first migration failing.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        input_yaml = """
        migrations:
          - [release_util, 0001_initial]
          - [release_util, 0002_second]
        initial_states:
          - [release_util, zero]
        """
        output = {
            'success': [],
            'failure': {
                'migration': ['release_util', '0001_initial'],
                'duration': None,
                'output': None,
                'traceback': None,
            },
            'unapplied': [
                ['release_util', '0002_second'],
            ],
            'rollback_commands': [
                ['python', 'manage.py', 'migrate', 'release_util', 'zero'],
            ],
        }

        out_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file.write(input_yaml)
        in_file.flush()

        with patch('django.core.management.commands.migrate.Command.handle') as handle_mock:
            handle_mock.side_effect = CommandError("BIG ERROR!")
            # Check the stdout output.
            self._check_command_output(
                cmd="run_migrations",
                cmd_args=(in_file.name,),
                cmd_kwargs={'output_file': out_file.name},
                output=output,
                err_output="Migration error: Migration failed for app 'release_util' - migration '0001_initial'.",
                exit_value=1
            )
        in_file.close()
        out_file.close()
