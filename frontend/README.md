# NEXO Client (C0)

Browser client for the two-tab live ride loop.

## Run

Frontend (from `frontend/`):

```
npm install
npm run dev
```

Open http://localhost:5173

API and WebSocket traffic is proxied from the Vite origin to http://localhost:8000. Do not enable backend CORS for this milestone.

Backend (from `frontend/`, recommended on Windows):

```
python scripts/run_backend.py
```

This launcher only starts the existing backend. It re-encodes `DATABASE_URL` when the password contains `@`, imports models before `app.main` to avoid a circular import, and sets UTF-8 so lifespan logs can print. It does not change backend production code.

Equivalent backend-only command after those environment issues are fixed:

```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Smoke test

With both servers running:

```
python scripts/e2e_ride_loop.py
```
