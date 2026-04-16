"""
对战引擎 v2
- 完整 v2 规则支持（体力值、宝石颜色、宝箱重生、出口加分）
- LLM CoT 记录
- 赛季 Elo 积分
- 关卡编辑器支持（通过 SeasonRules 传入）
"""
import uuid
import math
import time
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from maze_env import MazeEnvironment, SeasonRules, Observation
from agent_framework import AgentConfig, LLMAgent, RuleBasedAgent, make_agent

HUMAN_EFFICIENCY_BASELINE = 80  # 人类平均步数基准

@dataclass
class TurnRecord:
    turn: int
    player_id: str
    action: str
    pos_row: int
    pos_col: int
    score: int
    stamina: int
    reward: float
    thinking: str = ""     # LLM CoT 内容

@dataclass
class MatchResult:
    match_id: str
    agent_a: AgentConfig
    agent_b: AgentConfig
    agent_a_score: int
    agent_b_score: int
    agent_a_actions: int
    agent_b_actions: int
    agent_a_stamina_left: int
    agent_b_stamina_left: int
    agent_a_exit: bool
    agent_b_exit: bool
    efficiency_a: float
    efficiency_b: float
    winner: Optional[str]   # "agent_a" | "agent_b" | None (tie)
    winner_name: str
    turns: int
    timeline: List[TurnRecord] = field(default_factory=list)
    cot_log: List[Dict] = field(default_factory=list)
    map_seed: Optional[int] = None
    rules: Optional[Dict] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "match_id": self.match_id,
            "agent_a": {"name": self.agent_a.name, "id": self.agent_a.agent_id, "strategy": self.agent_a.strategy},
            "agent_b": {"name": self.agent_b.name, "id": self.agent_b.agent_id, "strategy": self.agent_b.strategy},
            "agent_a_score": self.agent_a_score,
            "agent_b_score": self.agent_b_score,
            "agent_a_actions": self.agent_a_actions,
            "agent_b_actions": self.agent_b_actions,
            "efficiency_a": round(self.efficiency_a, 4),
            "efficiency_b": round(self.efficiency_b, 4),
            "winner": self.winner,
            "winner_name": self.winner_name,
            "turns": self.turns,
            "map_seed": self.map_seed,
            "agent_a_exit": self.agent_a_exit,
            "agent_b_exit": self.agent_b_exit,
            "timeline": [
                {
                    "turn": t.turn, "agent": t.player_id,
                    "action": t.action, "pos": {"row": t.pos_row, "col": t.pos_col},
                    "score": t.score, "stamina": t.stamina, "reward": t.reward,
                    "thinking": t.thinking
                } for t in self.timeline
            ],
            "cot_log": self.cot_log,
            "timestamp": self.timestamp
        }


def calc_efficiency(actions: int, baseline: int = HUMAN_EFFICIENCY_BASELINE) -> float:
    if actions <= 0:
        return 0.0
    return min(1.0, baseline / actions)


