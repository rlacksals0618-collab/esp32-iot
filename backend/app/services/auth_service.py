from dataclasses import asdict
from typing import Annotated

from fastapi import Depends

from ..dependencies import AuthGatewayDep
from ..schemas.auth import SignupIn, TokenOut


class AuthService:
    def __init__(self, auth: AuthGatewayDep):
        self.auth = auth

    def signup(self, data: SignupIn) -> TokenOut:
        """가입 후 바로 로그인한 토큰을 돌려준다."""
        self.auth.sign_up(data.email, data.password)
        return self.login(data.email, data.password)

    def login(self, email: str, password: str) -> TokenOut:
        return TokenOut.model_validate(asdict(self.auth.sign_in(email, password)))

    def refresh(self, refresh_token: str) -> TokenOut:
        return TokenOut.model_validate(asdict(self.auth.refresh(refresh_token)))


AuthServiceDep = Annotated[AuthService, Depends()]
