from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field

Password = Annotated[str, Field(min_length=8, max_length=72, examples=["password123"])]


class SignupIn(BaseModel):
    email: EmailStr
    password: Password


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=72)]


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1)]


class UserOut(BaseModel):
    id: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str = Field(description="access token이 만료되면 /api/auth/refresh로 새 토큰을 받을 때 쓴다")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="access token 유효 시간(초)")
    user: UserOut
