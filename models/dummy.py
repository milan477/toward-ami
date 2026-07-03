"""Dummy model server — responds with a random letter. For PoC only."""

import random
import string
from fastapi import FastAPI

app = FastAPI(title="Dummy Random Letter", version="0.1")

MODEL_ID = "dummy-random-letter-v0"


@app.get("/info")
def info():
    return {"model_id": MODEL_ID}


@app.post("/query")
def query():
    return {"response": random.choice(string.ascii_uppercase[:4])}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
