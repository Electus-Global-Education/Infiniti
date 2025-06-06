# fund_finder/grant_sources/grants_gov.py
import requests
import os
from typing import List, Dict, Any

class GrantsGovAPIClient:
    """
    A client for interacting with the Grants.gov API.

    This class handles making requests to the search and fetch endpoints
    and processing the responses into a standardized format. For the MVP,
    it uses the unauthenticated V1 'search2' and 'fetchOpportunity' endpoints.
    """
    # Using the V1 endpoint which has unauthenticated search capabilities
    API_BASE_URL = "https://api.grants.gov/v1/api"
    # Note: The V2 API required a key, but the V1 'search2' does not.
    # API_KEY = os.environ.get("GRANTS_GOV_API_KEY") # No longer needed for search2

    def _make_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Private helper method to make a POST request to the API.

        Args:
            endpoint (str): The API endpoint to hit (e.g., '/search2').
            payload (Dict[str, Any]): The JSON payload for the request body.

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        url = f"{self.API_BASE_URL}{endpoint}"
        headers = {
            "Content-Type": "application/json",
        }
        
        try:
            # Grants.gov API uses POST for search queries
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err} - {response.text}")
            raise
        except requests.exceptions.RequestException as req_err:
            print(f"Request error occurred: {req_err}")
            raise

    def search_posted_grants(self, keyword: str = None, rows: int = 50) -> List[Dict[str, Any]]:
        """
        Searches for currently posted grant opportunities on Grants.gov using the 'search2' endpoint.

        Args:
            keyword (str, optional): A keyword to search for. Defaults to None.
            rows (int, optional): The number of records to retrieve. Defaults to 50.

        Returns:
            List[Dict[str, Any]]: A list of grant opportunity dictionaries from the API response.
        """
        endpoint = "/search2" # Using the unauthenticated search2 endpoint
        payload = {
            "oppStatus": "posted", # We are only interested in currently posted grants
            "rows": rows
        }
        if keyword:
            payload["keyword"] = keyword

        print(f"Searching Grants.gov with payload: {payload}")
        data = self._make_request(endpoint, payload)
        
        # The opportunities are nested under the 'opps' key in the response
        return data.get("opps", [])

    def fetch_opportunity_details(self, opportunity_id: str) -> Dict[str, Any]:
        """
        Retrieves comprehensive details for a single grant opportunity.

        Args:
            opportunity_id (str): The opportunityId of the grant to fetch.

        Returns:
            Dict[str, Any]: A dictionary containing the detailed grant information.
        """
        endpoint = "/fetchOpportunity"
        payload = {"opportunityId": opportunity_id}
        
        print(f"Fetching details for opportunity ID: {opportunity_id}")
        data = self._make_request(endpoint, payload)
        
        # The response structure might vary, adjust as needed.
        # Often details are directly in the response or under a key.
        return data
