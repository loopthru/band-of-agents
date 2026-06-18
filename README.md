# band-of-agents

A small FastAPI scaffold for the Band of Agents Hackathon.

## Local Setup

Create and activate a virtual environment, then install the project with development dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For a runtime-only install, use:

```bash
python -m pip install .
```

The editable development install keeps tests pointed at the current `src/` files as you make changes.

## Run Locally

Start the API with:

```bash
uvicorn band_of_agents.main:app --host 0.0.0.0 --port 8000 --reload
```

The app exposes:

- `GET /` for basic service metadata.
- `GET /health` for a simple health check.
- `POST /review` to run placeholder review agents asynchronously and return a combined answer.

Example review request:

```bash
curl -X POST http://localhost:8000/review ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"release readiness\"}"
```

## Tests

Run the test suite with:

```bash
python -m pytest
```

## Render Deployment

This repository includes `render.yaml` for a Python web service.

Render build command:

```bash
python -m pip install .
```

Render start command:

```bash
uvicorn band_of_agents.main:app --host 0.0.0.0 --port $PORT
```
