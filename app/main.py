import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth
from .routers import products
from .routers import liked_games
from .routers import order_buy
from .routers import coupons
from .routers import shopping_car
from .routers import user_points
from .database import Base, engine
from .routers import tracking

app = FastAPI(title="Reactive FastAPI Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve locally-stored invoice files (see app/util/local_storage.py).
_invoices_dir = Path(os.getenv("INVOICES_DIR", "/data/invoices"))
_invoices_dir.mkdir(parents=True, exist_ok=True)
app.mount("/invoices", StaticFiles(directory=str(_invoices_dir)), name="invoices")

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health_check():
    """Simple health endpoint that logs a message on each call."""
    print("[health] backend is alive")
    return {"status": "ok"}

app.include_router(products.router)
app.include_router(auth.router)
app.include_router(liked_games.router)
app.include_router(order_buy.router)
app.include_router(shopping_car.router)
app.include_router(coupons.router)
app.include_router(user_points.router)
app.include_router(tracking.router)