class MatchEngine:
    """对战引擎（双方交替行动）"""
    
    def __init__(self, rules: Optional[SeasonRules] = None, verbose: bool = False):
        self.verbose = verbose
        self.rules = rules or SeasonRules()

    def run_match(
        self,
        config_a: AgentConfig,
        config_b: AgentConfig,
        max_stamina_override: Optional[int] = None
    ) -> MatchResult:
        
        if max_stamina_override:
            self.rules.stamina = max_stamina_override
        
        env = MazeEnvironment(rules=self.rules)
        env.reset(["agent_a", "agent_b"])
        
        agent_a = make_agent(config_a)
        agent_b = make_agent(config_b)
        
        match_id = str(uuid.uuid4())[:12]
        timeline: List[TurnRecord] = []
        cot_log: List[Dict] = []
        
        if self.verbose:
            print("=" * 50)
            print(f"🏟️  {config_a.name} ({config_a.strategy}) vs {config_b.name} ({config_b.strategy})")
            print(f"地图种子: {env.rules.map_seed} | 体力: {self.rules.stamina}")
            print("=" * 50)
            print(env.render())
            print()
        
        turn = 0
        while True:
            pa = env.players["agent_a"]
            pb = env.players["agent_b"]
            
            # agent_a 行动
            if pa.stamina > 0 and not pa.reached_exit:
                obs_a = env.get_observation("agent_a")
                thinking_a = ""
                if isinstance(agent_a, LLMAgent):
                    action_a, thinking_a = agent_a.act(obs_a)
                else:
                    action_a = agent_a.act(obs_a)
                obs_a2, reward_a, _ = env.step("agent_a", action_a)
                
                timeline.append(TurnRecord(
                    turn=turn, player_id="agent_a", action=action_a,
                    pos_row=obs_a2.player_pos.row, pos_col=obs_a2.player_pos.col,
                    score=obs_a2.score, stamina=obs_a2.stamina, reward=reward_a,
                    thinking=thinking_a
                ))
                if thinking_a:
                    cot_log.append({"turn": turn, "agent": config_a.name, "thinking": thinking_a})
            
            # agent_b 行动
            if pb.stamina > 0 and not pb.reached_exit:
                obs_b = env.get_observation("agent_b")
                thinking_b = ""
                if isinstance(agent_b, LLMAgent):
                    action_b, thinking_b = agent_b.act(obs_b)
                else:
                    action_b = agent_b.act(obs_b)
                obs_b2, reward_b, _ = env.step("agent_b", action_b)
                
                timeline.append(TurnRecord(
                    turn=turn, player_id="agent_b", action=action_b,
                    pos_row=obs_b2.player_pos.row, pos_col=obs_b2.player_pos.col,
                    score=obs_b2.score, stamina=obs_b2.stamina, reward=reward_b,
                    thinking=thinking_b
                ))
                if thinking_b:
                    cot_log.append({"turn": turn, "agent": config_b.name, "thinking": thinking_b})
            
            turn += 1
            
            if self.verbose and turn % 20 == 0:
                print(f"[轮次 {turn}] {config_a.name}: 分={pa.score} 体力={pa.stamina} | "
                      f"{config_b.name}: 分={pb.score} 体力={pb.stamina}")
            
            # 结束条件：双方体力耗尽或到达出口
            if (pa.stamina <= 0 or pa.reached_exit) and (pb.stamina <= 0 or pb.reached_exit):
                break
            if turn > self.rules.stamina * 2 + 50:  # 保险截止
                break
        
        pa = env.players["agent_a"]
        pb = env.players["agent_b"]
        
        eff_a = calc_efficiency(pa.actions_taken)
        eff_b = calc_efficiency(pb.actions_taken)
        
        if pa.score > pb.score:
            winner, winner_name = "agent_a", config_a.name
        elif pb.score > pa.score:
            winner, winner_name = "agent_b", config_b.name
        else:
            winner, winner_name = None, "平局"
        
        if self.verbose:
            print("\n" + "=" * 50)
            print("🏆 对战结束!")
            print("=" * 50)
            w_emoji = "🥇" if winner else "🤝"
            print(f"{w_emoji} 胜利者: {winner_name}")
            print(f"\n📊 战报:")
            for pid, ps, cfg, eff in [
                ("agent_a", pa, config_a, eff_a),
                ("agent_b", pb, config_b, eff_b)
            ]:
                exit_bonus = f" (含出口加分)" if ps.reached_exit else ""
                print(f"  {cfg.name} [{cfg.strategy}]:")
                print(f"    分数: {ps.score}{exit_bonus}")
                print(f"    行动: {ps.actions_taken} | 剩余体力: {ps.stamina}")
                print(f"    效率: {eff:.3f}")
        
        return MatchResult(
            match_id=match_id,
            agent_a=config_a, agent_b=config_b,
            agent_a_score=pa.score, agent_b_score=pb.score,
            agent_a_actions=pa.actions_taken, agent_b_actions=pb.actions_taken,
            agent_a_stamina_left=pa.stamina, agent_b_stamina_left=pb.stamina,
            agent_a_exit=pa.reached_exit, agent_b_exit=pb.reached_exit,
            efficiency_a=eff_a, efficiency_b=eff_b,
            winner=winner, winner_name=winner_name,
            turns=turn, timeline=timeline, cot_log=cot_log,
            map_seed=env.rules.map_seed,
            rules={
                "gem_score": env.rules.gem_score,
                "chest_rewards": env.rules.chest_rewards,
                "exit_bonus": env.rules.exit_bonus,
                "stamina": env.rules.stamina
            }
        )


