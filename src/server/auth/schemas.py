# -*- coding: utf-8 -*-
"""
认证相关 Pydantic 模型（模板版）

公开接口：
- `UserProfile`、`UserCreate`、`UserUpdate`、`UserLogin`、`TokenResponse`
- `VerificationCodeRequest`、`UserRegisterWithCode`
- `EmailChangeCodeRequest`、`EmailChangeConfirm`
- `PasswordResetLinkRequest`、`PasswordResetWithToken`
- `PasswordChangeConfirm`
"""

from typing import Optional
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRole(str, Enum):
    """
    用户角色枚举
    """

    USER = "user"
    ADMIN = "admin"


class UserStatus(str, Enum):
    """
    用户状态枚举
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


class UserProfile(BaseModel):
    id: int
    username: str
    email: EmailStr
    name: Optional[str] = Field(default=None)
    role: UserRole
    status: UserStatus
    two_factor_enabled: bool = False
    two_factor_confirmed_at: Optional[datetime] = None
    effective_scopes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    turnstile_token: str | None = Field(default=None, min_length=1, max_length=2048)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    name: Optional[str] = Field(default=None, max_length=100)


class UserLogin(BaseModel):
    """登录标识支持用户名或邮箱，字段名保持兼容。"""

    username: str
    password: str
    turnstile_token: str | None = Field(default=None, min_length=1, max_length=2048)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class LoginChallengeResponse(BaseModel):
    requires_2fa: bool = True
    challenge_token: str
    challenge_type: str = "totp"


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(..., min_length=6, max_length=32)


class TwoFactorSetupStartResponse(BaseModel):
    secret: str
    secret_masked: str
    otpauth_url: str
    setup_token: str


class TwoFactorSetupConfirmRequest(BaseModel):
    setup_token: str
    code: str = Field(..., min_length=6, max_length=32)


class TwoFactorDisableRequest(BaseModel):
    password: str
    code: str = Field(..., min_length=6, max_length=32)


class TwoFactorBackupCodesRegenerateRequest(BaseModel):
    password: str
    code: str = Field(..., min_length=6, max_length=32)


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]
    message: str = "backup codes 已生成"


class MessageResponse(BaseModel):
    message: str


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


class VerificationCodeRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = Field(default=None, min_length=1, max_length=2048)


class UserRegisterWithCode(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    code: str = Field(..., min_length=6, max_length=6)
    turnstile_token: str | None = Field(default=None, min_length=1, max_length=2048)


class PasswordResetLinkRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = Field(default=None, min_length=1, max_length=2048)


class PasswordResetWithToken(BaseModel):
    token: str = Field(..., min_length=64, max_length=64)
    new_password: str = Field(..., min_length=8)


class EmailChangeCodeRequest(BaseModel):
    email: EmailStr


class EmailChangeConfirm(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class PasswordChangeConfirm(BaseModel):
    token: str = Field(..., min_length=64, max_length=64)
    new_password: str = Field(..., min_length=8)
