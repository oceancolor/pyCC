"""
Agent 框架 v2
- LLM Agent 支持 CoT 推理过程展示
- 工蜂 LLM API 真实接入
- Skills 注册 + 调用
"""
import os
import sys
import json
import urllib.request
import random
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

# 路径兼容（server 目录运行时）
sys.path.insert(0, os.path.dirname(__file__))
from maze_env import (
    MazeEnvironment, SeasonRules, Observation, Action,
    Position, ACTIONS, DELTA, ALL_COLORS
)

# ── 工蜂 LLM API ──────────────────────────────────────────────
LLM_ENDPOINT = "https://copilot.code.woa.com/server/openclaw/copilot-gateway/v1/chat/completions"

def _gf_headers():
    device_id = (
        os.environ.get("GF_DEVICE_ID") or
        os.environ.get("MOLTBOT_CLIENT_UUID") or
        os.environ.get("GF_IDE_WORKSPACE_ID") or
        "arena-demo"
    )
    return {
        "OAUTH-TOKEN": os.environ.get("GF_TOKEN", ""),
        "X-Username": os.environ.get("GF_USERNAME", ""),
        "DEVICE-ID": device_id,
        "Content-Type": "application/json"
    }

def call_gongfeng_llm(messages: List[Dict], model: str = "auto", max_tokens: int = 400) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3
    }).encode()
    req = urllib.request.Request(
        LLM_ENDPOINT, data=payload,
        headers=_gf_headers(), method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return json.dumps({"action": "wait", "reasoning": f"LLM error: {e}"})


# ── Agent 配置 ────────────────────────────────────────────────
@dataclass
class AgentConfig:
    name: str
    agent_id: str = "agent_a"
    strategy: str = "rule_based"  # "rule_based" | "llm"
    skills: List[str] = field(default_factory=lambda: ["pathfinder", "memory_map"])
    system_prompt: str = "你是迷宫寻宝专家，用最少步数收集最多积分。"
    model: str = "auto"
    enable_cot: bool = True  # 是否记录 CoT 推理过程


# ── Skills 注册表 ─────────────────────────────────────────────
class SkillRegistry:
    """内置 Skills，返回给 Agent 的结构化分析结果"""
    
    @staticmethod
    def pathfinder(obs: Observation) -> Dict:
        """BFS 最短路径规划，找到最近的宝石/宝箱/出口"""
        grid = obs.map_snapshot
        H = len(grid)
        W = len(grid[0]) if H > 0 else 0
        start = obs.player_pos
        
        # BFS
        from collections import deque
        visited = {(start.row, start.col)}
        q = deque([(start.row, start.col, [])])
        targets = {}
        
        # 标记目标
        gem_cells  = {(p.row, p.col): f"gem_{c}" for c, p in obs.gem_positions.items()}
        chest_cell = (obs.chest_pos.row, obs.chest_pos.col) if obs.chest_pos else None
        exit_cell  = (obs.exit_pos.row, obs.exit_pos.col)  if obs.exit_pos  else None
        
        while q:
            r, c, path = q.popleft()
            cell = (r, c)
            
            if cell in gem_cells and gem_cells[cell] not in targets:
                targets[gem_cells[cell]] = path
            if chest_cell and cell == chest_cell and "chest" not in targets:
                targets["chest"] = path
            if exit_cell and cell == exit_cell and "exit" not in targets:
                targets["exit"] = path
            
            for action, (dr, dc) in DELTA.items():
                nr, nc = r + dr, c + dc
                if (0 <= nr < H and 0 <= nc < W and
                    (nr, nc) not in visited and
                    grid[nr][nc] not in ("#",)):
                    visited.add((nr, nc))
                    q.append((nr, nc, path + [action]))
        
        return {
            "nearest": sorted(targets.items(), key=lambda x: len(x[1]))[:3],
            "targets": {k: {"steps": len(v), "first_action": v[0] if v else None} 
                       for k, v in targets.items()}
        }
    
    @staticmethod
    def memory_map(obs: Observation) -> Dict:
        """分析当前局势"""
        gem_count = len(obs.gem_positions)
        has_chest = obs.chest_pos is not None
        collected = sum(obs.gems_collected.values())
        
        # 与出口的曼哈顿距离
        exit_dist = None
        if obs.exit_pos:
            exit_dist = (abs(obs.exit_pos.row - obs.player_pos.row) + 
                        abs(obs.exit_pos.col - obs.player_pos.col))
        
        # 体力评估
        stamina_pct = obs.stamina / 1000.0
        urgency = "低" if stamina_pct > 0.5 else ("中" if stamina_pct > 0.2 else "高")
        
        return {
            "gems_remaining": gem_count,
            "gems_collected": collected,
            "has_chest": has_chest,
            "exit_distance_approx": exit_dist,
            "stamina_pct": round(stamina_pct, 2),
            "urgency": urgency,
            "current_score": obs.score
        }
    
    @staticmethod
    def opponent_tracker(obs: Observation) -> Dict:
        """追踪对手位置"""
        if not obs.opponent_pos:
            return {"opponent_visible": False}
        
        dist = (abs(obs.opponent_pos.row - obs.player_pos.row) +
                abs(obs.opponent_pos.col - obs.player_pos.col))
        
        # 谁离宝箱更近
        chest_threat = None
        if obs.chest_pos:
            my_dist = (abs(obs.chest_pos.row - obs.player_pos.row) +
                      abs(obs.chest_pos.col - obs.player_pos.col))
            opp_dist = (abs(obs.chest_pos.row - obs.opponent_pos.row) +
                       abs(obs.chest_pos.col - obs.opponent_pos.col))
            chest_threat = "我更近" if my_dist < opp_dist else "对手更近"
        
        return {
            "opponent_visible": True,
            "opponent_pos": [obs.opponent_pos.row, obs.opponent_pos.col],
            "distance": dist,
            "chest_race": chest_threat
        }
    
    REGISTRY = {
        "pathfinder": pathfinder.__func__,
        "memory_map": memory_map.__func__,
        "opponent_tracker": opponent_tracker.__func__
    }
    
    @classmethod
    def run(cls, skill_name: str, obs: Observation) -> Dict:
        fn = cls.REGISTRY.get(skill_name)
        if fn:
            try:
                return fn(obs)
            except Exception as e:
                return {"error": str(e)}
        return {"error": f"skill {skill_name} not found"}


# ── 规则型 Agent ──────────────────────────────────────────────
class RuleBasedAgent:
    """纯规则 Agent（不调用 LLM）"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
    
    def act(self, obs: Observation) -> Action:
        pf = SkillRegistry.run("pathfinder", obs)
        nearest = pf.get("nearest", [])
        if nearest:
            target, path = nearest[0]
            if path:
                return path[0]
        return random.choice(ACTIONS)
    
    def reset(self): pass


# ── LLM Agent（支持 CoT）─────────────────────────────────────
class LLMAgent:
    """LLM 推理 Agent"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.conversation_history: List[Dict] = []
        self._init_system_prompt()
    
    def _init_system_prompt(self):
        self.conversation_history = [{
            "role": "system",
            "content": (
                self.config.system_prompt + "\n\n"
                "## 输出格式\n"
                "你必须以 JSON 格式输出，包含两个字段：\n"
                "1. `thinking`: 你的推理过程（CoT，1-3句话）\n"
                "2. `action`: 最终行动，必须是 up/down/left/right 之一\n\n"
                "示例：{\"thinking\": \"宝箱在右下方，BFS路径显示需先向右走\", \"action\": \"right\"}\n"
                "不要输出任何其他内容。"
            )
        }]
    
    def act(self, obs: Observation) -> Tuple[Action, str]:
        """返回 (action, thinking) 元组"""
        # 运行所有 Skills
        skill_results = {
            skill: SkillRegistry.run(skill, obs)
            for skill in self.config.skills
        }
        
        # 构建 prompt
        map_str = "\n".join(" ".join(row) for row in obs.map_snapshot)
        prompt = f"""## 当前状态
- 位置: {obs.player_pos} | 体力: {obs.stamina} | 分数: {obs.score}
- 已收集宝石: {obs.gems_collected}
- 回合: {obs.turn_number}
- 赛季规则: {obs.rules_hint}

## 地图
```
{map_str}
```
图例: A=你 B=对手 R/B/G/Y/P=宝石(颜色) C=宝箱 E=出口 #=墙

## Skills 分析
{json.dumps(skill_results, ensure_ascii=False, indent=2)}

## 决策
下一步走哪？输出 JSON：{{"thinking": "推理过程", "action": "方向"}}"""

        self.conversation_history.append({"role": "user", "content": prompt})
        
        raw = self._call_llm(self.conversation_history)
        action, thinking = self._parse_response(raw)
        
        self.conversation_history.append({"role": "assistant", "content": raw})
        
        # 保持对话历史不超过 10 轮
        if len(self.conversation_history) > 21:
            self.conversation_history = (
                self.conversation_history[:1] +
                self.conversation_history[-20:]
            )
        
        return action, thinking
    
    def _parse_response(self, raw: str) -> Tuple[Action, str]:
        """解析 LLM JSON 响应，提取 action 和 thinking"""
        try:
            # 找 JSON 块
            s = raw.find("{")
            e = raw.rfind("}") + 1
            if s >= 0 and e > s:
                data = json.loads(raw[s:e])
                action = data.get("action", "").strip().lower()
                thinking = data.get("thinking", "")
                if action in ACTIONS:
                    return action, thinking
        except Exception:
            pass
        
        # 兜底：从文本中找方向词
        for a in ACTIONS:
            if a in raw.lower():
                return a, raw[:100]
        
        return random.choice(ACTIONS), f"解析失败，随机行动: {raw[:80]}"
    
    def _call_llm(self, messages: List[Dict]) -> str:
        return call_gongfeng_llm(messages, model=self.config.model, max_tokens=300)
    
    def reset(self):
        self._init_system_prompt()


def make_agent(config: AgentConfig):
    if config.strategy == "llm":
        return LLMAgent(config)
    return RuleBasedAgent(config)
