from cStringIO import StringIO
from mock import patch, Mock
import contextlib
from path import Path as path

from django.test import TransactionTestCase
from django.core.management import call_command
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

    def _check_command_output(self, command, output, exit_value):
        out = StringIO()
        with patch('sys.exit') as exit_mock:
            call_command(command, stdout=out, verbosity=0)
            self.assertTrue(exit_mock.called)
            exit_mock.assert_called_once_with(exit_value)
        self.assertEqual(output, out.getvalue().replace('\n', ''))

    def test_showmigrations_list(self):
        """
        Tests output of the show_unapplied_output mgmt command.
        """
        # Using TransactionTestCase sets up the migrations as set up for the test.
        # Reset the release_util migrations to the very beginning - i.e. no tables.
        call_command("migrate", "release_util", "zero", verbosity=0)

        self._check_command_output(
            "show_unapplied_migrations",
            "Checking... Unapplied migrations: [('release_util', '0001_initial'), ('release_util', '0002_second')]",
            1
        )

        call_command("migrate", "release_util", "0001", verbosity=0)

        self._check_command_output(
            "show_unapplied_migrations",
            "Checking... Unapplied migrations: [('release_util', '0002_second')]",
            1
        )

        call_command("migrate", "release_util", "0002", verbosity=0)

        self._check_command_output(
            "show_unapplied_migrations",
            "Checking... All migration files have been applied.",
            0
        )

        # Cleanup by unmigrating everything
        call_command("migrate", "release_util", "zero", verbosity=0)

    @patch.object(MigrationLoader, '__init__')
    def test_bogus_db(self, init_error_mock):
        """
        Ensure that an inaccesible DB throws the proper error.
        """
        init_error_mock.side_effect = OperationalError
        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command("show_unapplied_migrations", stdout=out, verbosity=0)
        self.assertEqual(
            "Checking... Unable to check migrations: cannot connect to database 'default'.",
            out.getvalue().replace('\n', '')
        )

    def test_missing_migrations(self):
        """
        In the current repo state, there are no missing migrations.
        Make Django forget about the models in the release_util app's models.py file.
        Then verify that migrations are missing.
        """
        with remove_and_restore_models([('release_util', 'book'), ('release_util', 'author')]):
            self._check_command_output(
                "detect_missing_migrations",
                "Checking...Apps with model changes but no corresponding migration file: ['release_util']",
                1
            )

    def test_no_missing_migrations(self):
        """
        In the current repo state, verify that there are no missing migrations.
        """
        self._check_command_output(
            "detect_missing_migrations",
            "Checking...All migration files present.",
            0
        )
