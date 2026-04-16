# 原始 TS: utils/hash.ts
"""内容哈希工具"""
import hashlib


def sha256(content: str) -> str:
    """返回字符串的 SHA-256 十六进制摘要（64 位）"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def md5(content: str) -> str:
    """返回字符串的 MD5 十六进制摘要（32 位）"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def content_hash(content: str) -> str:
    """返回内容的短哈希（SHA-256 前 8 位），适合用作文件名或标识符"""
    return sha256(content)[:8]
