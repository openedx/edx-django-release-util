import contextlib
import sys
import tempfile
from datetime import datetime
from unittest import skip

import ddt
import six
import yaml
from django.core.management import CommandError, call_command
from django.db import connection
from django.db.migrations.state import ProjectState
from django.test import TransactionTestCase
from mock import patch

import release_util.management.commands.generate_history
import release_util.tests.migrations.test_migrations
from release_util.management.commands import MigrationSession
from release_util.tests.models import Foo, HistoricalFoo


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
            for model_key, model_value in six.iteritems(app_models.models):
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


class GenerateHistoryTest(TransactionTestCase):

    def setUp(self):
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(Foo)
            schema_editor.create_model(HistoricalFoo)

    def tearDown(self):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(Foo)
            schema_editor.delete_model(HistoricalFoo)

    def test_history_generation(self):
        row1 = Foo.objects.create(name='row1')
        row2 = Foo.objects.create(name='row2')
        row3 = Foo.objects.create(name='row3')

        rows = [row2, row3]

        # A row with existing history
        historical_row1 = HistoricalFoo.objects.create(
            id=1,
            name='row1',
            history_date=datetime.today().strftime('%Y-%m-%d'),
            history_change_reason='initial history population',
            history_type='~',
            history_user_id=None,
        )

        with patch.object(
            release_util.management.commands.generate_history.Command,
            'columns_from_schema', return_value=['id', 'name']
        ):
            call_command('generate_history', tables=["test_app_foo"], batchsize=1)

        self.assertEqual(HistoricalFoo.objects.count(), 3)

        historical_rows = HistoricalFoo.objects.filter(id__in=[2, 3])

        for row, historical_row in zip(rows, historical_rows):
            self.assertEqual(historical_row.id, row.id)
            self.assertEqual(historical_row.name, row.name)
            self.assertEqual(historical_row.history_date, datetime.today().strftime('%Y-%m-%d'))
            self.assertEqual(historical_row.history_change_reason, 'initial history population')
            self.assertEqual(historical_row.history_type, '+')
            self.assertEqual(historical_row.history_user_id, None)

        # Test no-op as all rows would now have history
        with patch.object(
            release_util.management.commands.generate_history.Command,
            'columns_from_schema', return_value=['id', 'name']
        ):
            call_command('generate_history', tables=["test_app_foo"], batchsize=1)

        self.assertEqual(HistoricalFoo.objects.count(), 3)


