from typing import Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings
from services.auth_service import decode_jwt
from repositories.user_repository import UserRepository
from repositories.session_repository import SessionRepository
import jwt
from errors import AppError, ErrorCode, public_error

security = HTTPBearer(auto_error=False)

async def optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    if not credentials:
        return None

    token = credentials.credentials
    settings = get_settings()
    db = request.app.state.db

    try:
        payload = decode_jwt(token, settings.jwt_secret, settings.jwt_algorithm)
        jti = payload.get("jti")
        user_id = payload.get("sub")
        
        if not jti or not user_id:
            return None

        session_repo = SessionRepository(db)
        session = await session_repo.find_active(jti=jti)
        
        if not session:
            return None

        from bson import ObjectId
        user_repo = UserRepository(db)
        user = await user_repo.find_by_id(ObjectId(user_id))
        
        return user
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWTError:
        return None
    except Exception:
        return None

async def get_current_user(
    user: Optional[dict] = Depends(optional_current_user)
) -> dict:
    if not user:
        raise public_error(
            code=ErrorCode.UNAUTHORIZED,
            message="Not authenticated",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    return user
