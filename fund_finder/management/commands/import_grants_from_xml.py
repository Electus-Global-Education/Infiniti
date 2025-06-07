# fund_finder/management/commands/import_grants_from_xml.py
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Management command to import grant opportunities from a Grants.gov XML data extract.

    This command parses a given XML file (unzipped from the Grants.gov data dump)
    and populates the FunderProfile and GrantOpportunity models. It uses more realistic
    tag names based on the Grants.gov schema.
    """
    help = 'Imports grant opportunities from a Grants.gov XML data extract file.'

    def add_arguments(self, parser):
        parser.add_argument('xml_file_path', type=str, help='The full path to the XML data extract file.')

    def _clean_decimal(self, value: str) -> float | None:
        """Helper to convert string to decimal, returns None if empty or invalid."""
        if value is None or value.strip() == '':
            return None
        try:
            return float(value.replace(',', ''))
        except (ValueError, TypeError):
            return None
            
    def _clean_date(self, value: str) -> str | None:
        """Helper to parse date string (MMDDYYYY format), returns None if invalid."""
        if not value or len(value) != 8:
            return None
        try:
            # Assumes format MMDDYYYY, e.g., 08152014
            return f"{value[4:8]}-{value[0:2]}-{value[2:4]}"
        except Exception:
            return None

    def handle(self, *args, **options):
        xml_file_path = options['xml_file_path']
        self.stdout.write(self.style.SUCCESS(f"Starting import from XML file: {xml_file_path}"))

        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
        except FileNotFoundError:
            raise CommandError(f"XML file not found at: {xml_file_path}")
        except ET.ParseError as e:
            raise CommandError(f"Failed to parse XML file: {e}")

        # The root tag for grants in Grants.gov XML extracts is often 'OpportunitySynopsisDetail_1_0'
        # or similar. We will iterate through these.
        grant_nodes = root.findall('.//OpportunitySynopsisDetail_1_0')
        if not grant_nodes:
            self.stdout.write(self.style.WARNING("Could not find any 'OpportunitySynopsisDetail_1_0' nodes in the XML file. Please check the file structure."))
            return

        self.stdout.write(f"Found {len(grant_nodes)} potential grant opportunities in the XML file. Starting processing...")

        gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for grant_node in grant_nodes:
            opportunity_id = grant_node.findtext('OpportunityID')
            try:
                if not opportunity_id:
                    skipped_count += 1
                    continue

                agency_name = grant_node.findtext('AgencyName', 'Unknown Government Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={
                        'funder_type': gov_funder_type,
                        'agency_code': grant_node.findtext('AgencyCode'),
                        'organization': None # This is a global funder from a system source
                    }
                )

                # Map the XML tags to our model fields
                defaults = {
                    'funder': funder,
                    'title': grant_node.findtext('OpportunityTitle', 'No Title Provided'),
                    'description': grant_node.findtext('Description', 'No description provided.'),
                    'status': grant_node.findtext('OpportunityStatus', 'POSTED').upper(),
                    'version': grant_node.findtext('Version'),
                    
                    'estimated_total_funding': self._clean_decimal(grant_node.findtext('EstimatedTotalProgramFunding')),
                    'award_floor': self._clean_decimal(grant_node.findtext('AwardFloor')),
                    'award_ceiling': self._clean_decimal(grant_node.findtext('AwardCeiling')),
                    'expected_number_of_awards': int(grant_node.findtext('NumberOfAwards')) if grant_node.findtext('NumberOfAwards') else None,
                    
                    'cost_sharing_requirement': 'Yes' if grant_node.findtext('CostSharingOrMatchingRequirement') == 'Y' else 'No',
                    
                    'funding_instrument_type': grant_node.findtext('FundingInstrumentType'),
                    'funding_activity_category': grant_node.findtext('FundingActivityCategory'),
                    'assistance_listings': grant_node.findtext('CFDANumbers'), # CFDA is now Assistance Listing

                    'posted_date': self._clean_date(grant_node.findtext('PostDate')),
                    'close_date': self._clean_date(grant_node.findtext('ClosingDate')),
                    'last_updated_date': self._clean_date(grant_node.findtext('LastUpdatedDate')),
                    
                    'is_active': grant_node.findtext('OpportunityStatus', '').upper() == 'POSTED',
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'eligibility_criteria_text': grant_node.findtext('EligibilityCriteria'),
                }

                grant_obj, created = GrantOpportunity.objects.update_or_create(
                    source_name='XML_UPLOAD',
                    source_id=str(opportunity_id),
                    defaults=defaults
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error processing XML node for opp ID '{opportunity_id}': {e}"))
                skipped_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"XML Import complete. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}"))
