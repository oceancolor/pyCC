# 原始 TS: commands/login/
"""登录命令：通过 OAuth 或 API key 认证"""
import os
from typing import Optional


def login_command(api_key: Optional[str] = None) -> bool:
    """
    认证到 Anthropic。
    - 如果传入 api_key，直接写入配置
    - 否则引导用户通过 OAuth 流程（TODO）
    """
    if api_key:
        # 写入环境变量或配置文件
        config_path = os.path.expanduser("~/.claude/config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        import json
        config: dict = {}
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
        config["api_key"] = api_key
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print("✅ API key 已保存")
        return True
    else:
        # TODO: OAuth flow
        print("请设置环境变量 ANTHROPIC_API_KEY 或运行 `claude login --api-key <key>`")
        return False


def logout_command() -> None:
    """清除认证信息"""
    config_path = os.path.expanduser("~/.claude/config.json")
    if os.path.exists(config_path):
        import json
        with open(config_path) as f:
            config = json.load(f)
        config.pop("api_key", None)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    print("已登出")