@ddt.ddt
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

        for one_status in status:
            _null_migration_values(one_status)
        return status

    def _check_command_output(self, cmd, cmd_args=(), cmd_kwargs={}, output='', err_output='', exit_value=0):
        """
        Run a mgmt command and perform comparisons on the output with what is expected.
        """
        out = six.StringIO()
        err = six.StringIO()
        # Run command.
        with patch('sys.exit') as exit_mock:
            call_command(cmd, stdout=out, stderr=err, verbosity=0, *cmd_args, **cmd_kwargs)
            self.assertTrue(exit_mock.called)
            exit_mock.assert_called_once_with(exit_value)
        # Check command output.
        if cmd.startswith(('show_unapplied_migrations', 'run_migrations')):
            parsed_yaml = yaml.safe_load(out.getvalue())
            if cmd == 'show_unapplied_migrations':
                self.assertTrue(isinstance(parsed_yaml, dict))
            else:
                self.assertTrue(isinstance(parsed_yaml, list))
            if cmd == 'show_unapplied_migrations':
                # Ensure the command output is parsable as YAML -and- is exactly the expected YAML.
                self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
            elif cmd.startswith('run_migrations'):
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
                    'database': 'default',
                    'initial_states': [{'app': 'release_util', 'migration': 'zero'}],
                    'migrations': [
                        {'app': 'release_util', 'migration': '0001_initial'},
                        {'app': 'release_util', 'migration': '0002_second'},
                        {'app': 'release_util', 'migration': '0003_third'},
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
                    'database': 'default',
                    'initial_states': [{'app': 'release_util', 'migration': '0001_initial'}],
                    'migrations': [
                        {'app': 'release_util', 'migration': '0002_second'},
                        {'app': 'release_util', 'migration': '0003_third'},
                    ]
                },
                exit_value=exit_code
            )

        call_command("migrate", "release_util", "0002", verbosity=0)

        for fail_on_unapplied, exit_code in (
                (True, 1),
                (False, 0),
        ):
            self._check_command_output(
                cmd="show_unapplied_migrations",
                cmd_kwargs={'fail_on_unapplied': fail_on_unapplied},
                output={
                    'database': 'default',
                    'initial_states': [{'app': 'release_util', 'migration': '0002_second'}],
                    'migrations': [
                        {'app': 'release_util', 'migration': '0003_third'},
                    ]
                },
                exit_value=exit_code
            )

        call_command("migrate", "release_util", "0003", verbosity=0)

        for fail_on_unapplied, exit_code in (
                (True, 0),
                (False, 0),
        ):
            self._check_command_output(
                cmd="show_unapplied_migrations",
                cmd_kwargs={'fail_on_unapplied': fail_on_unapplied},
                output={
                    'database': 'default',
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

    @skip('')
    def test_run_migrations_success_one_by_one(self):
        """
        DEPRECATED:
        Test the migration success path.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        input_yaml = """
        database: 'default',
        migrations:
          - [release_util, 0001_initial]
          - [release_util, 0002_second]
          - [release_util, 0003_third]
        initial_states:
          - [release_util, zero]
        """
        output = {
            'database': 'default',
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
                {
                    'migration': ['release_util', '0003_third'],
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
        in_file.write(input_yaml.encode('utf-8'))
        in_file.flush()

        # Check the stdout output against the expected output.
        self._check_command_output(
            cmd='run_migrations_one_by_one',
            cmd_args=(in_file.name,),
            cmd_kwargs={'output_file': out_file.name},
            output=output,
        )
        in_file.close()

        # Check the contents of the output file against the expected output.
        with open(out_file.name, 'r') as f:
            output_yaml = f.read()
        parsed_yaml = yaml.safe_load(output_yaml)
        self.assertTrue(isinstance(parsed_yaml, list))
        parsed_yaml = self._null_certain_fields(parsed_yaml)
        self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
        out_file.close()

    def test_run_migrations_success(self):
        """
        Test the migration success path.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        input_yaml = """
        database: 'default',
        migrations:
          - [release_util, 0001_initial]
          - [release_util, 0002_second]
          - [release_util, 0003_third]
        initial_states:
          - [release_util, zero]
        """
        output = [
            {
                'database': 'default',
                'duration': None,
                'failed_migration': None,
                'migration': 'all',
                'output': None,
                'succeeded_migrations': [
                    ['release_util', '0001_initial'],
                    ['release_util', '0002_second'],
                    ['release_util', '0003_third'],
                ],
                'traceback': None,
                'succeeded': True,
            },
        ]

        out_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file.write(input_yaml.encode('utf-8'))
        in_file.flush()

        # Check the stdout output against the expected output.
        self._check_command_output(
            cmd='run_migrations',
            cmd_args=(in_file.name,),
            cmd_kwargs={'output_file': out_file.name},
            output=output,
        )
        in_file.close()

        # Check the contents of the output file against the expected output.
        with open(out_file.name, 'r') as f:
            output_yaml = f.read()
        parsed_yaml = yaml.safe_load(output_yaml)
        self.assertTrue(isinstance(parsed_yaml, list))
        parsed_yaml = self._null_certain_fields(parsed_yaml)
        self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
        out_file.close()

    @ddt.data(
        (
            '0001_initial',
            [
                {
                    'database': 'default',
                    'failed_migration': ['release_util', '0001_initial'],
                    'migration': 'all',
                    'succeeded_migrations': [],
                    'duration': None,
                    'output': None,
                    'traceback': None,
                    'succeeded': False,
                }
            ],
        ),
        (
            '0002_second',
            [
                {
                    'database': 'default',
                    'failed_migration': ['release_util', '0002_second'],
                    'migration': 'all',
                    'succeeded_migrations': [['release_util', '0001_initial'], ],
                    'duration': None,
                    'output': None,
                    'traceback': None,
                    'succeeded': False,
                }
            ],
        ),
        (
            '0003_third',
            [
                {
                    'database': 'default',
                    'failed_migration': ['release_util', '0003_third'],
                    'migration': 'all',
                    'succeeded_migrations': [
                        ['release_util', '0001_initial'],
                        ['release_util', '0002_second'],
                    ],
                    'duration': None,
                    'output': None,
                    'traceback': None,
                    'succeeded': False,
                }
            ],
        ),
    )
    @ddt.unpack
    def test_run_migrations_failure(self, migration_name, migration_output):
        """
        Test the first, second, and last migration failing.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        input_yaml = """
        database: 'default',
        migrations:
          - [release_util, 0001_initial]
          - [release_util, 0002_second]
          - [release_util, 0003_third]
        initial_states:
          - [release_util, zero]
        """
        out_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file = tempfile.NamedTemporaryFile(suffix='.yml')
        in_file.write(input_yaml.encode('utf-8'))
        in_file.flush()

        # A bogus class for creating a migration object that will raise a CommandError.
        class MigrationFail(object):
            atomic = False

            def state_forwards(self, app_label, state):
                pass

            def database_forwards(self, app_label, schema_editor, from_state, to_state):
                raise CommandError("Yo")

        # Insert the bogus object into the first operation of a migration.
        current_migration_list = \
            release_util.tests.migrations.test_migrations.__dict__[migration_name].__dict__['Migration'].operations
        current_migration_list.insert(0, MigrationFail())

        try:
            # Check the stdout output.
            self._check_command_output(
                cmd="run_migrations",
                cmd_args=(in_file.name,),
                cmd_kwargs={'output_file': out_file.name},
                output=migration_output,
                err_output="Migration error: Migration failed for app 'release_util' - migration '{}'.".format(
                    migration_name
                ),
                exit_value=1
            )
        finally:
            # Whether the test passes or fails, always pop the failure migration of the list.
            current_migration_list.pop(0)

        in_file.close()
        out_file.close()

    @ddt.data(
        ('Applying app1.9999_final... OK', True, True),
        ('Applying crazy_app.11111111_n_e_w_f_i_e_l_d... ', True, False),
        ('Applying .0001_dot_with_no_app... ', False, False),
        ('Applying 0001_no_app... ', False, False),
        ('Applying testapp.0001_copious_space_b4_OK...                    OK', True, True),
        ('Applying testapp.0001_no_space_between_dot_and_OK...OK', True, True),
        ('Applying testapp.0001_lowercase_OK... ok', False, False),
        ('Applying testapp.amigration_with_no_number... ', True, False),
        ('Applying testapp.amigration... KOK', False, False),
    )
    @ddt.unpack
    def test_migration_regex(self, status_string, is_match, success):
        migrator = MigrationSession(sys.stderr, 'default')
        match = migrator.migration_regex.match(status_string)
        self.assertEqual(is_match, match is not None)
        if match:
            self.assertEqual(success, match.group('success') == 'OK')
