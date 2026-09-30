from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import analysis, cleanup, library, review, tracks

app = FastAPI(title="Cueflow API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tracks.router)
app.include_router(library.router)
app.include_router(review.router)
app.include_router(cleanup.router)
app.include_router(analysis.router)


@app.get("/health")
def health():
    return {"status": "ok"}
