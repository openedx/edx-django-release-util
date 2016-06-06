from cStringIO import StringIO
from mock import patch, Mock
import contextlib
from path import Path as path
import yaml

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

    def _check_command_output(self, cmd, cmd_kwargs, output, exit_value, yaml_output=False):
        out = StringIO()
        with patch('sys.exit') as exit_mock:
            call_command(cmd, stdout=out, verbosity=0, **cmd_kwargs)
            self.assertTrue(exit_mock.called)
            exit_mock.assert_called_once_with(exit_value)
        if yaml_output:
            # Ensure the command output is parsable as YAML -and- is the expected YAML.
            parsed_yaml = yaml.load(out.getvalue())
            self.assertTrue(isinstance(parsed_yaml, dict))
            self.assertEqual(yaml.dump(output), yaml.dump(parsed_yaml))
        else:
            self.assertEqual(output, out.getvalue().replace('\n', ''))

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
                "show_unapplied_migrations",
                {'fail_on_unapplied': fail_on_unapplied},
                {'migrations': {'release_util': [u'0001_initial', u'0002_second']}},
                exit_code,
                yaml_output=True
            )

        call_command("migrate", "release_util", "0001", verbosity=0)

        for fail_on_unapplied, exit_code in (
            (True, 1),
            (False, 0),
        ):
            self._check_command_output(
                "show_unapplied_migrations",
                {'fail_on_unapplied': fail_on_unapplied},
                {'migrations': {'release_util': [u'0002_second']}},
                exit_code,
                yaml_output=True
            )

        call_command("migrate", "release_util", "0002", verbosity=0)

        for fail_on_unapplied, exit_code in (
            (True, 0),
            (False, 0),
        ):
            self._check_command_output(
                "show_unapplied_migrations",
                {'fail_on_unapplied': fail_on_unapplied},
                {'migrations': {}},
                exit_code,
                yaml_output=True
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
                "detect_missing_migrations",
                {},
                "Checking...Apps with model changes but no corresponding migration file: ['release_util']",
                1
            )

    def test_no_missing_migrations(self):
        """
        In the current repo state, verify that there are no missing migrations.
        """
        self._check_command_output(
            "detect_missing_migrations",
            {},
            "Checking...All migration files present.",
            0
        )
