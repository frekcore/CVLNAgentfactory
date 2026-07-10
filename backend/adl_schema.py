import re
import yaml
from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+$')
AGENT_ID_RE = re.compile(r'^AGT-\d{3}$')


class LifecycleStatus(str, Enum):
    DRAFT = "Draft"
    PROTOTYPE = "Prototype"
    ALPHA = "Alpha"
    BETA = "Beta"
    PRODUCTION = "Production"
    MAINTENANCE = "Maintenance"
    ARCHIVE = "Archive"


LIFECYCLE_ORDER = [
    LifecycleStatus.DRAFT, LifecycleStatus.PROTOTYPE, LifecycleStatus.ALPHA,
    LifecycleStatus.BETA, LifecycleStatus.PRODUCTION, LifecycleStatus.MAINTENANCE,
    LifecycleStatus.ARCHIVE,
]


def allowed_transitions(current: str) -> List[str]:
    try:
        idx = LIFECYCLE_ORDER.index(LifecycleStatus(current))
    except ValueError:
        return []
    targets = []
    if idx + 1 < len(LIFECYCLE_ORDER):
        targets.append(LIFECYCLE_ORDER[idx + 1].value)
    if current not in (LifecycleStatus.ARCHIVE.value,) and LifecycleStatus.ARCHIVE.value not in targets:
        targets.append(LifecycleStatus.ARCHIVE.value)
    return targets


class BrainMemory(BaseModel):
    scope: Literal["session", "persistent"] = "session"
    owner: str = ""


class BrainEvents(BaseModel):
    subscribe: List[str] = Field(default_factory=list)
    publish: List[str] = Field(default_factory=list)


class Brain(BaseModel):
    registry: dict = Field(default_factory=dict)
    memory: BrainMemory = Field(default_factory=BrainMemory)
    identity: dict = Field(default_factory=dict)
    events: BrainEvents = Field(default_factory=BrainEvents)
    monitoring: dict = Field(default_factory=dict)


class Tool(BaseModel):
    name: str
    type: str = "api"
    description: str = ""
    config: dict = Field(default_factory=dict)


class KnowledgeSource(BaseModel):
    source: str
    type: str = "document"
    description: str = ""


class Permissions(BaseModel):
    read: List[str] = Field(default_factory=list)
    write: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)


class TestCase(BaseModel):
    name: str
    assertion: str


class AgentMeta(BaseModel):
    id: str
    name: str = Field(min_length=3)
    pole: str = Field(min_length=1)
    entity: str = Field(min_length=1)
    version: str = "0.1.0"
    mission: str = Field(min_length=10)
    vision: str = ""
    objectives: List[str] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)

    @field_validator('id')
    @classmethod
    def check_id(cls, v):
        if not AGENT_ID_RE.match(v):
            raise ValueError("id must match pattern AGT-XXX (ex: AGT-042)")
        return v

    @field_validator('version')
    @classmethod
    def check_version(cls, v):
        if not SEMVER_RE.match(v):
            raise ValueError("version must be semver X.Y.Z (ex: 1.0.0)")
        return v


class ADLDocument(BaseModel):
    adl_version: str = "1.0"
    agent: AgentMeta
    brain: Brain = Field(default_factory=Brain)
    tools: List[Tool] = Field(default_factory=list)
    knowledge: List[KnowledgeSource] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
    tests: List[TestCase] = Field(default_factory=list)


def parse_adl_yaml(text: str):
    """Returns (ADLDocument | None, errors: list[{path, message}])."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, [{"path": "yaml", "message": f"Invalid YAML: {e}"}]
    if not isinstance(raw, dict):
        return None, [{"path": "root", "message": "ADL document must be a YAML mapping"}]
    try:
        doc = ADLDocument(**raw)
        return doc, []
    except Exception as e:
        errors = []
        if hasattr(e, 'errors'):
            for err in e.errors():
                path = ".".join(str(p) for p in err.get('loc', []))
                errors.append({"path": path, "message": err.get('msg', 'invalid')})
        else:
            errors.append({"path": "root", "message": str(e)})
        return None, errors


def adl_to_yaml(doc: dict) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False)


def semver_tuple(v: str):
    return tuple(int(x) for x in v.split('.'))
