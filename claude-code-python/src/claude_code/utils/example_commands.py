# 原始 TS: utils/exampleCommands.ts
"""示例命令（新用户引导）"""
from typing import List

EXAMPLE_COMMANDS: List[dict] = [
    {"label": "解释代码",      "prompt": "解释一下这个项目的结构"},
    {"label": "修复 Bug",      "prompt": "找出并修复 main.py 中的 bug"},
    {"label": "写测试",        "prompt": "为 utils.py 写单元测试"},
    {"label": "代码审查",      "prompt": "审查最近的改动，给出改进建议"},
    {"label": "提交变更",      "prompt": "把改动整理成一个 git commit"},
    {"label": "创建文件",      "prompt": "创建一个 README.md 文件"},
    {"label": "搜索代码",      "prompt": "找出所有调用 login 函数的地方"},
    {"label": "运行测试",      "prompt": "运行测试并修复失败的用例"},
]


def get_example_commands(n: int = 4) -> List[dict]:
    return EXAMPLE_COMMANDS[:n]


def format_examples() -> str:
    lines = ["示例："]
    for cmd in get_example_commands():
        lines.append(f'  claude "{cmd["prompt"]}"')
    return "\n".join(lines)