# ── 赛季管理 + Elo ────────────────────────────────────────────
ELO_K = 32
ELO_INIT = 1000

@dataclass
class PlayerStats:
    agent_id: str
    name: str
    strategy: str = "rule_based"
    elo: float = ELO_INIT
    wins: int = 0
    losses: int = 0
    ties: int = 0
    total_score: int = 0
    total_actions: int = 0
    match_count: int = 0

class TournamentManager:
    def __init__(self):
        self.players: Dict[str, PlayerStats] = {}
        self.match_history: List[MatchResult] = []

    def register(self, config: AgentConfig):
        if config.agent_id not in self.players:
            self.players[config.agent_id] = PlayerStats(
                agent_id=config.agent_id,
                name=config.name,
                strategy=config.strategy
            )

    def record_match(self, result: MatchResult):
        self.match_history.append(result)
        self.register(result.agent_a)
        self.register(result.agent_b)
        
        pa = self.players[result.agent_a.agent_id]
        pb = self.players[result.agent_b.agent_id]
        
        # Elo 更新
        ea = 1 / (1 + 10 ** ((pb.elo - pa.elo) / 400))
        eb = 1 - ea
        
        if result.winner == "agent_a":
            sa, sb = 1, 0
            pa.wins += 1; pb.losses += 1
        elif result.winner == "agent_b":
            sa, sb = 0, 1
            pa.losses += 1; pb.wins += 1
        else:
            sa, sb = 0.5, 0.5
            pa.ties += 1; pb.ties += 1
        
        pa.elo += ELO_K * (sa - ea)
        pb.elo += ELO_K * (sb - eb)
        
        pa.total_score += result.agent_a_score
        pb.total_score += result.agent_b_score
        pa.total_actions += result.agent_a_actions
        pb.total_actions += result.agent_b_actions
        pa.match_count += 1
        pb.match_count += 1

    def leaderboard(self) -> List[Dict]:
        rows = []
        for pid, ps in sorted(self.players.items(), key=lambda x: -x[1].elo):
            total = ps.wins + ps.losses + ps.ties
            rows.append({
                "agent_id": pid,
                "name": ps.name,
                "strategy": ps.strategy,
                "elo": round(ps.elo, 1),
                "wins": ps.wins, "losses": ps.losses, "ties": ps.ties,
                "win_rate": round(ps.wins / total, 3) if total > 0 else 0,
                "avg_score": round(ps.total_score / max(ps.match_count, 1)),
                "avg_efficiency": round(
                    calc_efficiency(ps.total_actions // max(ps.match_count, 1)), 3
                )
            })
        return rows


if __name__ == "__main__":
    # 快速验证
    rules = SeasonRules(
        season_id="S1_v2",
        map_seed=2026,
        stamina=200,  # 测试用小体力
        gem_set_bonus=5,
        exit_bonus=20
    )
    
    config_a = AgentConfig(
        name="LLM大师", agent_id="llm_a", strategy="llm",
        skills=["pathfinder", "memory_map", "opponent_tracker"],
        system_prompt="优先宝箱(期望均值约4.8分)，再追宝石套装，最后冲出口。"
    )
    config_b = AgentConfig(
        name="规则勇士", agent_id="rule_b", strategy="rule_based",
        skills=["pathfinder", "memory_map"]
    )
    
    engine = MatchEngine(rules=rules, verbose=True)
    result = engine.run_match(config_a, config_b)
    
    print(f"\n📋 CoT 记录 (前3条):")
    for entry in result.cot_log[:3]:
        print(f"  [{entry['agent']}] {entry['thinking']}")
    
    print(f"\n✅ 验证完成 | 地图种子: {result.map_seed}")
