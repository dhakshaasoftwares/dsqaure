"""
Prepare a client install: company settings row, default roles, units,
construction stages, agreement template and document numbering, plus an
optional country preset. Safe to run again – it never overwrites edits.

    python manage.py setup_defaults                 # no country-specific rules
    python manage.py setup_defaults --preset india  # INR, GST, sample PF / ESI / PT rules (switched off)
"""

from django.core.management.base import BaseCommand

from apps.core.setup import COUNTRY_PRESETS, ensure_defaults


class Command(BaseCommand):
    help = "Create default configuration for a new client install"

    def add_arguments(self, parser):
        parser.add_argument("--preset", choices=sorted(COUNTRY_PRESETS), default=None)

    def handle(self, *args, preset, **options):
        for name in ensure_defaults(preset):
            self.stdout.write(f"Added pay rule (switched off – review and switch on): {name}")
        self.stdout.write(self.style.SUCCESS("Setup complete."))
