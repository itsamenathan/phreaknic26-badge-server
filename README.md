# PhreakNIC 26 Badge Server

Python web service for managing PhreakNIC badge artwork, from attendee selection through to the printable work queue.

## Features
- Attendee badge page (`/badges/{unique_id}`) shows the badge holder’s name and current artwork options. (Legacy `/id={unique_id}` still works.) A landing page `/` lets users enter their badge ID.
- Admin artwork screen (`/admin/images`) lets authenticated staff add, preview, and delete available badge artwork.
- Admin badge management screen (`/admin/badges`) registers badge IDs, names, and MAC addresses, and lists existing entries for quick updates.
- Admin work queue (`/admin/work-items`) shows pending items with controls to mark them processed or delete them.
- Admin hub (`/admin`) links to the badge, artwork, and queue tools behind a single login.
- Programmatic badge API (`POST /admin/api/badges`) lets trusted systems register attendees (ID, name, MAC) via JSON.
- JSON lookup endpoints allow trusted systems or devices to resolve badges by MAC address.
- Authenticated work API (`GET /admin/api/work-items/next`) returns the oldest unprocessed queue entry as JSON and marks it processed.
- Built with FastAPI, SQLAlchemy’s async engine, Jinja2 templates, and lightweight HTML/CSS for quick operator workflows.

## Prerequisites
1. Python 3.11+
2. PostgreSQL instance with access credentials.
3. [`uv`](https://github.com/astral-sh/uv) for dependency and virtualenv management.
4. [`alembic`](https://alembic.sqlalchemy.org/) (already listed in `pyproject.toml`) for database migrations.

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
| `WORK_BASIC_AUTH_USERNAME` | Username required for all admin endpoints and `GET /admin/api/work-items/next` |
| `WORK_BASIC_AUTH_PASSWORD` | Password required for all admin endpoints and `GET /admin/api/work-items/next` |
| `DB_POOL_MIN_SIZE` *(optional)* | Minimum PostgreSQL pool size (default `1`) |
| `DB_POOL_MAX_SIZE` *(optional)* | Maximum PostgreSQL pool size (default `10`) |

Use the same credentials to access `/admin/badges`, `/admin/images`, `/admin/work-items`, and the admin APIs.

## Database Migrations
The project uses Alembic for schema management.

- **Fresh database:** create the database, ensure `DATABASE_URL` is set, then run:
  ```bash
  alembic upgrade head
  ```
- **Existing database (pre-Alembic):** tell Alembic the current schema is at the baseline revision, then run the latest migrations:
  ```bash
  alembic stamp b8bec1855043
  alembic upgrade head
  ```

Run migrations every time you pull changes that update the schema.

## Database Schema
Below is the schema that corresponds to the current migrations. Adjust names and columns as needed, but preserve the referenced fields.

```sql
CREATE TABLE badges (
    unique_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mac_address VARCHAR(17) UNIQUE
);

CREATE TABLE badge_images (
    unique_id TEXT NOT NULL REFERENCES badges(unique_id) ON DELETE CASCADE,
    image_label TEXT NOT NULL,
    image_base64 TEXT NOT NULL,
    image_mime_type TEXT,
    PRIMARY KEY (unique_id, image_label)
);

CREATE TABLE available_images (
    id SERIAL PRIMARY KEY,
    image_label TEXT UNIQUE NOT NULL,
    image_base64 TEXT NOT NULL,
    image_mime_type TEXT,
    image_color TEXT NOT NULL,
    image_font TEXT NOT NULL
);

CREATE TABLE work_queue (
    id BIGSERIAL PRIMARY KEY,
    unique_id TEXT NOT NULL,
    name TEXT NOT NULL,
    image_label TEXT NOT NULL,
    image_base64 TEXT NOT NULL,
    image_mime_type TEXT,
    image_color TEXT NOT NULL,
    image_font TEXT NOT NULL,
    font_size INTEGER,
    text_x INTEGER,
    text_y INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_work_queue_processed_created
    ON work_queue (processed_at, created_at);
```

## Endpoints

- `GET /badges/{unique_id}`  
  Renders badge details and available images. Selecting an image and submitting the form queues the work item. (Legacy `/id={unique_id}` remains available.)

- `POST /badges/{unique_id}`  
  Handles image selection submission. On success, redirects back to the GET view with a confirmation banner.

- `GET /admin` *(Basic Auth)*  
  Landing page that links to badge creation, artwork management, and queue review.

- `GET /admin/images` *(Basic Auth)*  
  Shows the upload form plus a gallery of existing artwork with delete buttons.

- `POST /admin/images` *(Basic Auth)*  
  Saves or replaces an available image.

- `POST /admin/images/delete` *(Basic Auth)*  
  Deletes an available image by label.

- `GET /admin/badges` *(Basic Auth)*  
  Displays a form to register or update attendees, including MAC addresses used by firmware tooling.

- `POST /admin/badges` *(Basic Auth)*  
  Saves the badge ID, name, and MAC address so the attendee can access `/badges/{unique_id}`.

- `GET /admin/work-items` *(Basic Auth)*  
  Displays up to 50 recent work items (toggle processed items with `?show_processed=1`).

- `POST /admin/work-items/{id}/mark` *(Basic Auth)*  
  Marks a work item as processed.

- `POST /admin/work-items/{id}/delete` *(Basic Auth)*  
  Permanently removes a work item.

- `POST /admin/api/badges` *(Basic Auth, JSON)*  
  Accepts a JSON body `{"unique_id": "...", "name": "...", "mac_address": "AA:BB:CC:DD:EE:FF"}` and returns `201 Created` for new badges or `200 OK` when updating an existing record. The MAC address is normalised and must be unique.

- `GET /admin/api/badges/mac/{mac_address}` *(Basic Auth)*  
  Returns the full badge profile (ID, name, available images) for the given MAC address. Responds with `404` if no badge matches.

- `GET /admin/api/work-items/next` *(Basic Auth)*  
  Returns the oldest unprocessed queue entry:
  ```json
  {
    "badge_id": "ABC123",
    "name": "Jane Doe",
    "image_label": "Badge Art 1",
    "image_base64": "<base64 payload>",
    "image_mime_type": "image/png",
    "image_color": "black",
    "image_font": "Awkward.ttf",
    "font_size": 18,
    "text_x": 120,
    "text_y": 60,
    "created_at": "2024-08-01T12:34:56.789123+00:00"
  }
  ```
  Responds with `204 No Content` when no work is available.

- `GET /api/badges/mac/{mac_address}`  
  Public JSON endpoint that returns the badge ID, name, and MAC address. Useful for firmware tools that only know the hardware MAC.

- `GET /healthz`  
  Lightweight readiness probe returning `{"status": "ok"}`.

## Error Handling & Security
- All database interactions run through SQLAlchemy’s async engine with an explicit session per request.
- Basic authentication with constant-time comparisons protects the work queue endpoint.
- Graceful error messages are displayed for badge lookup, enqueue failures, and queue retrieval issues.
- Admin pages reuse the same basic auth and surface upload/queue errors inline.

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
