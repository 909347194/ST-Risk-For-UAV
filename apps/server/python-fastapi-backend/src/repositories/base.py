"""Repository 基类 — 定义通用 CRUD 接口"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
ID = TypeVar("ID")


class BaseRepository(Generic[T, ID]):
    """
    通用仓储接口。

    所有具体 Repository 继承此类，实现内存 / 数据库版本。
    当前提供 InMemory 默认实现。
    """

    def save(self, entity: T) -> T:
        raise NotImplementedError

    def find_by_id(self, entity_id: ID) -> T | None:
        raise NotImplementedError

    def find_all(self) -> list[T]:
        raise NotImplementedError

    def delete(self, entity_id: ID) -> bool:
        raise NotImplementedError

    def exists(self, entity_id: ID) -> bool:
        raise NotImplementedError


class InMemoryRepository(BaseRepository[T, ID]):
    """基于 dict 的内存仓储，通用 CRUD"""

    def __init__(self) -> None:
        self._store: dict[ID, T] = {}

    def save(self, entity: T) -> T:
        entity_id = self._extract_id(entity)
        self._store[entity_id] = entity
        return entity

    def find_by_id(self, entity_id: ID) -> T | None:
        return self._store.get(entity_id)

    def find_all(self) -> list[T]:
        return list(self._store.values())

    def delete(self, entity_id: ID) -> bool:
        if entity_id in self._store:
            del self._store[entity_id]
            return True
        return False

    def exists(self, entity_id: ID) -> bool:
        return entity_id in self._store

    def count(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()

    def _extract_id(self, entity: T) -> ID:
        """子类覆写，从实体中提取 ID"""
        raise NotImplementedError
