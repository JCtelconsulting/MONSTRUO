from fastapi import APIRouter, Depends
from plataforma.core import deps

router = APIRouter(prefix="/api/zabbix", tags=["zabbix"])


@router.get("/health")
async def health(sess: dict = Depends(deps.require_permission("zabbix:read"))):
    return {"status": "ok", "module": "zabbix"}
