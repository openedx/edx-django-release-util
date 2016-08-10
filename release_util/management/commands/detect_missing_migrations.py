import sys

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.questioner import InteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState
from django.db.utils import OperationalError


class Command(BaseCommand):
    """
    Detect if any apps have missing migration files.
    Does *not* check to see if the existing migrations have been applied.
    """
    help = "Detect if any apps have missing migration files."

    def handle(self, *args, **kwargs):

        changed = set()

        self.stdout.write("Checking...")
        for db in settings.DATABASES.keys():

            try:
                executor = MigrationExecutor(connections[db])
            except OperationalError:
                self.stdout.write("Unable to check migrations: cannot connect to database '{}'.\n".format(db))
                sys.exit(1)

            all_apps = apps.app_configs.keys()
            questioner = InteractiveMigrationQuestioner(specified_apps=all_apps, dry_run=True)

            autodetector = MigrationAutodetector(
                executor.loader.project_state(),
                ProjectState.from_apps(apps),
                questioner,
            )

            changed.update(autodetector.changes(graph=executor.loader.graph, convert_apps=all_apps).keys())

        if changed:
            self.stdout.write(
                "Apps with model changes but no corresponding migration file: {!r}\n".format(
                    list(changed)
                )
            )
            sys.exit(1)
        else:
            self.stdout.write("All migration files present.\n")
            sys.exit(0)
