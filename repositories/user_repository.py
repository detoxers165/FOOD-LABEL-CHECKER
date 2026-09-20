 from datetime import datetime, timezone
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    def __init__(self, database: AsyncDatabase):
        self.collection = database.users

    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"email": email})

    async def find_by_id(self, user_id: Any) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": user_id})

    async def create(
        self,
        *,
        email: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()

        document = {
            "email": email,
            "email_verified": True,
            "is_active": True,
            "display_name": None,
            "created_at": now,
            "updated_at": now,
            "last_login_at": now,
        }

        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def mark_login(
        self,
        user_id: Any,
        *,
        now: datetime | None = None,
    ) -> None:
        now = now or utc_now()

        await self.collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "email_verified": True,
                    "last_login_at": now,
                    "updated_at": now,
                }
            },
        )

    async def update_display_name(
        self,
        user_id: Any,
        display_name: str | None,
    ) -> dict[str, Any] | None:
        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {
                "$set": {
                    "display_name": display_name,
                    "updated_at": utc_now(),
                }
            },
            return_document=True,
        )

        return result
