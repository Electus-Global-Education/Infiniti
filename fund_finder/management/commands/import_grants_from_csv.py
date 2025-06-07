# fund_finder/management/commands/import_grants_from_csv.py
import csv
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Imports grant opportunities from a Grants.gov CSV file.

    Maps the CSV columns to the FunderProfile and GrantOpportunity models.
    Uses the 'OPPORTUNITY NUMBER' from the CSV as a unique source_id.

    Example usage:
    - python manage.py import_grants_from_csv /path/to/your/Grants-Export.csv
    """
    help = 'Imports grant opportunities from a Grants.gov CSV data file.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file_path', type=str, help='The full path to the CSV data file.')

    def _clean_decimal(self, value):
        """Helper to convert string to decimal, returns None if empty or invalid."""
        if value is None or value.strip() == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _clean_date(self, value):
        """Helper to parse date string, returns None if invalid."""
        if not value:
            return None
        # Try different formats if needed. Grants.gov often uses "Mon-DD-YYYY HH:MM:SS AM/PM TZ"
        # For simplicity, we'll try a common parse. A more robust solution might try several formats.
        try:
            # Example: Jun-06-2025 03:28:33 PM EST
            # Python's parse_datetime is quite flexible
            return parse_datetime(value.replace(' EST', ' -0500').replace(' EDT', ' -0400'))
        except Exception:
            return None

    def handle(self, *args, **options):
        csv_file_path = options['csv_file_path']
        self.stdout.write(self.style.SUCCESS(f"Starting import from CSV file: {csv_file_path}"))

        try:
            with open(csv_file_path, mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Get or create the system-level "Government" FunderType
                gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)

                created_count = 0
                updated_count = 0

                for row in reader:
                    try:
                        opportunity_number = row.get('OPPORTUNITY NUMBER')
                        if not opportunity_number:
                            self.stderr.write(self.style.WARNING(f"Skipping row with no OPPORTUNITY NUMBER."))
                            continue

                        agency_name = row.get('AGENCY NAME', 'Unknown Government Funder').strip()
                        funder, _ = FunderProfile.objects.get_or_create(
                            name=agency_name,
                            defaults={
                                'funder_type': gov_funder_type,
                                'agency_code': row.get('AGENCY CODE'),
                                'contact_info': f"{row.get('GRANTOR CONTACT')} - {row.get('GRANTOR CONTACT EMAIL')}"
                            }
                        )
                        
                        defaults = {
                            'funder': funder,
                            'title': row.get('OPPORTUNITY TITLE'),
                            'description': row.get('FUNDING DESCRIPTION', 'No description provided.'),
                            'status': row.get('OPPORTUNITY STATUS', 'POSTED').upper(),
                            'version': row.get('VERSION'),
                            'estimated_total_funding': self._clean_decimal(row.get('ESTIMATED TOTAL FUNDING')),
                            'award_floor': self._clean_decimal(row.get('AWARD FLOOR')),
                            'award_ceiling': self._clean_decimal(row.get('AWARD CEILING')),
                            'expected_number_of_awards': int(row['EXPECTED NUMBER OF AWARDS']) if row.get('EXPECTED NUMBER OF AWARDS') else None,
                            'cost_sharing_requirement': row.get('COST SHARING / MATCH REQUIREMENT', 'Not Specified'),
                            'funding_instrument_type': row.get('FUNDING INSTRUMENT TYPE'),
                            'funding_activity_category': row.get('CATEGORY OF FUNDING ACTIVITY'),
                            'assistance_listings': row.get('ASSISTANCE LISTINGS'),
                            'posted_date': self._clean_date(row.get('POSTED DATE')),
                            'close_date': self._clean_date(row.get('CLOSE DATE')),
                            'last_updated_date': self._clean_date(row.get('LAST UPDATED DATE/TIME')),
                            'is_active': row.get('OPPORTUNITY STATUS', '').lower() == 'posted',
                        }
                        
                        grant_obj, created = GrantOpportunity.objects.update_or_create(
                            source_name='CSV_UPLOAD',
                            source_id=opportunity_number,
                            defaults=defaults
                        )

                        if created: created_count += 1
                        else: updated_count += 1
                        
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing row for opp# {opportunity_number}: {e}"))

        except FileNotFoundError:
            raise CommandError(f"CSV file not found at: {csv_file_path}")
        except Exception as e:
            raise CommandError(f"An unexpected error occurred: {e}")

        self.stdout.write(self.style.SUCCESS(f"CSV Import complete. Created: {created_count}, Updated: {updated_count}"))
