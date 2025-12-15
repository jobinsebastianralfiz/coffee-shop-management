"""
Management command to generate QR codes for tables that don't have them.
"""

from django.core.management.base import BaseCommand

from apps.tables.models import Table
from apps.tables.utils import generate_table_qr_code


class Command(BaseCommand):
    help = "Generate QR codes for tables that don't have them"

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Regenerate QR codes for all tables (not just missing ones)',
        )
        parser.add_argument(
            '--outlet',
            type=int,
            help='Only generate for specific outlet ID',
        )

    def handle(self, *args, **options):
        regenerate_all = options.get('all', False)
        outlet_id = options.get('outlet')

        # Build queryset
        tables = Table.objects.select_related('floor__outlet')

        if outlet_id:
            tables = tables.filter(floor__outlet_id=outlet_id)

        if not regenerate_all:
            # Only tables without QR codes
            tables = tables.filter(qr_code='')

        total = tables.count()

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS('No tables need QR code generation.')
            )
            return

        self.stdout.write(f'Generating QR codes for {total} tables...')

        success_count = 0
        error_count = 0

        for table in tables:
            try:
                qr_file = generate_table_qr_code(table)
                table.qr_code.save(qr_file.name, qr_file, save=True)
                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  Generated QR for table {table.number} ({table.floor.name})')
                )
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  Failed for table {table.number}: {str(e)}')
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f'Successfully generated {success_count} QR codes.')
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Failed to generate {error_count} QR codes.')
            )
