"""FREK AI Workforce — 38 first active employee roles.

Definitions only: agents start PROTOTYPE/dry-run and remain governed by CVLN Agent Factory.
MetaCVLN orchestrates capabilities; Agent Factory owns lifecycle/permissions/runtime control.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class FrekRole:
    id: str
    entity: str
    pole: str
    name: str
    mission: str
    capability: str
    read_scope: Tuple[str, ...]
    write_scope: Tuple[str, ...] = ()
    human_gate: bool = False


CORE = "FREKCORE"
ANSL = "FREKANSLA"
RAW = "FREKRAW"
LUC = "FREK Luciole"

# Dedicated range. AGT-000 remains Agent Factory autonomous-runtime authority.
FREK_WORKFORCE = (
    # FREKCORE — 10
    FrekRole("AGT-301", CORE, "FREKCORE", "General Manager FREKCORE", "Coordinate FREKCORE strategy and operations without overriding protocol or human governance.", "frekcore.manage", ("frekcore:*",), ("frekcore:plans",), True),
    FrekRole("AGT-302", CORE, "FREKCORE", "Protocol Lead", "Maintain versioned FREK protocol semantics and prepare governed protocol changes.", "frekcore.protocol", ("frekcore:protocol", "frekcore:evidence"), ("frekcore:protocol:proposal",), True),
    FrekRole("AGT-303", CORE, "FREKCORE", "CTO / Lead Engineer", "Coordinate FREKCORE runtime architecture, reliability and engineering execution.", "frekcore.engineering", ("frekcore:runtime", "frekcore:metrics"), ("frekcore:engineering:proposal",), True),
    FrekRole("AGT-304", CORE, "FREKCORE", "Backend / Infrastructure Engineer", "Implement and maintain governed FREKCORE backend and infrastructure work.", "frekcore.backend", ("frekcore:runtime",), ("frekcore:worktree",)),
    FrekRole("AGT-305", CORE, "FREKCORE", "Security & Cryptography Engineer", "Assess Core cryptographic and operational security and prepare remediations.", "frekcore.security", ("frekcore:security", "frekcore:audit"), ("frekcore:security:proposal",), True),
    FrekRole("AGT-306", CORE, "FREKCORE", "Product Lead", "Own Core API, operator and verification product requirements within trust invariants.", "frekcore.product", ("frekcore:product",), ("frekcore:roadmap",)),
    FrekRole("AGT-307", CORE, "FREKCORE", "Developer Experience / SDK Engineer", "Improve FREKCORE SDKs, integration tooling and developer documentation.", "frekcore.devex", ("frekcore:sdk", "frekcore:protocol"), ("frekcore:sdk:worktree",)),
    FrekRole("AGT-308", CORE, "FREKCORE", "Data / Indexing Engineer", "Maintain trustworthy Core indexing, event and proof query models.", "frekcore.indexing", ("frekcore:data",), ("frekcore:index:proposal",)),
    FrekRole("AGT-309", CORE, "FREKCORE", "Standards & Domain Governance Lead", "Coordinate public standards and domain profiles without changing runtime authority.", "frek.standard.governance", ("frekcore:protocol", "frek:standards"), ("frek:standards:proposal",), True),
    FrekRole("AGT-310", CORE, "FREKCORE", "Enterprise Partnerships & Operations", "Prepare enterprise integrations, operations and compliance coordination for FREKCORE.", "frekcore.enterprise_ops", ("frekcore:operations",), ("frekcore:operations:proposal",), True),

    # FREKANSLA — 10
    FrekRole("AGT-311", ANSL, "FREKANSLA", "General Manager FREKANSLA", "Coordinate FREKANSLA business and product-line execution within FREK boundaries.", "frekansla.manage", ("frekansla:*",), ("frekansla:plans",), True),
    FrekRole("AGT-312", ANSL, "FREKANSLA", "Head of Product", "Maintain the FREKANSLA portfolio and product roadmap.", "frekansla.product", ("frekansla:product",), ("frekansla:roadmap",)),
    FrekRole("AGT-313", ANSL, "FREKANSLA", "DAW Product Lead", "Own DAW workflow requirements and creator-facing product decisions.", "frekansla.daw_product", ("frekansla:daw",), ("frekansla:daw:proposal",)),
    FrekRole("AGT-314", ANSL, "FREKANSLA", "Plugins Product Lead", "Own plugin framework, catalog and developer ecosystem requirements.", "frekansla.plugins", ("frekansla:plugins",), ("frekansla:plugins:proposal",)),
    FrekRole("AGT-315", ANSL, "FREKANSLA", "Audio Director / DSP Lead", "Maintain audio-engine, DSP and sound-quality direction.", "frekansla.dsp", ("frekansla:audio",), ("frekansla:audio:proposal",)),
    FrekRole("AGT-316", ANSL, "FREKANSLA", "CTO / Lead Engineer", "Coordinate FREKANSLA software architecture and engineering delivery.", "frekansla.engineering", ("frekansla:runtime",), ("frekansla:engineering:proposal",), True),
    FrekRole("AGT-317", ANSL, "FREKANSLA", "DAW / Platform Engineer", "Implement DAW platform capabilities against approved interfaces.", "frekansla.daw_engineering", ("frekansla:daw",), ("frekansla:worktree",)),
    FrekRole("AGT-318", ANSL, "FREKANSLA", "SDK / Developer Experience Engineer", "Build audio/plugin SDK and developer integration experience.", "frekansla.devex", ("frekansla:sdk", "frekcore:protocol"), ("frekansla:sdk:worktree",)),
    FrekRole("AGT-319", ANSL, "FREKANSLA", "Creator & Developer Relations", "Collect creator/developer feedback and support adoption without product decision authority.", "frekansla.devrel", ("frekansla:community",), ("frekansla:feedback",)),
    FrekRole("AGT-320", ANSL, "FREKANSLA", "QA / Audio Quality Lead", "Validate FREKANSLA release, compatibility and audio quality gates.", "frekansla.qa", ("frekansla:builds",), ("frekansla:qa:results",)),

    # FREKRAW — 9
    FrekRole("AGT-321", RAW, "FREKRAW", "General Manager FREKRAW", "Coordinate FREKRAW capture and data operations without assuming Core trust authority.", "frekraw.manage", ("frekraw:*",), ("frekraw:plans",), True),
    FrekRole("AGT-322", RAW, "FREKRAW", "Head of Product", "Maintain capture, ingestion and edge product roadmap.", "frekraw.product", ("frekraw:product",), ("frekraw:roadmap",)),
    FrekRole("AGT-323", RAW, "FREKRAW", "CTO / Lead Engineer", "Coordinate capture, ingestion and edge architecture.", "frekraw.engineering", ("frekraw:runtime",), ("frekraw:engineering:proposal",), True),
    FrekRole("AGT-324", RAW, "FREKRAW", "Ingestion / Edge Engineer", "Implement governed source connectors and edge ingestion flows.", "frekraw.ingestion", ("frekraw:sources",), ("frekraw:worktree",)),
    FrekRole("AGT-325", RAW, "FREKRAW", "Data Lead", "Govern source data modeling, normalization and enrichment.", "frekraw.data", ("frekraw:data",), ("frekraw:data:proposal",)),
    FrekRole("AGT-326", RAW, "FREKRAW", "Data Pipeline Engineer", "Implement qualified-source data pipelines and controlled backfills.", "frekraw.pipeline", ("frekraw:pipeline",), ("frekraw:worktree",)),
    FrekRole("AGT-327", RAW, "FREKRAW", "Data Quality & Validation Lead", "Validate source data quality; never claim Core verification or certification.", "frekraw.quality", ("frekraw:data",), ("frekraw:quality:results",)),
    FrekRole("AGT-328", RAW, "FREKRAW", "Field Operations Manager", "Coordinate physical capture deployment, calibration and field maintenance.", "frekraw.field_ops", ("frekraw:field",), ("frekraw:field:plans",), True),
    FrekRole("AGT-329", RAW, "FREKRAW", "Cultural Data Specialist", "Preserve cultural context and semantic fidelity at source.", "frekraw.cultural_context", ("frekraw:data", "frek:standards"), ("frekraw:context:proposal",)),

    # FREK Luciole / V3 — 9
    FrekRole("AGT-330", LUC, "FREK-LUCIOLE", "General Manager FREK Luciole / V3", "Coordinate the Luciole/V3 hardware product line and lifecycle.", "frek.luciole.manage", ("frek:luciole:*",), ("frek:luciole:plans",), True),
    FrekRole("AGT-331", LUC, "FREK-LUCIOLE", "Hardware Lead", "Own Luciole electronics architecture and hardware engineering direction.", "frek.luciole.hardware", ("frek:luciole:hardware",), ("frek:luciole:hardware:proposal",), True),
    FrekRole("AGT-332", LUC, "FREK-LUCIOLE", "Electronics Engineer", "Implement and test Luciole electronics designs.", "frek.luciole.electronics", ("frek:luciole:hardware",), ("frek:luciole:worktree",)),
    FrekRole("AGT-333", LUC, "FREK-LUCIOLE", "Industrial / Hardware Designer", "Design manufacturable, robust and testable Luciole physical systems.", "frek.luciole.industrial_design", ("frek:luciole:hardware",), ("frek:luciole:design:proposal",)),
    FrekRole("AGT-334", LUC, "FREK-LUCIOLE", "Firmware Lead", "Own secure firmware architecture, boot, OTA and device-runtime controls.", "frek.luciole.firmware", ("frek:luciole:firmware",), ("frek:luciole:firmware:proposal",), True),
    FrekRole("AGT-335", LUC, "FREK-LUCIOLE", "Embedded / Device Engineer", "Implement Luciole drivers, peripherals, communications and recovery behavior.", "frek.luciole.embedded", ("frek:luciole:firmware",), ("frek:luciole:worktree",)),
    FrekRole("AGT-336", LUC, "FREK-LUCIOLE", "Security & Cryptography Lead — Device", "Own Luciole device PKI, secure-element and hardware threat-model proposals.", "frek.luciole.security", ("frek:luciole:security",), ("frek:luciole:security:proposal",), True),
    FrekRole("AGT-337", LUC, "FREK-LUCIOLE", "Device Security / Testing Engineer", "Test Luciole device security, tamper, fault and side-channel controls.", "frek.luciole.security_test", ("frek:luciole:security",), ("frek:luciole:test:results",)),
    FrekRole("AGT-338", LUC, "FREK-LUCIOLE", "Hardware QA & Manufacturing Lead", "Govern Luciole manufacturing quality, provisioning traceability and RMA evidence.", "frek.luciole.manufacturing_qa", ("frek:luciole:manufacturing",), ("frek:luciole:qa:results",), True),
)

assert len(FREK_WORKFORCE) == 38
assert len({r.id for r in FREK_WORKFORCE}) == 38
assert len({r.capability for r in FREK_WORKFORCE}) == 38
