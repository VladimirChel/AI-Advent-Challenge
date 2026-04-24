from fastapi import APIRouter, Depends, HTTPException

from config import AUTH_ENABLED
from auth.dependencies import get_current_user
from auth.schemas import LoginRequest, PublicUser, RegisterRequest, TokenResponse
from auth.service import login_user, register_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest) -> TokenResponse:
    if not AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="auth_disabled")
    return register_user(email=payload.email, password=payload.password)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if not AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="auth_disabled")
    return login_user(email=payload.email, password=payload.password)


@router.get("/me", response_model=PublicUser)
def me(current_user: PublicUser = Depends(get_current_user)) -> PublicUser:
    return current_user
