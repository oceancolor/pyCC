"""
Agent Arena API Server v2
- 完整 v2 规则（SeasonRules）
- 关卡编辑器 API
- CoT 日志
- LLM + 规则混排
"""
import os
import sys
import uuid
import time
from typing import Optional, Dict, List, Any
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agents'))

from maze_env import SeasonRules, MazeEnvironment
from agent_framework import AgentConfig, make_agent, LLMAgent
from match_engine import MatchEngine, TournamentManager, MatchResult

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ── 全局状态 ─────────────────────────────────────────────────
agents_db: Dict[str, dict] = {}
matches_db: Dict[str, dict] = {}
tournament = TournamentManager()
current_season: SeasonRules = SeasonRules(season_id="S1")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Agent Arena API v2 启动...")
    print("📖 API: http://localhost:8888/docs")
    print("🎮 Demo: http://localhost:8888/demo")
    yield

app = FastAPI(title="Agent Arena API", version="2.0.0", lifespan=lifespan)

# ── Pydantic 模型 ────────────────────────────────────────────

class AgentRegisterReq(BaseModel):
    name: str
    strategy: str = "rule_based"
    skills: List[str] = ["pathfinder", "memory_map"]
    system_prompt: str = "你是迷宫寻宝专家，高效决策。"
    model: str = "auto"
    enable_cot: bool = True

class MatchStartReq(BaseModel):
    agent_a_id: str
    agent_b_id: str
    maze_seed: Optional[int] = None
    max_stamina: Optional[int] = None   # None=用赛季默认值

class SeasonRulesReq(BaseModel):
    season_id: str = "S1"
    map_width: int = 13
    map_height: int = 13
    map_seed: Optional[int] = None
    stamina: int = 1000
    gem_score: Dict[str, int] = {"R":1,"B":1,"G":1,"Y":1,"P":1}
    gem_set_bonus: int = 0
    gem_respawn: str = "set"
    chest_rewards: List[int] = [0, 3, 5, 7, 9]
    chest_probs: List[float] = [0.2, 0.2, 0.2, 0.2, 0.2]
    exit_bonus: int = 20

# ── 路由 ─────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Agent Arena", "version": "2.0.0", "status": "running",
            "season": current_season.season_id}

# --- Season / Level Editor ---

@app.get("/season")
def get_season():
    """获取当前赛季规则"""
    r = current_season
    return {
        "season_id": r.season_id,
        "map_size": [r.map_width, r.map_height],
        "map_seed": r.map_seed,
        "stamina": r.stamina,
        "gem_score": r.gem_score,
        "gem_set_bonus": r.gem_set_bonus,
        "gem_respawn": r.gem_respawn,
        "chest_rewards": r.chest_rewards,
        "chest_probs": r.chest_probs,
        "exit_bonus": r.exit_bonus,
    }

@app.post("/season/update")
def update_season(req: SeasonRulesReq):
    """关卡编辑器：更新赛季规则"""
    global current_season
    current_season = SeasonRules(
        season_id=req.season_id,
        map_width=req.map_width,
        map_height=req.map_height,
        map_seed=req.map_seed,
        stamina=req.stamina,
        gem_score=req.gem_score,
        gem_set_bonus=req.gem_set_bonus,
        gem_respawn=req.gem_respawn,
        chest_rewards=req.chest_rewards,
        chest_probs=req.chest_probs,
        exit_bonus=req.exit_bonus
    )
    return {"ok": True, "season_id": current_season.season_id}

@app.get("/season/preview")
def preview_map():
    """预览当前赛季地图"""
    import copy
    rules = copy.deepcopy(current_season)
    env = MazeEnvironment(rules=rules)
    snapshot = [row[:] for row in env.grid]
    for pos, obj in env.objects.items():
        if obj.kind == "gem":
            snapshot[pos.row][pos.col] = obj.color
        elif obj.kind == "chest":
            snapshot[pos.row][pos.col] = "C"
    if env.exit_pos:
        snapshot[env.exit_pos.row][env.exit_pos.col] = "E"
    gem_pos = {obj.color: [pos.row, pos.col] for pos, obj in env.objects.items() if obj.kind == "gem"}
    chest_pos_list = [[pos.row, pos.col] for pos, obj in env.objects.items() if obj.kind == "chest"]
    return {
        "seed": env.rules.map_seed,
        "width": env.width,
        "height": env.height,
        "map": snapshot,
        "gem_positions": gem_pos,
        "chest_pos": chest_pos_list[0] if chest_pos_list else None,
        "exit_pos": [env.exit_pos.row, env.exit_pos.col] if env.exit_pos else None
    }

