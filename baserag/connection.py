import os
import environ
from vertexai import init as vertexai_init
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStoreDatastore

# Load vector config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env.vectorstore"))  # or any relevant file

# Read env vars
PROJECT_ID = env("PROJECT_ID")
REGION = env("REGION")
INDEX_ID = env("INDEX_ID")
ENDPOINT_ID = env("ENDPOINT_ID")
EMBEDDING_MODEL_NAME = env("EMBEDDING_MODEL_NAME")
BUCKET = env("BUCKET")
# print(f"Using project: {PROJECT_ID}")
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
