from datetime import datetime, timezone
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionRepository:
    def __init__(self, database: AsyncDatabase):
        self.collection = database.sessions

    async def create(
        self,
        *,
        jti: str,
        user_id: Any,
        expires_at: datetime,
    ) -> dict[str, Any]:
        document = {
            "jti": jti,
            "user_id": user_id,
            "created_at": utc_now(),
            "expires_at": expires_at,
            "revoked_at": None,
        }

        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def find_active(
        self,
        *,
        jti: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = now or utc_now()

        return await self.collection.find_one(
            {
                "jti": jti,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            }
        )

    async def revoke(self, jti: str) -> None:
        await self.collection.update_one(
            {
                "jti": jti,
                "revoked_at": None,
            },
            {
                "$set": {
                    "revoked_at": utc_now(),
                }
            },
        )
