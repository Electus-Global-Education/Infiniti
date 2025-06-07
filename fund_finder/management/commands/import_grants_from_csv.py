# fund_finder/management/commands/import_grants_from_csv.py
import csv
import re
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Imports grant opportunities from a Grants.gov CSV file.

    This version includes intelligent parsing to extract the opportunity ID
    from a HYPERLINK formula commonly found in CSV exports.
    """
    help = 'Imports grant opportunities from a Grants.gov CSV data file.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file_path', type=str, help='The full path to the CSV data file.')

    def _extract_opportunity_id(self, hyperlink_string: str) -> str | None:
        """
        Parses a HYPERLINK string to extract the numerical opportunity ID.
        Example input: =HYPERLINK("https://www.grants.gov/search-results-detail/3589399", "...")
        Returns: "3589399"
        """
        if not hyperlink_string or not hyperlink_string.startswith('=HYPERLINK'):
            return hyperlink_string # Return as-is if it's not a hyperlink formula

        # Use regex to find the sequence of digits in the URL part of the hyperlink
        match = re.search(r'/(\d+)"', hyperlink_string)
        if match:
            return match.group(1) # Return the captured digits
        
        # Fallback if regex fails, just in case
        return None

    def _clean_decimal(self, value: str) -> float | None:
        """Helper to convert string to decimal, returns None if empty or invalid."""
        if value is None or value.strip() == '':
            return None
        try:
            # Remove commas from numbers like "1,000,000"
            return float(value.replace(',', ''))
        except (ValueError, TypeError):
            return None

    def _clean_date(self, value: str) -> str | None:
        """Helper to parse date string, returns None if invalid."""
        if not value:
            return None
        try:
            # Handle formats like "Jun-06-2025 03:28:33 PM EST"
            cleaned_value = value.replace(' EST', ' -0500').replace(' EDT', ' -0400')
            return parse_datetime(cleaned_value)
        except Exception:
            # Try another common format like MM/DD/YYYY
            try:
                return parse_datetime(value)
            except Exception:
                return None

    def handle(self, *args, **options):
        csv_file_path = options['csv_file_path']
        self.stdout.write(self.style.SUCCESS(f"Starting import from CSV file: {csv_file_path}"))

        try:
            with open(csv_file_path, mode='r', encoding='utf-8') as csvfile:
                # Use a different delimiter if your CSV is not comma-separated
                reader = csv.DictReader(csvfile)
                
                gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)

                created_count = 0
                updated_count = 0
                skipped_count = 0

                for row in reader:
                    try:
                        # Use the new helper to parse the opportunity number
                        opportunity_id_raw = row.get('OPPORTUNITY NUMBER')
                        opportunity_id = self._extract_opportunity_id(opportunity_id_raw)

                        if not opportunity_id:
                            self.stderr.write(self.style.WARNING(f"Skipping row with unparsable OPPORTUNITY NUMBER: {opportunity_id_raw}"))
                            skipped_count += 1
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
                            'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                        }
                        
                        grant_obj, created = GrantOpportunity.objects.update_or_create(
                            source_name='CSV_UPLOAD',
                            source_id=opportunity_id,
                            defaults=defaults
                        )

                        if created: created_count += 1
                        else: updated_count += 1
                        
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing row for opp ID '{opportunity_id}': {e}"))
                        skipped_count += 1

        except FileNotFoundError:
            raise CommandError(f"CSV file not found at: {csv_file_path}")
        except Exception as e:
            raise CommandError(f"An unexpected error occurred while reading the CSV file: {e}")

        self.stdout.write(self.style.SUCCESS(f"CSV Import complete. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}"))
