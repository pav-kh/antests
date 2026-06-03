from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    access_code: str


class LoginRequest(BaseModel):
    login: str
    password: str


class UserOut(BaseModel):
    id: str
    login: str
