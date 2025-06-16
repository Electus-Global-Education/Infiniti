import os
import environ
from vertexai import init as vertexai_init
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStoreDatastore

# baserag/connection.py

import os
import sys
import environ

# Determine if we're running a Django management command that doesn't need vector-store
_MANAGEMENT_CMD = sys.argv[1] if len(sys.argv) > 1 else None
_SIMPLE_COMMANDS = {
    "collectstatic",
    "migrate",
    "makemigrations",
    "check",
    "shell",
    "runserver",
}

if _MANAGEMENT_CMD in _SIMPLE_COMMANDS:
    # Stub out embedding and vector store during management commands
    class _DummyEmbedding:
        def embed_documents(self, docs):
            return [[] for _ in docs]

    class _DummyStore:
        def upsert(self, *args, **kwargs):
            pass

    embedding_model = _DummyEmbedding()
    vector_store = _DummyStore()

else:
    # Real initialization: load creds & settings from .env.vectorstore
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ENV_PATH = os.path.join(ROOT_DIR, ".env.vectorstore")

    env = environ.Env()
    if os.path.exists(ENV_PATH):
        env.read_env(ENV_PATH, overwrite=True)
    else:
        raise RuntimeError(f"Missing .env.vectorstore at {ENV_PATH}")

    # Required variables
    GOOGLE_APPLICATION_CREDENTIALS = env("GOOGLE_APPLICATION_CREDENTIALS")
    PROJECT_ID                     = env("PROJECT_ID")
    REGION                         = env("REGION")
    INDEX_ID                       = env("INDEX_ID")
    ENDPOINT_ID                    = env("ENDPOINT_ID")
    EMBEDDING_MODEL_NAME           = env("EMBEDDING_MODEL_NAME")
    BUCKET                         = env("BUCKET")
    # # print all values
    # print("\n--- VECTOR STORE CONFIG ---")
    # print(f"PROJECT_ID           = {PROJECT_ID}")
    # print(f"REGION               = {REGION}")
    # print(f"INDEX_ID             = {INDEX_ID}")
    # print(f"ENDPOINT_ID          = {ENDPOINT_ID}")
    # print(f"EMBEDDING_MODEL_NAME = {EMBEDDING_MODEL_NAME}")
    # print(f"BUCKET               = {BUCKET}")
    # print("-----------------------------\n")

    # Point Google SDK at your service account
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

    # Initialize Vertex AI
    from vertexai import init as vertexai_init
    from langchain_google_vertexai import (
        VertexAIEmbeddings,
        VectorSearchVectorStoreDatastore,
    )

    vertexai_init(project=PROJECT_ID, location=REGION)

    embedding_model = VertexAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    embedding_model.model_rebuild()

    vector_store = VectorSearchVectorStoreDatastore.from_components(
        project_id=PROJECT_ID,
        region=REGION,
        index_id=INDEX_ID,
        gcs_bucket_name=BUCKET,
        endpoint_id=ENDPOINT_ID,
        embedding=embedding_model,
        stream_update=True,
    )

# # Load environment variables
# env = environ.Env()

# # Assuming your .env.vectorstore is in the root directory (same as manage.py)
# ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# env.read_env(os.path.join(ROOT_DIR, ".env.vectorstore"))

# # Now read the environment variables
# GOOGLE_APPLICATION_CREDENTIALS = env("GOOGLE_APPLICATION_CREDENTIALS")
# PROJECT_ID = env("PROJECT_ID")
# REGION = env("REGION")
# INDEX_ID = env("INDEX_ID")
# ENDPOINT_ID = env("ENDPOINT_ID")
# EMBEDDING_MODEL_NAME = env("EMBEDDING_MODEL_NAME")
# BUCKET = env("BUCKET")

# # print all values
# # print("\n--- VECTOR STORE CONFIG ---")
# # print(f"PROJECT_ID           = {PROJECT_ID}")
# # print(f"REGION               = {REGION}")
# # print(f"INDEX_ID             = {INDEX_ID}")
# # print(f"ENDPOINT_ID          = {ENDPOINT_ID}")
# # print(f"EMBEDDING_MODEL_NAME = {EMBEDDING_MODEL_NAME}")
# # print(f"BUCKET               = {BUCKET}")
# # print("-----------------------------\n")

# # print(f"Using project: {PROJECT_ID}")
# #  Initialize Vertex AI
# vertexai_init(project=PROJECT_ID, location=REGION)

# #  Create embedding model and vector store
# embedding_model = VertexAIEmbeddings(model=EMBEDDING_MODEL_NAME)
# embedding_model.model_rebuild()

# vector_store = VectorSearchVectorStoreDatastore.from_components(
#     project_id=PROJECT_ID,
#     region=REGION,
#     index_id=INDEX_ID,
#     gcs_bucket_name=BUCKET,
#     endpoint_id=ENDPOINT_ID,
#     embedding=embedding_model, # Text Embedding-005
#     stream_update=True
# )
