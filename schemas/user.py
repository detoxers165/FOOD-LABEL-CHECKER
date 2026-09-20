from pydantic import BaseModel, Field


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(
        default=None,
        max_length=120,
    )
