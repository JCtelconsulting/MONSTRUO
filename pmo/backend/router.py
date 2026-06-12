from fastapi import APIRouter, Depends
from plataforma.core import deps

router = APIRouter(prefix="/api/pmo", tags=["pmo"])


@router.get("/health")
async def health(sess: dict = Depends(deps.require_permission("pmo:read"))):
    return {"status": "ok", "module": "pmo"}
