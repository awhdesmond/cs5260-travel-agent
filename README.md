# CS5260 Travel Planner Agent

NUS CS5260 Neural Networks and Deep Learning II, AY 2025/26 Semester 2 — Group 9.

A multi-agent AI travel planner that generates complete day-by-day itineraries (flights, hotels, activities) from natural language input. The system implements two orchestration architectures — **Supervisor** (3-level hierarchy) and **Swarm** (flat peer-to-peer) — using identical worker agents, enabling a controlled empirical comparison of multi-agent coordination patterns.

## Prerequisites

- Docker and Docker Compose
- A Google Gemini API key ([aistudio.google.com](https://aistudio.google.com))

## Quick Start

1. **Clone and configure environment:**

```bash
git clone https://github.com/kaiyitkoh/cs5260-travel-agent.git
cd cs5260-travel-agent
cp backend/.env.example backend/.env
```

2. **Copy the environment file** — all shared API keys are pre-filled:

```bash
# .env.example has all keys ready to use — just copy it
cp backend/.env.example backend/.env
```

3. **Start the application:**

```bash
docker compose up -d --build
```

This starts PostgreSQL (with auto-applied migrations) and the FastAPI backend. Wait ~15 seconds for startup.

4. **Verify it's running:**

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","supervisor_ready":true,"swarm_ready":true}
```

## Usage

### Authentication

The system uses JWT authentication. A default admin account is pre-seeded:

```bash
# Login
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@cs5260.nus.edu.sg","password":"NeuralNets5260!"}'
# Returns: {"token":"eyJ...", "user_id":"...", "email":"..."}
```

Use the returned token as `Authorization: Bearer <token>` in all subsequent requests.

### Four-Pass Planning Pipeline

**Pass 1 — Ingestion & Search:** User describes their trip in natural language. The Ingestion Agent extracts parameters, asks clarification questions if needed, and shows a read-back confirmation. Once confirmed, parallel worker agents search for flights (SerpAPI), hotels (Google Search grounding), and activities (Google Maps grounding).

```bash
curl -s -N -X POST http://localhost:8000/plan/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "user_input": "3 days in Bangkok for 2 people, SGD 3000 budget",
    "mode": "supervisor",
    "booking_mode": "sandbox"
  }'
```

Returns SSE stream with `thinking`, `agent_active`, and `options` events.
Set `mode` to `"supervisor"` or `"swarm"` to choose the orchestration architecture.

**Pass 2 — Selection & Meals:** User picks flight and hotel options. The system generates meal options near selected activities using Google Maps grounding.

```bash
curl -s -N -X POST http://localhost:8000/plan/<plan_id>/select \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"flight_selection": 0, "hotel_selection": 0}'
```

**Pass 3 — Meal Selection & Day Planner:** User picks meals. The Day Planner assembles a complete day-by-day itinerary with selected flights, hotels, activities, and meals. The Critic validates geographic feasibility and time-block conflicts.

```bash
curl -s -N -X POST http://localhost:8000/plan/<plan_id>/meals \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"selected_meals": {...}}'
```

**Pass 4 — Confirmation & Booking:** User reviews the final itinerary and confirms. Sandbox booking generates a confirmation ID.

```bash
curl -s -X POST http://localhost:8000/plan/<itinerary_plan_id>/confirm \
  -H "Authorization: Bearer <token>"
# Returns: {"confirmation_id":"SBX-XXXXXXXX","message":"SANDBOX MODE..."}
```

### Other Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with graph readiness |
| `/auth/login` | POST | JWT authentication |
| `/itineraries` | GET | User's saved itinerary history |

## Architecture

```
User Query
    │
    ▼
Ingestion Agent (LLM extraction + clarification + read-back confirmation)
    │
    ▼
Cache Check (pg_trgm fuzzy match on city + preferences)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Supervisor Mode             │  Swarm Mode           │
│  Root Dispatch (L1, no LLM)  │  parallel_workers_node│
│  ├─ Transport Coord (L2)     │  asyncio.gather:      │
│  │  └─ flight_worker (L3)    │   flight_worker ─┐    │
│  ├─ Accom Coord (L2)         │   hotel_worker ──┤    │
│  │  └─ hotel_worker (L3)     │   activities ────┘    │
│  └─ Experiences Coord (L2)   │                       │
│     └─ activities_worker (L3)│                       │
│  (asyncio.gather all L2)     │                       │
└──────────────────────────────────────────────────────┘
    │
    ▼
Critic (deterministic: geo + time block checks)
    │
    ▼
[Pass 1 stops — options event emitted]
    │
    ▼  (user selects flights + hotels)
Meal Generation (Google Maps grounding, proximity-scored)
    │
    ▼  (user selects meals)
Day Planner (LLM assembles day-by-day schedule)
    │
    ▼
Complete Itinerary (flights, hotels, activities, meals, transport)
```

## Tech Stack

- **LLM**: Gemini 3 Flash Preview (thinking_budget=0, max_output_tokens=65536)
- **Grounding**: Google Search (flights, hotels) + Google Maps (activities, meals)
- **Flight Data**: SerpAPI Google Flights (real data, with Gemini fallback)
- **Places Enrichment**: Google Maps Places API (Essentials SKU — place_id, lat/lng, photos)
- **Agent Framework**: LangGraph 1.0.x with asyncio.gather for parallel workers
- **Backend**: FastAPI, PostgreSQL (psycopg3, pg_trgm for cache matching)
- **Auth**: Custom JWT (PyJWT + bcrypt)
- **Streaming**: Server-Sent Events (SSE via sse-starlette)
- **Tracing**: LangSmith (zero-code, env vars only)
- **Caching**: Activities + meal proximity cache with 1-year TTL

## Constraints

- Total test inference cost < SGD 10
- No real booking transactions (sandbox only)
- China destinations supported with soft warning (Google Search grounding may be limited)

## License

Academic project — NUS CS5260, AY 2025/26 Semester 2.
