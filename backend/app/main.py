from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal, create_all_tables
from app.domains.tax.rules_seed import ensure_seed_rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all_tables()
    with SessionLocal() as db:
        ensure_seed_rules(db)
        db.commit()
    yield


app = FastAPI(title="AI Finance Controller", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
