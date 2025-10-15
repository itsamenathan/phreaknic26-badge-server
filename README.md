# PhreakNIC 26 Badge Server

Python web service for selecting badge artwork and queueing work items for downstream processing.

## Features
- Public `GET /id={unique_id}` endpoint renders a minimal UI showing the badge holder's name and available artwork thumbnails.
- Submitting the form enqueues the badge selection (unique id, name, selected image) into PostgreSQL for later processing.
- Authenticated `GET /get-work` endpoint returns the oldest unprocessed queue entry as JSON and marks it processed to prevent duplication.
- Built with FastAPI, asyncpg connection pooling, server-side templates, and basic HTML/CSS for a clean interactive experience.

## Prerequisites
1. Python 3.11+
2. PostgreSQL instance with access credentials.
3. [`uv`](https://github.com/astral-sh/uv) for dependency and virtualenv management.

Install dependencies with:
```bash
uv sync
```

Run the development server:
```bash
uv run uvicorn app.main:app --reload
```

## Configuration
Set the following environment variables before launching the app:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@host:port/dbname`) |
| `WORK_BASIC_AUTH_USERNAME` | Username required to call `GET /get-work` |
| `WORK_BASIC_AUTH_PASSWORD` | Password required to call `GET /get-work` |
| `DB_POOL_MIN_SIZE` *(optional)* | Minimum PostgreSQL pool size (default `1`) |
| `DB_POOL_MAX_SIZE` *(optional)* | Maximum PostgreSQL pool size (default `10`) |

## Database Schema
Below is a reference schema used by the application. Adjust names and columns as needed, but preserve the referenced fields.

```sql
CREATE TABLE badges (
    unique_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE badge_images (
    id SERIAL PRIMARY KEY,
    unique_id TEXT NOT NULL REFERENCES badges(unique_id) ON DELETE CASCADE,
    image_label TEXT NOT NULL,
    image_base64 TEXT NOT NULL,
    image_mime_type TEXT NOT NULL DEFAULT 'image/png'
);

CREATE TABLE work_queue (
    id BIGSERIAL PRIMARY KEY,
    unique_id TEXT NOT NULL,
    name TEXT NOT NULL,
    image_label TEXT NOT NULL,
    image_base64 TEXT NOT NULL,
    image_mime_type TEXT NOT NULL DEFAULT 'image/png',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_work_queue_processed_created
    ON work_queue (processed_at, created_at);
```

## Endpoints

- `GET /id={unique_id}`  
  Renders badge details and available images. Selecting an image and submitting the form queues the work item.

- `POST /id={unique_id}`  
  Handles image selection submission. On success, redirects back to the GET view with a confirmation banner.

- `GET /get-work` *(Basic Auth)*  
  Returns the oldest unprocessed queue entry:
  ```json
  {
    "unique_id": "ABC123",
    "name": "Jane Doe",
    "image_label": "Badge Art 1",
    "image_base64": "<base64 payload>",
    "image_mime_type": "image/png",
    "created_at": "2024-08-01T12:34:56.789123+00:00"
  }
  ```
  Responds with `204 No Content` when no work is available.

- `GET /healthz`  
  Lightweight readiness probe returning `{"status": "ok"}`.

## Error Handling & Security
- All database operations are wrapped in connection pooling via asyncpg.
- Basic authentication with constant-time comparisons protects the work queue endpoint.
- Graceful error messages are displayed for badge lookup, enqueue failures, and queue retrieval issues.

## Testing
Install optional development dependencies:
```bash
uv sync --group dev
```

Add tests under `tests/` using `pytest` and `pytest-asyncio`. Run them with:
```bash
uv run pytest
```

## Containerised Deployment
Build and run everything with Docker Compose:

```bash
docker compose up -d --build
```

This starts the FastAPI app on port `8000` and a PostgreSQL 15 instance with seeded credentials. Override environment variables in `docker-compose.yml` or export them before running to suit your environment. Stop the stack with:

```bash
docker compose down
```
