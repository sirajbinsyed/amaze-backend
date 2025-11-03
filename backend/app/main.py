from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.pool import init_pool, close_pool
from .routers import auth as auth_router
from .routers import crm as crm_router
from .routers import sales as sales_router
from .routers import projects as projects_router
from .routers import admin as admin_router
from .routers import designer as designer_router
from .routers import printing as printing_router
from .routers import logistics as logistics_router
from .routers import hr as hr_router
from .routers import accounts as accounts_router






@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

app = FastAPI(title="Choisircraft ERP API", version="0.1.0", lifespan=lifespan)

# Adjust CORS as needed for your frontend origin(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(crm_router.router)
app.include_router(sales_router.router)
app.include_router(projects_router.router)
app.include_router(admin_router.router)
app.include_router(designer_router.router)
app.include_router(printing_router.router)
app.include_router(logistics_router.router)
app.include_router(hr_router.router)
app.include_router(accounts_router.router)





@app.get("/health")
async def health():
    return {"status": "ok"}
