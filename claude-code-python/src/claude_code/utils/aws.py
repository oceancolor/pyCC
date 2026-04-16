# 原始 TS: utils/aws.ts / utils/awsAuthStatusManager.ts
"""AWS 凭据工具（Bedrock 调用用）"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AWSCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None
    region: str = "us-east-1"


def get_aws_credentials() -> Optional[AWSCredentials]:
    """从环境变量读取 AWS 凭据"""
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not key or not secret:
        return None
    return AWSCredentials(
        access_key_id=key,
        secret_access_key=secret,
        session_token=os.environ.get("AWS_SESSION_TOKEN"),
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def is_bedrock_enabled() -> bool:
    """检查是否配置了 Bedrock 访问"""
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_BEDROCK_ENABLED"))


def get_bedrock_endpoint(region: str = "us-east-1") -> str:
    return f"https://bedrock-runtime.{region}.amazonaws.com"


class AWSAuthStatusManager:
    """管理 AWS 认证状态"""

    def __init__(self) -> None:
        self._creds: Optional[AWSCredentials] = None

    def refresh(self) -> bool:
        self._creds = get_aws_credentials()
        return self._creds is not None

    @property
    def is_authenticated(self) -> bool:
        return self._creds is not None

    @property
    def credentials(self) -> Optional[AWSCredentials]:
        return self._creds
