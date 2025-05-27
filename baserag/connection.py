import os
from dotenv import load_dotenv
from vertexai import init as vertexai_init
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStoreDatastore

# Load vector config
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env_vector_store'))

# Read env vars
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
INDEX_ID = os.getenv("INDEX_ID")
ENDPOINT_ID = os.getenv("ENDPOINT_ID")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
BUCKET = os.getenv("BUCKET")

#  Initialize Vertex AI
vertexai_init(project=PROJECT_ID, location=REGION)

#  Create embedding model and vector store
embedding_model = VertexAIEmbeddings(model=EMBEDDING_MODEL_NAME)
embedding_model.model_rebuild()

vector_store = VectorSearchVectorStoreDatastore.from_components(
    project_id=PROJECT_ID,
    region=REGION,
    index_id=INDEX_ID,
    gcs_bucket_name=BUCKET,
    endpoint_id=ENDPOINT_ID,
    embedding=embedding_model,
    stream_update=True
)