# --- Agents ---

@app.post("/agents/register")
def register_agent(req: AgentRegisterReq):
    agent_id = "agent_" + uuid.uuid4().hex[:8]
    agents_db[agent_id] = {
        "id": agent_id,
        "name": req.name,
        "strategy": req.strategy,
        "skills": req.skills,
        "system_prompt": req.system_prompt,
        "model": req.model,
        "enable_cot": req.enable_cot,
        "registered_at": time.time()
    }
    tournament.register(AgentConfig(
        name=req.name, agent_id=agent_id,
        strategy=req.strategy, skills=req.skills,
        system_prompt=req.system_prompt, model=req.model
    ))
    return {"agent_id": agent_id, "name": req.name}

@app.get("/agents")
def list_agents():
    agents = list(agents_db.values())
    return {"agents": agents, "total": len(agents)}

@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    if agent_id not in agents_db:
        raise HTTPException(404, "agent not found")
    return agents_db[agent_id]

# --- Matches ---

@app.post("/matches/start")
def start_match(req: MatchStartReq):
    if req.agent_a_id not in agents_db:
        raise HTTPException(404, f"agent_a {req.agent_a_id} not found")
    if req.agent_b_id not in agents_db:
        raise HTTPException(404, f"agent_b {req.agent_b_id} not found")
    
    import copy
    rules = copy.deepcopy(current_season)
    if req.maze_seed is not None:
        rules.map_seed = req.maze_seed
    if req.max_stamina is not None:
        rules.stamina = req.max_stamina
    
    da, db = agents_db[req.agent_a_id], agents_db[req.agent_b_id]
    config_a = AgentConfig(
        name=da["name"], agent_id=req.agent_a_id,
        strategy=da["strategy"], skills=da.get("skills", []),
        system_prompt=da.get("system_prompt", ""),
        model=da.get("model", "auto"),
        enable_cot=da.get("enable_cot", True)
    )
    config_b = AgentConfig(
        name=db["name"], agent_id=req.agent_b_id,
        strategy=db["strategy"], skills=db.get("skills", []),
        system_prompt=db.get("system_prompt", ""),
        model=db.get("model", "auto"),
        enable_cot=db.get("enable_cot", True)
    )
    
    engine = MatchEngine(rules=rules, verbose=False)
    result = engine.run_match(config_a, config_b)
    tournament.record_match(result)
    
    d = result.to_dict()
    matches_db[result.match_id] = d
    return d

@app.get("/matches")
def list_matches():
    matches = sorted(matches_db.values(), key=lambda x: -x["timestamp"])
    return {"matches": matches[:20], "total": len(matches)}

@app.get("/matches/{match_id}")
def get_match(match_id: str):
    if match_id not in matches_db:
        raise HTTPException(404, "match not found")
    return matches_db[match_id]

@app.get("/matches/{match_id}/cot")
def get_match_cot(match_id: str):
    """获取对战完整 CoT 推理日志"""
    if match_id not in matches_db:
        raise HTTPException(404, "match not found")
    return {"match_id": match_id, "cot_log": matches_db[match_id].get("cot_log", [])}

# --- Leaderboard ---

@app.get("/leaderboard")
def leaderboard():
    return {"leaderboard": tournament.leaderboard(), "season": current_season.season_id}

# --- Demo Frontend ---

@app.get("/demo", response_class=HTMLResponse)
def demo_page():
    html_path = os.path.join(os.path.dirname(__file__), "../frontend/index.html")
    with open(html_path) as f:
        return HTMLResponse(f.read())

@app.get("/replay", response_class=HTMLResponse)
def replay_page():
    html_path = os.path.join(os.path.dirname(__file__), "../frontend/replay.html")
    with open(html_path) as f:
        return HTMLResponse(f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
