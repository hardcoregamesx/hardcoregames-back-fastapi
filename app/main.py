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
from .routers import rewards
from .routers import sorteos
from .database import Base, engine
from .routers import tracking

app = FastAPI(title="Reactive FastAPI Microservice")

# allow_origins=["*"] combinado con allow_credentials=True es una
# combinacion invalida: Starlette solo hace echo del Origin real (necesario
# para que el navegador acepte la respuesta) cuando la request trae un
# header Cookie. Como este API se autentica con Bearer token (sin cookies),
# toda respuesta a un POST/PUT/DELETE autenticado volvia con
# "Access-Control-Allow-Origin: *" + "Access-Control-Allow-Credentials: true",
# combinacion que el navegador rechaza sin excepcion. Afectaba a cualquier
# endpoint autenticado por POST (cupones, canje de puntos, ahora la ruleta),
# no solo a Hardcore Rewards. Se resuelve listando los origenes reales.
ALLOWED_ORIGINS = [
    "https://www.hardcoregames.co",
    "https://hardcoregames.co",
    "https://srv936408.hstgr.cloud",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
app.include_router(rewards.router)
app.include_router(sorteos.router)
app.include_router(tracking.router)