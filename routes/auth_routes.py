import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, status
from bson import ObjectId

from config import get_settings, Settings
from schemas.auth import SendOtpRequest, VerifyOtpRequest, VerifyOtpResponse, UserResponse, UpdateProfileRequest
from services.auth_service import generate_otp, hash_otp, verify_otp, create_jwt, serialize_user
from services.email_service import send_otp_email
from repositories.otp_repository import OtpRepository
from repositories.user_repository import UserRepository
from repositories.session_repository import SessionRepository
from middleware.auth_middleware import get_current_user
from response import success_response, error_response
from errors import public_error, ErrorCode

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])

@auth_router.post("/send-otp")
async def send_otp(
    request: Request,
    payload: SendOtpRequest,
    settings: Settings = Depends(get_settings)
):
    db = request.app.state.db
    otp_repo = OtpRepository(db)
    
    email = payload.email.lower()
    
    # Rate limiting
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    sends_last_hour = await otp_repo.count_since(email, one_hour_ago)
    
    if sends_last_hour >= settings.otp_max_sends_per_hour:
        raise public_error(
            ErrorCode.RATE_LIMITED,
            "Too many OTP requests. Please try again later.",
            status_code=429
        )
        
    latest_otp = await otp_repo.latest_active(email)
    if latest_otp:
        cooldown_end = latest_otp["created_at"] + timedelta(seconds=settings.otp_resend_cooldown_seconds)
        if now < cooldown_end:
            raise public_error(
                ErrorCode.RATE_LIMITED,
                f"Please wait before requesting another OTP.",
                status_code=429
            )
            
    await otp_repo.invalidate_previous(email)
    
    otp = generate_otp()
    otp_hash = hash_otp(otp, settings.otp_hmac_secret)
    
    expires_at = now + timedelta(seconds=settings.otp_expiry_seconds)
    purge_at = expires_at + timedelta(days=1)
    
    await otp_repo.create(
        email=email,
        otp_hash=otp_hash,
        expires_at=expires_at,
        purge_at=purge_at,
        max_attempts=settings.otp_max_attempts
    )
    
    try:
        send_otp_email(email, otp, settings)
    except Exception:
        raise public_error(
            ErrorCode.OTP_SEND_FAILED,
            "Failed to send OTP email.",
            status_code=500
        )
        
    return success_response({"message": "OTP sent successfully"})

@auth_router.post("/verify-otp")
async def verify_otp_endpoint(
    request: Request,
    payload: VerifyOtpRequest,
    settings: Settings = Depends(get_settings)
):
    db = request.app.state.db
    otp_repo = OtpRepository(db)
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)
    
    email = payload.email.lower()
    latest_otp = await otp_repo.latest_active(email)
    
    if not latest_otp:
        raise public_error(
            ErrorCode.INVALID_OTP,
            "No active OTP found. Please request a new one.",
            status_code=400
        )
        
    now = datetime.now(timezone.utc)
    if now > latest_otp["expires_at"]:
        raise public_error(
            ErrorCode.OTP_EXPIRED,
            "OTP has expired.",
            status_code=400
        )
        
    if latest_otp["attempts"] >= latest_otp["max_attempts"]:
        raise public_error(
            ErrorCode.OTP_TOO_MANY_ATTEMPTS,
            "Too many failed attempts. Please request a new OTP.",
            status_code=400
        )
        
    await otp_repo.increment_attempts(latest_otp["_id"])
    
    is_valid = verify_otp(payload.otp, latest_otp["otp_hash"], settings.otp_hmac_secret)
    if not is_valid:
        raise public_error(
            ErrorCode.INVALID_OTP,
            "Invalid OTP.",
            status_code=400
        )
        
    await otp_repo.mark_used(latest_otp["_id"])
    
    user = await user_repo.find_by_email(email)
    if not user:
        user = await user_repo.create(email=email, now=now)
    else:
        await user_repo.mark_login(user["_id"], now=now)
        user = await user_repo.find_by_id(user["_id"])
        
    jti = str(uuid.uuid4())
    jwt_exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    
    access_token = create_jwt(
        user_id=str(user["_id"]),
        jti=jti,
        exp=jwt_exp,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    
    await session_repo.create(
        jti=jti,
        user_id=user["_id"],
        expires_at=jwt_exp
    )
    
    response_data = VerifyOtpResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        user=serialize_user(user)
    )
    
    return success_response(response_data.model_dump())

@auth_router.post("/logout")
async def logout(
    request: Request,
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    from fastapi.security import HTTPBearer
    security = HTTPBearer(auto_error=False)
    auth = await security(request)
    
    if auth:
        try:
            from services.auth_service import decode_jwt
            payload = decode_jwt(auth.credentials, settings.jwt_secret, settings.jwt_algorithm)
            jti = payload.get("jti")
            if jti:
                db = request.app.state.db
                session_repo = SessionRepository(db)
                await session_repo.revoke(jti)
        except Exception:
            pass
            
    return success_response({"message": "Logged out successfully"})

@auth_router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return success_response(serialize_user(user).model_dump())

@auth_router.patch("/profile")
async def update_profile(
    request: Request,
    payload: UpdateProfileRequest,
    user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    user_repo = UserRepository(db)
    updated = await user_repo.update_display_name(user["_id"], payload.display_name.strip())
    if not updated:
        return success_response(serialize_user(user).model_dump())
    return success_response(serialize_user(updated).model_dump())

