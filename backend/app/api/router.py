from fastapi import APIRouter

from app.api import clientes, pedidos, reclamos, sistema

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(sistema.router)
api_router.include_router(clientes.router)
api_router.include_router(pedidos.router)
api_router.include_router(reclamos.router)
