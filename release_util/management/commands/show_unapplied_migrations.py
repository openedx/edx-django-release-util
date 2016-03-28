import re
import sys
import json
from cStringIO import StringIO

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.utils import OperationalError


class Command(BaseCommand):
    """
    Checks for unapplied migrations.
    Prints out a JSON string of any unapplied migrations, along with their accompanying application name.
    For example:
    [["app1", "0001_initial"], ["app1", "0002_something"]]
    If all migration are applied, returns an empty list.
    """
    help = "Prints out a JSON string of any unapplied migrations, along with their accompanying application name."

    def handle(self, *args, **kwargs):

        unapplied = []

        out = StringIO()
        ansi_escape = re.compile(r'\x1b[^m]*m')
        for db in settings.DATABASES.keys():

            try:
                call_command("showmigrations", database=db, stdout=out, format="list")
            except OperationalError:
                self.stderr.write("Unable to check migrations: cannot connect to database '{}'.\n".format(db))
                self.stdout.write("null")
                sys.exit(1)

            for line in out.getvalue().split('\n'):
                line = ansi_escape.sub('', line)
                if not line.startswith(' '):
                    # This is an application line.
                    current_app = line.strip()
                elif '[ ]' in line:
                    unapplied.append((current_app, line.strip().replace('[ ] ', '')))

        if unapplied:
            self.stdout.write(json.dumps(unapplied))
            sys.exit(1)
        else:
            self.stdout.write("[]")
            sys.exit(0)
