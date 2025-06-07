# fund_finder/management/commands/import_grants_from_xml.py
import xml.etree.ElementTree as ET
import re
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Management command to import grant opportunities from a Grants.gov XML data extract.

    This command uses a robust parsing method that finds grant records by searching for
    the 'OpportunityID' tag, making it resilient to changes in the parent XML structure
    and namespaces.
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
        if not ns_map:
            return node.findtext(path)
        return node.findtext(f"ns:{path}", namespaces=ns_map)

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

        # --- More Robust Namespace and Node Detection ---
        namespace = ''
        if '}' in root.tag:
            namespace = root.tag.split('}')[0][1:]
        
        ns_map = {'ns': namespace} if namespace else {}
        opportunity_id_tag = f"{{{namespace}}}OpportunityID" if namespace else "OpportunityID"

        # Instead of searching for a specific parent node, we iterate through the entire
        # document and find any node that contains an 'OpportunityID'. This is much more robust.
        grant_nodes = [node for node in root.iter() if node.find(opportunity_id_tag) is not None]
        
        if not grant_nodes:
            self.stdout.write(self.style.WARNING("Could not find any nodes containing an 'OpportunityID' tag. The XML file might be empty, structured unexpectedly, or have a different tag for the opportunity ID."))
            return

        self.stdout.write(f"Found {len(grant_nodes)} potential grant opportunities in the XML file. Starting processing...")

        gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for grant_node in grant_nodes:
            # Use a lambda function to simplify finding text within the current node
            find = lambda path: self._find_namespaced_text(grant_node, path, ns_map)
            
            opportunity_id = find('OpportunityID')

            try:
                if not opportunity_id:
                    skipped_count += 1
                    continue

                agency_name = (find('AgencyName') or 'Unknown Government Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={
                        'funder_type': gov_funder_type,
                        'agency_code': find('AgencyCode'),
                        'organization': None
                    }
                )

                defaults = {
                    'funder': funder,
                    'title': find('OpportunityTitle') or 'No Title Provided',
                    'description': find('Description') or 'No description provided.',
                    'status': (find('OpportunityStatus') or 'POSTED').upper(),
                    'version': find('Version'),
                    'estimated_total_funding': self._clean_decimal(find('EstimatedTotalProgramFunding')),
                    'award_floor': self._clean_decimal(find('AwardFloor')),
                    'award_ceiling': self._clean_decimal(find('AwardCeiling')),
                    'expected_number_of_awards': int(find('NumberOfAwards')) if find('NumberOfAwards') else None,
                    'cost_sharing_requirement': 'Yes' if find('CostSharingOrMatchingRequirement') == 'Y' else 'No',
                    'funding_instrument_type': find('FundingInstrumentType'),
                    'funding_activity_category': find('FundingActivityCategory'),
                    'assistance_listings': find('CFDANumbers'),
                    'posted_date': self._clean_date(find('PostDate')),
                    'close_date': self._clean_date(find('ClosingDate')),
                    'last_updated_date': self._clean_date(find('LastUpdatedDate')),
                    'is_active': (find('OpportunityStatus') or '').upper() == 'POSTED',
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'eligibility_criteria_text': find('EligibilityCriteria'),
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
