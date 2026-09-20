from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


class MongoDatabase:
    def __init__(self, uri: str, database_name: str):
        self.uri = uri
        self.database_name = database_name
        self.client: AsyncMongoClient | None = None
        self.database: AsyncDatabase | None = None

    async def connect(self) -> None:
        self.client = AsyncMongoClient(
            self.uri,
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )

        await self.client.admin.command("ping")
        self.database = self.client[self.database_name]

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.close()

        self.client = None
        self.database = None

    async def ping(self) -> bool:
        if self.client is None:
            return False

        await self.client.admin.command("ping")
        return True

    def get_database(self) -> AsyncDatabase:
        if self.database is None:
            raise RuntimeError("MongoDB is not connected")

        return self.database


@asynccontextmanager
async def mongodb_lifespan(
    mongo: MongoDatabase,
) -> AsyncIterator[AsyncDatabase]:
    await mongo.connect()

    try:
        yield mongo.get_database()
    finally:
        await mongo.disconnect()
