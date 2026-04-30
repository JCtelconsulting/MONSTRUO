from fastapi import APIRouter, Depends
from plataforma.core import deps

router = APIRouter(prefix="/api/ia", tags=["ia"])


@router.get("/health")
async def health(sess: dict = Depends(deps.require_permission("ia:read"))):
    return {"status": "ok", "module": "ia"}
