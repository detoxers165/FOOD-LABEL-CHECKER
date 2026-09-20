from datetime import datetime
from typing import Any

from pymongo import DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


class ScanRepository:
    def __init__(self, database: AsyncDatabase):
        self.collection = database.scans

    async def create(self, document: dict[str, Any]) -> None:
        await self.collection.insert_one(document)

    async def find_owned(
        self,
        *,
        scan_id: str,
        user_id: Any,
    ) -> dict[str, Any] | None:
        return await self.collection.find_one(
            {
                "scan_id": scan_id,
                "user_id": user_id,
            }
        )

    async def update_owned(
        self,
        *,
        scan_id: str,
        user_id: Any,
        update: dict[str, Any],
    ) -> bool:
        result = await self.collection.update_one(
            {
                "scan_id": scan_id,
                "user_id": user_id,
            },
            update,
        )

        return result.matched_count == 1

    async def delete_owned(
        self,
        *,
        scan_id: str,
        user_id: Any,
    ) -> dict[str, Any] | None:
        return await self.collection.find_one_and_delete(
            {
                "scan_id": scan_id,
                "user_id": user_id,
            }
        )

    async def list_owned(
        self,
        *,
        user_id: Any,
        skip: int,
        limit: int,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {
            "user_id": user_id,
        }

        if status:
            query["status"] = status

        if from_date or to_date:
            query["created_at"] = {}

            if from_date:
                query["created_at"]["$gte"] = from_date

            if to_date:
                query["created_at"]["$lte"] = to_date

        total = await self.collection.count_documents(query)

        cursor = (
            self.collection
            .find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )

        return await cursor.to_list(length=limit), total
