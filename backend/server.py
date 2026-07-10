from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Depends
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import client
from seed_data import seed_all
from adl_schema import parse_adl_yaml, LIFECYCLE_ORDER
from auth_utils import get_current_actor
import registry_routes
import identity_routes
import core_routes
import generator_routes
import external_routes
import daily_closing_routes
import entity_routes
import workforce_routes
import finance_routes
import knowledge_routes
import evolution_routes
import founder_routes
from seed_workforce import seed_workforce
from doctrine import seed_doctrine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_all()
    await seed_doctrine()
    await seed_workforce()
    logger.info("CVLN Agent Factory — Core Services started")
    yield
    client.close()


app = FastAPI(title="CVLN Agent Factory — Agent Operating System Layer", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "CVLN Agent Factory", "layer": "Agent Operating System Layer", "version": "1.0.0"}


class ADLValidatePayload(BaseModel):
    adl_yaml: str


@api_router.post("/adl/validate")
async def validate_adl(payload: ADLValidatePayload, actor: dict = Depends(get_current_actor)):
    doc, errors = parse_adl_yaml(payload.adl_yaml)
    if errors:
        return {"valid": False, "errors": errors, "parsed": None}
    return {"valid": True, "errors": [], "parsed": doc.model_dump()}


@api_router.get("/adl/lifecycle-states")
async def lifecycle_states():
    return [s.value for s in LIFECYCLE_ORDER]


api_router.include_router(registry_routes.router)
api_router.include_router(identity_routes.router)
api_router.include_router(core_routes.router)
api_router.include_router(generator_routes.router)
api_router.include_router(external_routes.router)
api_router.include_router(daily_closing_routes.router)
api_router.include_router(entity_routes.router)
api_router.include_router(workforce_routes.router)
api_router.include_router(finance_routes.router)
api_router.include_router(knowledge_routes.router)
api_router.include_router(evolution_routes.router)
api_router.include_router(founder_routes.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
