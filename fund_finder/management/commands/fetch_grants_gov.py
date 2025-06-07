# fund_finder/management/commands/fetch_grants_gov.py
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.db import IntegrityError
from fund_finder.grant_sources.grants_gov import GrantsGovAPIClient
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Django management command to fetch grant opportunities from Grants.gov.

    This command uses the GrantsGovAPIClient to search for grants, then populates
    the FunderProfile and GrantOpportunity models in the local database. It uses
    the 'opportunityId' from the API as a unique source ID to prevent duplicates.

    Example usage:
    - python manage.py fetch_grants_gov --rows 25
    - python manage.py fetch_grants_gov --keyword "health" --rows 100 --update-details
    """
    help = 'Fetches grant opportunities from Grants.gov and saves them to the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keyword',
            type=str,
            help='Optional: A keyword to search for grants.',
            default=None
        )
        parser.add_argument(
            '--rows',
            type=int,
            help='The number of grant records to fetch (max per request is typically limited by the API).',
            default=50
        )
        parser.add_argument(
            '--update-details',
            action='store_true',
            help='Optional: Fetch detailed information for each grant found. This will make more API calls.'
        )

    def handle(self, *args, **options):
        keyword = options['keyword']
        rows = options['rows']
        fetch_details = options['update_details']
        
        self.stdout.write(self.style.SUCCESS(f"Starting to fetch grants from Grants.gov... Keyword: '{keyword or 'None'}', Rows: {rows}"))
        
        client = GrantsGovAPIClient()
        
        try:
            grants_data = client.search_posted_grants(keyword=keyword, rows=rows)
        except Exception as e:
            raise CommandError(f"Failed to fetch data from Grants.gov API: {e}")

        if not grants_data:
            self.stdout.write(self.style.WARNING("No grant opportunities found or API returned empty list."))
            return

        # Get or create the system-level "Government" FunderType to assign to these funders
        gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)

        created_count = 0
        updated_count = 0

        for grant_summary in grants_data:
            try:
                opportunity_id = grant_summary.get('opportunityId')
                if not opportunity_id:
                    self.stderr.write(self.style.WARNING(f"Skipping grant with no opportunityId: {grant_summary.get('opportunityTitle')}"))
                    continue

                # --- Get or Create the Funder Profile ---
                agency_name = grant_summary.get('agencyName', 'Unknown Government Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={'funder_type': gov_funder_type, 'organization': None} # These are global, system-level funders
                )

                # --- Fetch Detailed Info if requested ---
                grant_details = grant_summary
                if fetch_details:
                    try:
                        self.stdout.write(f"Fetching details for ID: {opportunity_id}...")
                        detailed_response = client.fetch_opportunity_details(opportunity_id)
                        synopsis = detailed_response.get('synopsis', {})
                        if synopsis:
                             grant_details.update(synopsis) # Merge detailed data into our grant_details dict
                        else:
                             grant_details.update(detailed_response)
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Could not fetch details for ID {opportunity_id}: {e}. Proceeding with summary data."))

                # --- Map and Save the Grant Opportunity ---
                defaults = {
                    'funder': funder,
                    'title': grant_details.get('opportunityTitle', 'No Title Provided'),
                    'description': grant_details.get('description', 'No description provided.'),
                    'min_amount': grant_details.get('awardFloor'),
                    'max_amount': grant_details.get('awardCeiling'),
                    'application_deadline': parse_datetime(grant_details['closeDate']) if grant_details.get('closeDate') else None,
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'is_active': grant_details.get('opportunityStatus') == 'posted',
                    'funding_instrument_type': ", ".join(grant_details.get('fundingInstruments', [])),
                    'funding_activity_category': ", ".join(grant_details.get('fundingCategories', [])),
                    'eligibility_criteria_text': grant_details.get('eligibility', {}).get('description', ''),
                }
                
                grant_obj, created = GrantOpportunity.objects.update_or_create(
                    source_name='GRANTS_GOV',
                    source_id=str(opportunity_id),
                    defaults=defaults
                )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Created grant: {grant_obj.title}"))
                else:
                    updated_count += 1
                    self.stdout.write(f"Updated grant: {grant_obj.title}")

            except IntegrityError as e:
                self.stderr.write(self.style.ERROR(f"Database integrity error for grant '{grant_summary.get('opportunityTitle')}': {e}"))
            except KeyError as e:
                self.stderr.write(self.style.ERROR(f"Missing expected key in API response: {e}. Skipping grant."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred while processing grant '{grant_summary.get('opportunityTitle')}': {e}"))

        self.stdout.write(self.style.SUCCESS(f"Process complete. Created: {created_count}, Updated: {updated_count}"))
