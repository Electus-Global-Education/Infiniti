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
    the FunderProfile and GrantOpportunity models in the local database.

    It can be run manually or automated via a cron job for regular updates.

    Example usage:
    - python manage.py fetch_grants_gov
    - python manage.py fetch_grants_gov --keyword "health" --rows 100
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
                funder, created = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={'funder_type': 'Government'}
                )
                if created:
                    self.stdout.write(f"Created new funder: {agency_name}")

                # --- Step 3: Fetch Detailed Info (Optional) ---
                grant_details = grant_summary # Start with summary data
                if fetch_details:
                    try:
                        self.stdout.write(f"Fetching details for ID: {opportunity_id}...")
                        # The detailed response often contains the summary fields plus more.
                        # The API might return a list, so we handle that case.
                        detailed_response = client.fetch_opportunity_details(opportunity_id)
                        if isinstance(detailed_response, dict) and detailed_response.get('opps'):
                            grant_details = detailed_response['opps'][0]
                        else:
                            # Handle cases where the structure might be different
                            grant_details = detailed_response
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Could not fetch details for ID {opportunity_id}: {e}"))
                        # We can still proceed with the summary data

                # --- Step 4: Map and Save the Grant Opportunity ---
                # Use opportunityId as the unique key for update_or_create to avoid duplicates.
                # First, we need a field in our model to store this. Let's assume we add `source_id`.
                # For now, we'll try to match by title and funder as a fallback.
                
                # Recommended: Add `source_id` to GrantOpportunity model:
                # source_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
                
                defaults = {
                    'description': grant_details.get('description', 'No description provided.'),
                    'min_amount': grant_details.get('awardFloor'),
                    'max_amount': grant_details.get('awardCeiling'),
                    'application_deadline': parse_datetime(grant_details['closeDate']) if grant_details.get('closeDate') else None,
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'is_active': grant_details.get('opportunityStatus') == 'posted',
                    'eligibility_criteria': grant_details.get('eligibility', {}).get('description', ''),
                    # Add other fields you want to map from the API response
                }
                
                # Create or update the grant object
                grant_obj, created = GrantOpportunity.objects.update_or_create(
                    title=grant_details['opportunityTitle'],
                    funder=funder,
                    defaults=defaults
                )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Created grant: {grant_obj.title}"))
                else:
                    updated_count += 1
                    self.stdout.write(f"Updated grant: {grant_obj.title}")

                # --- Step 5 (For Future Implementation): Index for RAG ---
                # Here, after saving, you would call your baserag service to index the text fields.
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
