# 原始 TS: utils/crypto.ts
"""加密工具：随机 ID、安全 token 生成"""
import hashlib
import hmac
import os
import secrets
import string


def random_id(length: int = 16) -> str:
    """生成随机 URL-safe ID"""
    return secrets.token_urlsafe(length)[:length]


def secure_token(length: int = 32) -> str:
    """生成安全 token（hex）"""
    return secrets.token_hex(length // 2)


def hmac_sha256(key: str, message: str) -> str:
    """计算 HMAC-SHA256"""
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def random_alphanumeric(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
