from fastapi import APIRouter

from app.api import asistente, clientes, dispositivos, pedidos, reclamos, sistema, tiempo_real

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(sistema.router)
api_router.include_router(clientes.router)
api_router.include_router(pedidos.router)
api_router.include_router(reclamos.router)
api_router.include_router(tiempo_real.router)
api_router.include_router(dispositivos.router)
api_router.include_router(asistente.router)
