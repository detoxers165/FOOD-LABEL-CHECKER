from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


class ReportRepository:
    def __init__(self, database: AsyncDatabase):
        self.collection = database.reports

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
