from fastapi import APIRouter, status

from ..dependencies import CurrentUser
from ..schemas.auth import LoginIn, RefreshIn, SignupIn, TokenOut, UserOut
from ..services.auth_service import AuthServiceDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(data: SignupIn, service: AuthServiceDep):
    """회원가입. 가입과 동시에 로그인된 토큰을 돌려준다."""
    return service.signup(data)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, service: AuthServiceDep):
    return service.login(data.email, data.password)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, service: AuthServiceDep):
    """만료된 access token 대신 새 토큰을 받는다."""
    return service.refresh(data.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
