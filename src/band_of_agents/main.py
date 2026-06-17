from fastapi import FastAPI

app = FastAPI(title="Band of Agents")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "name": "band-of-agents",
        "status": "ok",
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok"}
