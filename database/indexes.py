from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def ensure_indexes(database: AsyncDatabase) -> None:
    await database.users.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="users_email_unique",
    )

    await database.otp_requests.create_index(
        [("email", ASCENDING), ("created_at", DESCENDING)],
        name="otp_email_created_at",
    )

    await database.otp_requests.create_index(
        [("purge_at", ASCENDING)],
        expireAfterSeconds=0,
        name="otp_purge_at_ttl",
    )

    await database.sessions.create_index(
        [("jti", ASCENDING)],
        unique=True,
        name="sessions_jti_unique",
    )

    await database.sessions.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="sessions_expires_at_ttl",
    )

    await database.scans.create_index(
        [("scan_id", ASCENDING)],
        unique=True,
        name="scans_scan_id_unique",
    )

    await database.scans.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="scans_user_created_at",
    )

    await database.scans.create_index(
        [
            ("user_id", ASCENDING),
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="scans_user_status_created_at",
    )

    await database.reports.create_index(
        [("scan_id", ASCENDING)],
        unique=True,
        name="reports_scan_id_unique",
    )

    await database.reports.create_index(
        [("user_id", ASCENDING)],
        name="reports_user",
    )
