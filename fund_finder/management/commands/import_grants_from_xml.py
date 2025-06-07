# fund_finder/management/commands/import_grants_from_xml.py
import xml.etree.ElementTree as ET
import re
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Management command to import grant opportunities from a Grants.gov XML data extract.

    This command intelligently parses a given XML file, handling potential namespaces
    to reliably find grant data nodes and populate the local database.
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
            
    def _find_namespaced_text(self, node, path, ns_map):
        """Helper to find text in a node with a given namespace map."""
        return node.findtext(path, namespaces=ns_map)

    def handle(self, *args, **options):
        xml_file_path = options['xml_file_path']
        self.stdout.write(self.style.SUCCESS(f"Starting import from XML file: {xml_file_path}"))

        try:
            # Register namespace before parsing to handle them correctly
            # This is crucial for ElementTree to parse namespaced XML
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
        except FileNotFoundError:
            raise CommandError(f"XML file not found at: {xml_file_path}")
        except ET.ParseError as e:
            raise CommandError(f"Failed to parse XML file: {e}")

        # --- Namespace Detection Logic ---
        # Grants.gov XML often uses a namespace. We need to detect and use it.
        namespace = ''
        if '}' in root.tag:
            namespace = root.tag.split('}')[0][1:] # Extracts the namespace URI from the root tag
        
        ns_map = {'ns': namespace} if namespace else {}
        grant_node_path = f".//ns:OpportunitySynopsisDetail_1_0" if namespace else ".//OpportunitySynopsisDetail_1_0"

        grant_nodes = root.findall(grant_node_path, ns_map)
        
        if not grant_nodes:
            self.stdout.write(self.style.WARNING(f"Could not find any grant opportunity nodes using path '{grant_node_path}'. Please check the XML file structure and namespace."))
            return

        self.stdout.write(f"Found {len(grant_nodes)} potential grant opportunities in the XML file. Starting processing...")

        gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for grant_node in grant_nodes:
            # Use the helper function to find text with the correct namespace
            find = lambda path: self._find_namespaced_text(grant_node, path, ns_map)
            
            opportunity_id = find('ns:OpportunityID') if ns_map else grant_node.findtext('OpportunityID')

            try:
                if not opportunity_id:
                    skipped_count += 1
                    continue

                agency_name = (find('ns:AgencyName') or 'Unknown Government Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={
                        'funder_type': gov_funder_type,
                        'agency_code': find('ns:AgencyCode'),
                        'organization': None # This is a global funder from a system source
                    }
                )

                defaults = {
                    'funder': funder,
                    'title': find('ns:OpportunityTitle') or 'No Title Provided',
                    'description': find('ns:Description') or 'No description provided.',
                    'status': (find('ns:OpportunityStatus') or 'POSTED').upper(),
                    'version': find('ns:Version'),
                    'estimated_total_funding': self._clean_decimal(find('ns:EstimatedTotalProgramFunding')),
                    'award_floor': self._clean_decimal(find('ns:AwardFloor')),
                    'award_ceiling': self._clean_decimal(find('ns:AwardCeiling')),
                    'expected_number_of_awards': int(find('ns:NumberOfAwards')) if find('ns:NumberOfAwards') else None,
                    'cost_sharing_requirement': 'Yes' if find('ns:CostSharingOrMatchingRequirement') == 'Y' else 'No',
                    'funding_instrument_type': find('ns:FundingInstrumentType'),
                    'funding_activity_category': find('ns:FundingActivityCategory'),
                    'assistance_listings': find('ns:CFDANumbers'), # CFDA is now Assistance Listing
                    'posted_date': self._clean_date(find('ns:PostDate')),
                    'close_date': self._clean_date(find('ns:ClosingDate')),
                    'last_updated_date': self._clean_date(find('ns:LastUpdatedDate')),
                    'is_active': (find('ns:OpportunityStatus') or '').upper() == 'POSTED',
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'eligibility_criteria_text': find('ns:EligibilityCriteria'),
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
