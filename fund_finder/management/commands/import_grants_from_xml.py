# fund_finder/management/commands/import_grants_from_xml.py
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from fund_finder.models import FunderProfile, GrantOpportunity, FunderType

class Command(BaseCommand):
    """
    Management command to import grant opportunities from a Grants.gov XML data extract.

    This command parses a given XML file (unzipped from the Grants.gov data dump)
    and populates the FunderProfile and GrantOpportunity models.

    Example usage:
    - python manage.py import_grants_from_xml /path/to/your/GrantsDBExtract.xml
    """
    help = 'Imports grant opportunities from a Grants.gov XML data extract file.'

    def add_arguments(self, parser):
        parser.add_argument('xml_file_path', type=str, help='The full path to the XML data extract file.')

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

        # Get or create the system-level "Government" FunderType
        gov_funder_type, _ = FunderType.objects.get_or_create(name="Government", organization=None)

        created_count = 0
        updated_count = 0

        # The exact tags depend on the XML schema from Grants.gov. This is an example structure.
        # You will need to inspect the XML to get the correct tag names and namespaces.
        for grant_node in root.findall('OpportunitySynopsisDetail_1_0'): # Example path
            try:
                opportunity_id = grant_node.findtext('OpportunityID')
                if not opportunity_id:
                    continue

                agency_name = grant_node.findtext('AgencyName', 'Unknown Government Funder').strip()
                funder, _ = FunderProfile.objects.get_or_create(
                    name=agency_name,
                    defaults={'funder_type': gov_funder_type, 'organization': None}
                )

                defaults = {
                    'funder': funder,
                    'title': grant_node.findtext('OpportunityTitle', 'No Title Provided'),
                    'description': grant_node.findtext('Description', 'No description provided.'),
                    'application_deadline': parse_datetime(grant_node.findtext('ClosingDate')) if grant_node.findtext('ClosingDate') else None,
                    'source_url': f"https://www.grants.gov/search-results-detail/{opportunity_id}",
                    'is_active': True, # Assume active if in the dump, or check a status field
                    # ... Map other fields from the XML nodes ...
                }

                grant_obj, created = GrantOpportunity.objects.update_or_create(
                    source_name='XML_UPLOAD',
                    source_id=str(opportunity_id),
                    defaults=defaults
                )

                if created: created_count += 1
                else: updated_count += 1
                self.stdout.write(f"{'Created' if created else 'Updated'} grant: {grant_obj.title}")

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error processing XML node for opp ID '{opportunity_id}': {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"XML Import complete. Created: {created_count}, Updated: {updated_count}"))
