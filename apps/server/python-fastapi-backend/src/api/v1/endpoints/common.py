"""公共路由"""

from fastapi import APIRouter

from src.algorithms import list_algorithms

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@router.get("/algorithms")
async def list_all_algorithms() -> list[dict]:
    """列出所有已注册的算法"""
    return list_algorithms()
