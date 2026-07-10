from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from database import db
from adl_schema import parse_adl_yaml
from auth_utils import get_current_actor
from doctrine import check_doctrine_compliance, DOCTRINE_VERSION

router = APIRouter(tags=["doctrine", "external"])

EXTERNAL_SYSTEMS = [
    {"key": "laurent-ia", "name": "Laurent.ia", "description": "Système IA applicatif indépendant (interface conversationnelle)"},
    {"key": "kora", "name": "KORA", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "frek", "name": "FREK", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "kiltikonet", "name": "Kiltikonet", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "labelos", "name": "LabelOS", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "good-mood", "name": "Good Mood", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "cvl-academy", "name": "CVL Academy", "description": "Système indépendant de l'écosystème CVLN"},
    {"key": "cvln-central", "name": "CVLN Central", "description": "Système central du groupe CVLN"},
]


class DoctrineCheckPayload(BaseModel):
    adl_yaml: str


@router.get("/doctrine")
async def get_doctrine(actor: dict = Depends(get_current_actor)):
    doc = await db.doctrine.find_one({"version": DOCTRINE_VERSION}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctrine not found")
    return doc


@router.post("/doctrine/check")
async def doctrine_check(payload: DoctrineCheckPayload, actor: dict = Depends(get_current_actor)):
    doc, errors = parse_adl_yaml(payload.adl_yaml)
    if errors:
        raise HTTPException(status_code=422, detail={"type": "validation", "errors": errors})
    compliance = check_doctrine_compliance(doc.model_dump())
    violations = [c for c in compliance if not c["passed"]]
    return {"doctrine_version": DOCTRINE_VERSION, "compliant": len(violations) == 0,
            "checks": compliance, "violations": violations}


@router.get("/external")
async def list_external_systems(actor: dict = Depends(get_current_actor)):
    return {"principle": "Chaque système reste indépendant. Communication future via contrats d'API uniquement.",
            "systems": EXTERNAL_SYSTEMS}


@router.api_route("/external/{system_key}", methods=["GET", "POST"])
async def external_system_placeholder(system_key: str):
    system = next((s for s in EXTERNAL_SYSTEMS if s["key"] == system_key), None)
    if not system:
        raise HTTPException(status_code=404, detail="Unknown external system")
    raise HTTPException(status_code=501, detail={
        "system": system["name"], "status": "reserved",
        "message": f"Point d'entrée API réservé pour {system['name']}. Contrat d'interface à définir en V2. Le système reste indépendant de la Factory."})
