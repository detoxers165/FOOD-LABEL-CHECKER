from pydantic import BaseModel, EmailStr, Field


class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    is_active: bool
    display_name: str | None = None
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class VerifyOtpResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse
