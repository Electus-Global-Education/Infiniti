# fund_finder/services.py
from typing import List, Dict, Any
from .models import GrantOpportunity
from core.models import Organization, BasePrompt

# --- Reusable Service Imports ---
# Import the actual, centralized services from your other apps.
from core.utils import generate_gemini_response
from baserag.connection import embedding_model, vector_store


class FundFinderService:
    """
    A service class to encapsulate the logic for finding and matching grant opportunities.
    This service integrates with the centralized RAG and LLM services.
    """
    
    @staticmethod
    def _retrieve_relevant_grants_from_rag(query_text: str, top_k: int = 10) -> List[str]:
        """
        Private helper method to perform semantic search against the vector store.

        This function encapsulates the logic from your baserag app's test view.
        It takes a query, generates an embedding, and finds the most relevant
        grant documents from the vector store.

        Args:
            query_text (str): The search query (e.g., an organization's program focus).
            top_k (int): The number of top results to retrieve.

        Returns:
            List[str]: A list of grant UUIDs that are considered relevant.
        """
        if not query_text:
            return []

        try:
            # 1. Generate an embedding for the user's query using the centralized model
            query_embedding = embedding_model.embed_documents([query_text])[0]
            if not query_embedding:
                print("ERROR: Failed to generate embedding for query.")
                return []

            # 2. Perform similarity search against the vector store
            # The result is a list of (Document, score) tuples.
            results = vector_store.similarity_search_by_vector_with_score(query_embedding, k=top_k)

            # 3. Extract grant IDs from the metadata of the matched documents.
            # CRITICAL ASSUMPTION: The documents in your vector store must have
            # metadata containing the grant's UUID, e.g., doc.metadata = {'grant_id': '...'}
            grant_ids = [doc.metadata['grant_id'] for doc, score in results if 'grant_id' in doc.metadata]
            
            if not grant_ids:
                print(f"WARNING: RAG search returned {len(results)} results, but none had a 'grant_id' in their metadata.")

            return grant_ids

        except Exception as e:
            # Log the error for debugging purposes
            print(f"ERROR: RAG service query failed: {str(e)}")
            return []


    @staticmethod
    def find_matching_grants(organization: Organization, needs_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Main method to find and rank grant opportunities for a given organization.

        This method coordinates between the RAG service (to find relevant grants)
        and the LLM service (to generate a justification for the match).

        Args:
            organization (Organization): The organization seeking funding.
            needs_profile (Dict[str, Any]): A dictionary describing the organization's
                                             current needs, e.g., {'program_focus': 'STEM education for youth'}.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing a GrantOpportunity
                                  object and an AI-generated 'match_rationale'.
        """
        program_focus = needs_profile.get('program_focus', organization.description)

        if not program_focus:
            return []

        # 1. Use our internal RAG helper to find relevant grant IDs
        matched_grant_ids = FundFinderService._retrieve_relevant_grants_from_rag(query_text=program_focus, top_k=10)
        
        if not matched_grant_ids:
            return []

        # 2. Fetch the full GrantOpportunity objects from the database
        matched_grants = GrantOpportunity.objects.filter(id__in=matched_grant_ids, is_active=True).select_related('funder')

        # 3. Use the centralized LLM Service (from core app) to generate a match rationale for each grant
        try:
            # Fetch the base prompt for generating match rationales
            base_prompt_obj = BasePrompt.objects.get(title="Fund Finder Match Rationale", prompt_type="SYSTEM", is_active=True)
            base_prompt_text = base_prompt_obj.prompt_text
        except BasePrompt.DoesNotExist:
            # Fallback prompt if the specific one isn't in the database
            print("WARNING: 'Fund Finder Match Rationale' SYSTEM prompt not found. Using fallback.")
            base_prompt_text = """
            Context: An organization with the following profile is seeking funding:
            - Organization Name: {{org_name}}
            - Organization Description: {{org_description}}
            - Stated Need: {{org_need}}

            A potentially matching grant has been identified:
            - Grant Title: {{grant_title}}
            - Grant Description: {{grant_description}}
            - Funder: {{funder_name}}

            Task: Based on the context, provide a concise, one-sentence rationale explaining why this grant is a good potential match for the organization.
            Rationale:
            """

        results = []
        for grant in matched_grants:
            # Construct the prompt for the LLM
            prompt = base_prompt_text.replace("{{org_name}}", organization.name) \
                                     .replace("{{org_description}}", organization.description or "N/A") \
                                     .replace("{{org_need}}", program_focus) \
                                     .replace("{{grant_title}}", grant.title) \
                                     .replace("{{grant_description}}", grant.description) \
                                     .replace("{{funder_name}}", grant.funder.name)
            
            # Call the centralized Gemini service from core.utils
            llm_result = generate_gemini_response(prompt=prompt)
            rationale = llm_result.get("response", "Could not generate rationale.") # Safely get the response
            
            # Prepare the result object
            results.append({
                "grant": grant, # The full GrantOpportunity object
                "match_rationale": rationale
            })
            
        return results

