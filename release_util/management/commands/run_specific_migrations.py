from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from release_util.management.commands import MigrationSession
import sys, yaml

class Command(BaseCommand):
    """docstring"""
    help = ""

    def add_arguments(self, parser):
        parser.add_argument(
            '--migration',
            type=str,
            nargs=2,
            metavar=('APP', 'MIGRATION_NUMBER'),
            action='append',
            required=True,
            help='App-migration pair to migrate to',
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
        migrator = MigrationSession(self.stderr, kwargs['database'], migrations=kwargs['migration'])
        
        failure = False
        try:
            migrator.apply()
        except Exception as e:
            self.stderr.write("Migration error: {}".format(e))
            failure = True

        state = yaml.safe_dump(migrator.state)
        self.stdout.write(state)
        if kwargs['output_file']:
            with open(kwargs['output_file'], 'w') as outfile:
                outfile.write(state)

        sys.exit(int(failure))
