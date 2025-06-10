import os
import environ
from vertexai import init as vertexai_init
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStoreDatastore

# Load environment variables
env = environ.Env()

# Assuming your .env.vectorstore is in the root directory (same as manage.py)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env.read_env(os.path.join(ROOT_DIR, ".env.vectorstore"))

# Now read the environment variables
GOOGLE_APPLICATION_CREDENTIALS = env("GOOGLE_APPLICATION_CREDENTIALS")
PROJECT_ID = env("PROJECT_ID")
REGION = env("REGION")
INDEX_ID = env("INDEX_ID")
ENDPOINT_ID = env("ENDPOINT_ID")
EMBEDDING_MODEL_NAME = env("EMBEDDING_MODEL_NAME")
BUCKET = env("BUCKET")

# print all values
# print("\n--- VECTOR STORE CONFIG ---")
# print(f"PROJECT_ID           = {PROJECT_ID}")
# print(f"REGION               = {REGION}")
# print(f"INDEX_ID             = {INDEX_ID}")
# print(f"ENDPOINT_ID          = {ENDPOINT_ID}")
# print(f"EMBEDDING_MODEL_NAME = {EMBEDDING_MODEL_NAME}")
# print(f"BUCKET               = {BUCKET}")
# print("-----------------------------\n")

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
    embedding=embedding_model, # Text Embedding-005
    stream_update=True
)
