# fund_finder/management/commands/fetch_grants_gov.py
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.db import IntegrityError
from fund_finder.grant_sources.grants_gov import GrantsGovAPIClient
from fund_finder.models import FunderProfile, GrantOpportunity

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
            # 1. Search for a list of grants
            grants_data = client.search_posted_grants(keyword=keyword, rows=rows)
        except Exception as e:
            raise CommandError(f"Failed to fetch data from Grants.gov API: {e}")

        if not grants_data:
            self.stdout.write(self.style.WARNING("No grant opportunities found or API returned empty list."))
            return

        created_count = 0
        updated_count = 0

        for grant_summary in grants_data:
            try:
                opportunity_id = grant_summary.get('opportunityId')
                if not opportunity_id:
                    self.stderr.write(self.style.WARNING(f"Skipping grant with no opportunityId: {grant_summary.get('opportunityTitle')}"))
                    continue

                # --- Step 2: Get or Create the Funder Profile ---
                agency_name = grant_summary.get('agencyName', 'Unknown Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={'funder_type': 'Government'}
                )

                # --- Step 3: Fetch Detailed Info (Optional) ---
                grant_details = grant_summary # Start with summary data
                if fetch_details:
                    try:
                        self.stdout.write(f"Fetching details for ID: {opportunity_id}...")
                        # The detailed response often has a slightly different structure
                        detailed_response = client.fetch_opportunity_details(opportunity_id)
                        # The detailed data is often in a 'synopsis' or similar key
                        synopsis = detailed_response.get('synopsis', {})
                        if synopsis:
                             grant_details.update(synopsis) # Merge detailed data into our grant_details dict
                        else:
                             grant_details.update(detailed_response) # Fallback to merging the whole response
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Could not fetch details for ID {opportunity_id}: {e}. Proceeding with summary data."))

                # --- Step 4: Map and Save the Grant Opportunity ---
                # Prepare the data for the fields in our GrantOpportunity model
                defaults = {
                    'funder': funder,
                    'title': grant_details.get('opportunityTitle', 'No Title Provided'),
                    'description': grant_details.get('description', 'No description provided.'),
                    'min_amount': grant_details.get('awardFloor'),
                    'max_amount': grant_details.get('awardCeiling'),
                    'application_deadline': parse_datetime(grant_details['closeDate']) if grant_details.get('closeDate') else None,
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'is_active': grant_details.get('opportunityStatus') == 'posted',
                    'eligibility_criteria': grant_details.get('eligibility', {}).get('description', ''),
                }
                
                # Create or update the grant object using the unique source_name and source_id
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

                # --- Step 5 (For Future Implementation): Index for RAG ---
                # After saving, you would call your baserag service to index the text.
                # from baserag.services import index_document
                # document_text = f"Title: {grant_obj.title}\nDescription: {grant_obj.description}\nEligibility: {grant_obj.eligibility_criteria}"
                # index_document(document_id=str(grant_obj.id), text=document_text, metadata={'grant_id': str(grant_obj.id), 'funder': funder.name})
                
            except IntegrityError as e:
                self.stderr.write(self.style.ERROR(f"Database integrity error for grant '{grant_summary.get('opportunityTitle')}': {e}"))
            except KeyError as e:
                self.stderr.write(self.style.ERROR(f"Missing expected key in API response: {e}. Skipping grant."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred while processing grant '{grant_summary.get('opportunityTitle')}': {e}"))

        self.stdout.write(self.style.SUCCESS(f"Process complete. Created: {created_count}, Updated: {updated_count}"))
