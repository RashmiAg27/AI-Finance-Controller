from fastapi import APIRouter

from app.api.v1 import (
    agent, batches, cash, clients, exceptions, matches, settlements, transactions, workspace,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(clients.router)
api_router.include_router(batches.router)
api_router.include_router(workspace.router)
api_router.include_router(transactions.router)
api_router.include_router(matches.router)
api_router.include_router(exceptions.router)
api_router.include_router(settlements.router)
api_router.include_router(cash.router)
api_router.include_router(agent.router)
