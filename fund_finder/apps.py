# fund_finder/apps.py
from django.apps import AppConfig

class FundFinderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fund_finder'

    def ready(self):
        """
        This method is called when Django starts. We import our signals here
        to ensure they are connected.
        """
        import fund_finder.signals
