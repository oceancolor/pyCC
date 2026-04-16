# 原始 TS: utils/caCerts.ts / utils/caCertsConfig.ts
"""CA 证书配置（自定义 SSL 证书支持）"""
from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Optional


def get_ca_bundle_path() -> Optional[str]:
    """获取自定义 CA bundle 路径（来自环境变量或默认位置）"""
    for env_var in ("CLAUDE_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        val = os.environ.get(env_var)
        if val and Path(val).exists():
            return val
    return None


def create_ssl_context(ca_bundle: Optional[str] = None) -> ssl.SSLContext:
    """创建 SSL context，可选自定义 CA bundle"""
    ctx = ssl.create_default_context()
    bundle = ca_bundle or get_ca_bundle_path()
    if bundle:
        ctx.load_verify_locations(cafile=bundle)
    return ctx


def is_custom_ca_configured() -> bool:
    return get_ca_bundle_path() is not None
