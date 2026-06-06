from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, recommend
from app.core.config import get_settings

settings = get_settings()

_cors_origins = [
    o.strip()
    for o in (settings.reco_cors_origins or "").split(",")
    if o.strip()
]
if not _cors_origins:
    _cors_origins = ["http://localhost:3000"]

app = FastAPI(
    title="Raspquery Reco",
    description="Moteur de recommandation StackAI (Python)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(recommend.router)
