

---

```markdown
# 🎓 Infiniti Platform – AI-Powered Education and Retrieval System

## 🚀 Overview

**Infiniti** is a modular Django-based platform designed to deliver advanced educational support and intelligent information retrieval. The system is built with scalability, concurrency, and modular integration in mind. It currently includes the following apps:

- `edujobs`: Handles chat-based AI interactions with Gemini.
- `baserag`: Interfaces with Google Cloud's Vertex AI Vector Search to retrieve relevant document chunks based on semantic similarity (Retrieval-Augmented Generation - RAG).

This repository is containerized with Docker and supports Redis, PostgreSQL, Celery workers, and environment-based configurations.

---

## 🧱 Project Structure

```

Infiniti/
├── edujobs/            # Gemini chat app using Google Generative AI
├── baserag/            # Vector store retrieval app using Vertex AI
├── infiniti/           # Django project settings and main URLs
├── requirements.txt    # Python dependencies
├── docker-compose.yml  # Full stack orchestration
├── .env.django         # Django & DB environment settings
├── .env\_vector\_store   # GCP Vertex AI environment variables
├── Dockerfile          # Web and worker container setup

```

---

## 💬 EduJobs (Gemini Chat Module)

### 🔧 Features

- Implements Gemini-2.0 Flash model via `google-generativeai`
- Exposes an API endpoint `/api/chat/` for AI responses
- Token-based JWT authentication with `djangorestframework-simplejwt`
- Asynchronous background processing via Celery
- API Key-based authentication also supported for external clients

### 🔒 Authentication

- JWT Access Token and Refresh Token via `/api/token/` and `/api/token/refresh/`
- Protects `/api/chat/` endpoint with `IsAuthenticated` permission class
- `.env.django` handles secret keys and token settings

---

## 📚 BaseRAG (Vector Store Retrieval Module)

### 🔧 Features

- Connects to Google Cloud Vertex AI Vector Search
- Converts user queries into embeddings and retrieves relevant chunks
- Endpoint `/api/test-query/` accepts POST with `query` and returns top-k relevant documents
- Embeddings powered by `VertexAIEmbeddings` with model name defined in `.env_vector_store`

### 🧪 Environment Variables (from `.env_vector_store`)

```

PROJECT\_ID=your-gcp-project
REGION=your-gcp-region
INDEX\_ID=your-index-id
ENDPOINT\_ID=your-endpoint-id
EMBEDDING\_MODEL\_NAME=textembedding-gecko
BUCKET=your-bucket-name

````

---

## 🐳 Docker & Services

### 🧩 Compose Stack

- **`web`**: Django app
- **`worker`**: Celery background task processor
- **`db`**: PostgreSQL 15 with persistent volume
- **`redis`**: Redis 7 for task queuing
- **`pgadmin`**: Database GUI interface

### 🛠️ Running the App

```bash
# First time build
docker-compose up -d --build

# Rebuild and restart containers
docker-compose down
docker-compose up -d --build

# View logs
docker-compose logs -f web
````

---

## 🔐 Environment Files

Ensure the following `.env` files exist at the project root:

* `.env.django`: Django settings (DEBUG, DB URL, SECRET\_KEY, etc.)
* `.env_vector_store`: GCP credentials for vector store (as shown above)
* `.env.db`: PostgreSQL settings
* `.env.pgadmin`: PGAdmin credentials

---

## 📜 API Endpoints

| Endpoint              | Method | Description                                 | Auth Required   |
| --------------------- | ------ | ------------------------------------------- | --------------- |
| `/api/token/`         | POST   | Get JWT access and refresh tokens           | No              |
| `/api/token/refresh/` | POST   | Refresh access token                        | No              |
| `/api/chat/`          | POST   | Chat with Gemini model                      | ✅ JWT / API Key |
| `/api/test-query/`    | POST   | Retrieve top-k vector chunks from RAG store | ✅ JWT           |

---

## 📝 Example `.env.django`

```env
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://infiniti_dev:MySecurePass123!@db:5432/infiniti_dev

# JWT
ACCESS_TOKEN_LIFETIME=1 day
REFRESH_TOKEN_LIFETIME=1 day

# Google Gemini
GENAI_API_KEY=your-gemini-api-key
CHAT_API_KEY=external-client-api-key

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
```

---

## 📦 Installed Packages

* `django`
* `djangorestframework`
* `djangorestframework-simplejwt`
* `celery`
* `redis`
* `google-generativeai`
* `langchain`
* `langchain-google-vertexai`
* `psycopg2-binary`
* `langchain-google-vertexai==2.0.13`
* `google-cloud-bigquery==3.29.0*`
* `google-cloud-datastore==2.20.2* `
* `google-cloud-speech==2.29.0* `
* `google-cloud-texttospeech==2.23.0* `
* `pydub==0.25.1* `
* `sounddevice==0.5.1* `
* `soundfile==0.12.1* `




---

## 📄 License

MIT License. © 2025 Electus-Global-Education

```

---
