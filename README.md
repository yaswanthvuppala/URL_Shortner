# Production URL Shortener API

A robust, production-ready URL Shortener API built using **FastAPI**, **SQLite** for persistent storage, and **Redis** for high-performance caching.

This service is designed to map long URLs to short, unique base62 codes, serve extremely fast redirects via a caching layer, and collect basic usage analytics.

---

## Features

- **FastAPI Core**: Highly performant, asynchronous-capable REST framework with automatic Swagger/OpenAPI documentation.
- **Dual-Layer Storage**:
  - **SQLite**: Reliable local relational database for persistent storage of URL mappings and click analytics.
  - **Redis Cache**: Low-latency caching layer to serve redirects instantly and minimize database read queries.
- **Base62 Code Generation**: Randomized, collision-safe 6-character short codes (supporting uppercase, lowercase, and numeric characters).
- **Caching Strategy**: Writes are cached immediately upon URL shortening with a 24-hour Time-To-Live (TTL). Reads first query Redis; on a cache miss, the service queries SQLite and updates Redis.
- **Click Analytics**: Tracks total click counts and creation timestamps for each shortened URL.

---

## System Architecture

```mermaid
graph TD
    Client[Client Browser/HTTP Client]
    API[FastAPI Web Server]
    RedisCache[(Redis Cache)]
    SQLiteDB[(SQLite Database)]

    %% Shorten Flow
    Client -->|1. POST /shorten| API
    API -->|2. Save mapping| SQLiteDB
    API -->|3. Cache mapping 24h TTL| RedisCache
    API -->|4. Return Short URL| Client

    %% Redirect Flow (Cache Hit)
    Client -->|5. GET /{short_code}| API
    API -->|6. Query cache| RedisCache
    RedisCache -->|7. Return Cached URL| API
    API -->|8. Async click increment| SQLiteDB
    API -->|9. 307 Redirect| Client

    %% Redirect Flow (Cache Miss)
    RedisCache -.->|6a. Cache Miss| API
    API -->|6b. Query database| SQLiteDB
    SQLiteDB -->|6c. Return URL| API
    API -->|6d. Update Cache| RedisCache
```

---

## Technical Details

### Database Schema (`url_mappings` table)
| Column Name | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key, Index | Unique autoincrement ID |
| `short_code`| String | Unique, Index | 6-character unique base62 code |
| `long_url` | String | Not Null | Original long URL to redirect to |
| `clicks` | Integer | Default: 0 | Number of redirection clicks |
| `created_at`| DateTime | Default: UTC Now | Timestamp when record was created |

---

## Prerequisites

Before running the application, make sure you have the following installed:
- **Python 3.8+**
- **Docker & Docker Compose** (for running the Redis container)

---

## Getting Started

### 1. Set Up the Python Virtual Environment

Clone or open the project directory in your terminal, then run:

**On Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

Install the required packages using `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 3. Spin Up the Redis Container

The application uses Redis for caching. Start the Redis instance in the background using Docker Compose:
```bash
docker compose up -d
```
*This will pull the lightweight `redis:alpine` image and run it on port `6379`.*

### 4. Run the FastAPI Application

Start the local development server using `uvicorn`:
```bash
uvicorn main:app --reload
```
The server will start on **`http://localhost:8000`**.

---

## API Documentation & Usage

FastAPI automatically generates documentation. Once the server is running, visit:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Endpoints

#### 1. Root Redirect
- **Endpoint**: `GET /`
- **Description**: Automatically redirects you to the Swagger `/docs` page for easy testing.

#### 2. Shorten a URL
- **Endpoint**: `POST /shorten`
- **Content-Type**: `application/json`
- **Request Body**:
  ```json
  {
    "long_url": "https://www.google.com"
  }
  ```
- **Response** (Status Code `201 Created`):
  ```json
  {
    "short_url": "http://localhost:8000/aB3xD2"
  }
  ```

#### 3. Redirection
- **Endpoint**: `GET /{short_code}`
- **Description**: Redirects client browser to the destination URL via a `307 Temporary Redirect` response.
- **Cache Logic**:
  - Checks Redis first. If found (Cache Hit), immediately increments click count in SQLite and redirects.
  - If not found in Redis (Cache Miss), queries SQLite, populates the Redis cache, increments click count in SQLite, and redirects.

#### 4. Analytics
- **Endpoint**: `GET /analytics/{short_code}`
- **Response** (Status Code `200 OK`):
  ```json
  {
    "short_code": "aB3xD2",
    "long_url": "https://www.google.com",
    "clicks": 1,
    "created_at": "2026-06-20T10:00:00Z"
  }
  ```

---

## Production Recommendations & Next Steps

If deploying this API in a high-traffic production environment, consider the following enhancements:
1. **Decoupled Analytics**: Currently, click counts are written to SQLite synchronously during the redirection flow. For high write volumes, decouple analytics updates using a queue (e.g., Celery, RabbitMQ) or increment them directly in Redis and sync them back to the database periodically.
2. **Short Code Pre-generation**: Instead of generating a base62 code on the fly and checking for database collisions (up to 10 retries), run a background service to pre-generate unique codes or use a distributed ID generator (e.g., Snowflake) converted to base62.
3. **Authentication & Rate Limiting**: Protect the `/shorten` endpoint using token-based authentication (JWT) and implement IP-based rate limiting to prevent spam.
4. **URL Safety Validation**: Integrate with a safe-browsing service (like Google Safe Browsing API) to ensure users are not shortening malicious URLs.
