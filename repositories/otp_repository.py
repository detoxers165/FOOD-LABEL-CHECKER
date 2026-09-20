from datetime import datetime, timezone
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OtpRepository:
    def __init__(self, database: AsyncDatabase):
        self.collection = database.otp_requests

    async def invalidate_previous(self, email: str) -> None:
        await self.collection.update_many(
            {
                "email": email,
                "purpose": "login",
                "used": False,
            },
            {
                "$set": {
                    "used": True,
                }
            },
        )

    async def create(
        self,
        *,
        email: str,
        otp_hash: str,
        expires_at: datetime,
        purge_at: datetime,
        max_attempts: int,
    ) -> dict[str, Any]:
        document = {
            "email": email,
            "purpose": "login",
            "otp_hash": otp_hash,
            "attempts": 0,
            "max_attempts": max_attempts,
            "used": False,
            "created_at": utc_now(),
            "expires_at": expires_at,
            "purge_at": purge_at,
        }

        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def latest_active(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        return await self.collection.find_one(
            {
                "email": email,
                "purpose": "login",
                "used": False,
            },
            sort=[("created_at", -1)],
        )

    async def count_since(
        self,
        email: str,
        since: datetime,
    ) -> int:
        return await self.collection.count_documents(
            {
                "email": email,
                "purpose": "login",
                "created_at": {"$gte": since},
            }
        )

    async def increment_attempts(
        self,
        otp_id: Any,
    ) -> None:
        await self.collection.update_one(
            {"_id": otp_id},
            {"$inc": {"attempts": 1}},
        )

    async def mark_used(self, otp_id: Any) -> None:
        await self.collection.update_one(
            {"_id": otp_id},
            {"$set": {"used": True}},
        )
