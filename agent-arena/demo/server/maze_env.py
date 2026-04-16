"""
迷宫环境 v2 — 完整规则实现
- 5色宝石，套装加分机制（可配置）
- 宝箱：开启即消失并在空格重生，奖励 [0,3,5,7,9] 各20%
- 体力值限制（默认1000），走一格消耗1体力
- 出口：到达出口获得额外加分
- 地图每赛季固定，可由关卡编辑器配置
"""
import random
import copy
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

# ── 宝石颜色 ────────────────────────────────────────────────
class GemColor(str, Enum):
    RED    = "R"  # 红
    BLUE   = "B"  # 蓝
    GREEN  = "G"  # 绿
    YELLOW = "Y"  # 黄
    PURPLE = "P"  # 紫

ALL_COLORS = list(GemColor)

# ── 赛季规则配置 ─────────────────────────────────────────────
@dataclass
class SeasonRules:
    """运营者可配置的赛季规则（关卡编辑器输出）"""
    season_id: str = "S1"
    
    # 地图配置
    map_width: int = 13
    map_height: int = 13
    map_seed: Optional[int] = None          # None = 随机，固定则每赛季一样
    random_start_pos: bool = False           # 玩家起始位置是否随机
    
    # 体力配置
    stamina: int = 1000                      # 初始体力，走一格-1
    
    # 宝石配置
    gem_score: Dict[str, int] = field(default_factory=lambda: {
        c.value: 1 for c in GemColor        # 默认每颗1分
    })
    gem_set_bonus: int = 0                   # 集齐5色套装额外加分（0=不启用）
    gem_respawn: str = "set"                 # set=成套重生, single=单个重生
    
    # 宝箱配置
    chest_rewards: List[int] = field(default_factory=lambda: [0, 3, 5, 7, 9])
    chest_probs:   List[float] = field(default_factory=lambda: [0.2, 0.2, 0.2, 0.2, 0.2])
    chest_respawn: bool = True               # 被踩后重生
    
    # 出口配置
    exit_bonus: int = 20                     # 到达出口额外加分
    
    # 碰撞规则
    collision_block: bool = False            # False=不阻挡（双方可占同格）


# ── 地图格子类型 ──────────────────────────────────────────────
class Cell:
    WALL  = "#"
    EMPTY = "."
    EXIT  = "E"

@dataclass
class MapObject:
    kind: str       # "gem" | "chest" | "player_a" | "player_b" | "exit"
    color: Optional[str] = None   # for gem
    value: Optional[int] = None   # for chest reward (after open)

@dataclass
class Position:
    row: int
    col: int
    def __eq__(self, other): return self.row == other.row and self.col == other.col
    def __hash__(self): return hash((self.row, self.col))
    def __repr__(self): return f"({self.row},{self.col})"

@dataclass
class PlayerState:
    pos: Position
    score: int = 0
    stamina: int = 1000
    gems_collected: Dict[str, int] = field(default_factory=dict)  # color -> count
    sets_completed: int = 0
    actions_taken: int = 0
    reached_exit: bool = False
    cot_history: List[str] = field(default_factory=list)          # LLM CoT 记录

@dataclass
class Observation:
    """Agent 每回合收到的观测信息"""
    player_id: str
    player_pos: Position
    stamina: int
    score: int
    gems_collected: Dict[str, int]
    
    # 地图感知（全图可见，LLM 输出时也会带 map_snapshot）
    map_snapshot: List[List[str]] = field(default_factory=list)  
    gem_positions: Dict[str, Position] = field(default_factory=dict)  # color -> pos
    chest_pos: Optional[Position] = None
    exit_pos: Optional[Position] = None
    opponent_pos: Optional[Position] = None
    
    # 赛季规则提示
    rules_hint: str = ""
    turn_number: int = 0

Action = str  # "up" | "down" | "left" | "right" | "wait"
ACTIONS = ["up", "down", "left", "right"]
DELTA   = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


class MazeEnvironment:
    """
    迷宫环境 v2
    - 固定地图（赛季种子）
    - 5色宝石 + 宝箱 + 出口
    - 体力值限制
    - 宝箱踩后消失并重生
    - 宝石支持套装重生
    """

    def __init__(self, rules: Optional[SeasonRules] = None):
        self.rules = rules or SeasonRules()
        seed = self.rules.map_seed or random.randint(0, 99999)
        self.rules.map_seed = seed  # 记录实际种子（赛季固定用）
        self.rng = random.Random(seed)

        W, H = self.rules.map_width, self.rules.map_height
        # 确保奇数尺寸
        self.width  = W if W % 2 == 1 else W + 1
        self.height = H if H % 2 == 1 else H + 1
        
        self.grid: List[List[str]] = []
        self.objects: Dict[Position, MapObject] = {}   # pos -> object
        self.exit_pos: Optional[Position] = None
        self.players: Dict[str, PlayerState] = {}
        self.turn: int = 0
        self.done: bool = False
        self.done_reason: str = ""
        
        self._generate_maze()
        self._place_items()

    # ── 地图生成 ──────────────────────────────────────────────

    def _generate_maze(self):
        H, W = self.height, self.width
        self.grid = [[Cell.WALL] * W for _ in range(H)]
        
        # 递归回溯
        def carve(r, c):
            dirs = [(0, 2), (0, -2), (2, 0), (-2, 0)]
            self.rng.shuffle(dirs)
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if 0 < nr < H-1 and 0 < nc < W-1 and self.grid[nr][nc] == Cell.WALL:
                    self.grid[r + dr//2][c + dc//2] = Cell.EMPTY
                    self.grid[nr][nc] = Cell.EMPTY
                    carve(nr, nc)

        self.grid[1][1] = Cell.EMPTY
        carve(1, 1)

    def _empty_cells(self) -> List[Position]:
        return [
            Position(r, c)
            for r in range(self.height)
            for c in range(self.width)
            if self.grid[r][c] == Cell.EMPTY
            and Position(r, c) not in self.objects
        ]

    def _place_items(self):
        cells = self._empty_cells()
        self.rng.shuffle(cells)
        
        # 出口（右下角附近）
        br, bc = self.height - 2, self.width - 2
        exit_pos = Position(br, bc)
        if self.grid[br][bc] == Cell.WALL:
            exit_pos = cells.pop()
        else:
            cells = [c for c in cells if c != exit_pos]
        self.exit_pos = exit_pos
        self.grid[exit_pos.row][exit_pos.col] = Cell.EXIT
        
        # 5色宝石
        for color in ALL_COLORS:
            if not cells: break
            pos = cells.pop()
            self.objects[pos] = MapObject(kind="gem", color=color.value)
        
        # 1个宝箱
        if cells:
            pos = cells.pop()
            self.objects[pos] = MapObject(kind="chest")

    def _add_player(self, player_id: str, pos: Optional[Position] = None):
        if pos is None:
            pos = Position(1, 1) if player_id == "agent_a" else Position(1, self.width - 2)
            # 确保不在墙里
            if self.grid[pos.row][pos.col] == Cell.WALL:
                cells = self._empty_cells()
                pos = cells[0] if cells else Position(1, 1)
        self.players[player_id] = PlayerState(
            pos=pos,
            stamina=self.rules.stamina
        )

    def reset(self, player_ids: List[str] = ["agent_a", "agent_b"]):
        """重置（两个玩家入场）"""
        self.__init__(self.rules)
        for pid in player_ids:
            self._add_player(pid)
        return {pid: self.get_observation(pid) for pid in player_ids}

    # ── 游戏逻辑 ─────────────────────────────────────────────

    def step(self, player_id: str, action: Action) -> Tuple["Observation", float, bool]:
        """执行一步，返回 (obs, reward, done)"""
        if player_id not in self.players:
            self._add_player(player_id)
        
        p = self.players[player_id]
        if p.stamina <= 0 or p.reached_exit:
            return self.get_observation(player_id), 0.0, self._check_done()
        
        reward = 0.0
        new_pos = self._try_move(p.pos, action)
        moved = (new_pos != p.pos)
        
        if moved:
            p.pos = new_pos
            p.stamina -= 1
            p.actions_taken += 1
        
        # 收集物品
        obj = self.objects.get(p.pos)
        if obj:
            if obj.kind == "gem":
                pts = self.rules.gem_score.get(obj.color, 1)
                p.score += pts
                reward += pts
                color = obj.color
                p.gems_collected[color] = p.gems_collected.get(color, 0) + 1
                del self.objects[p.pos]
                
                # 套装检测
                if self.rules.gem_set_bonus > 0:
                    sets = min(p.gems_collected.get(c.value, 0) for c in ALL_COLORS)
                    new_sets = sets - p.sets_completed
                    if new_sets > 0:
                        bonus = new_sets * self.rules.gem_set_bonus
                        p.score += bonus
                        reward += bonus
                        p.sets_completed = sets
                
                # 宝石重生
                self._respawn_gems(color)
                
            elif obj.kind == "chest":
                # 宝箱：即时开出奖励，重生到新位置
                chest_reward = self.rng.choices(
                    self.rules.chest_rewards,
                    weights=self.rules.chest_probs
                )[0]
                p.score += chest_reward
                reward += chest_reward
                del self.objects[p.pos]
                if self.rules.chest_respawn:
                    self._respawn_chest()
        
        # 到达出口
        cell = self.grid[p.pos.row][p.pos.col]
        if cell == Cell.EXIT and not p.reached_exit:
            p.reached_exit = True
            p.score += self.rules.exit_bonus
            reward += self.rules.exit_bonus
        
        self.turn += 1
        done = self._check_done()
        return self.get_observation(player_id), reward, done

    def _try_move(self, pos: Position, action: Action) -> Position:
        if action not in DELTA:
            return pos
        dr, dc = DELTA[action]
        nr, nc = pos.row + dr, pos.col + dc
        if 0 <= nr < self.height and 0 <= nc < self.width and self.grid[nr][nc] != Cell.WALL:
            return Position(nr, nc)
        return pos

    def _respawn_gems(self, color: str):
        """宝石重生逻辑"""
        if self.rules.gem_respawn == "set":
            # 成套重生：当5色都被收走才重生全套
            existing_colors = {v.color for v in self.objects.values() if v.kind == "gem"}
            if len(existing_colors) == 0:
                self._place_gems_all()
        else:
            # 单个重生
            cells = self._empty_cells()
            if cells:
                pos = self.rng.choice(cells)
                self.objects[pos] = MapObject(kind="gem", color=color)

    def _place_gems_all(self):
        cells = self._empty_cells()
        self.rng.shuffle(cells)
        for gem_color in ALL_COLORS:
            if cells:
                self.objects[cells.pop()] = MapObject(kind="gem", color=gem_color.value)

    def _respawn_chest(self):
        """宝箱重生到随机空格"""
        cells = self._empty_cells()
        if cells:
            pos = self.rng.choice(cells)
            self.objects[pos] = MapObject(kind="chest")

    def _check_done(self) -> bool:
        all_stamina_out = all(
            p.stamina <= 0 or p.reached_exit
            for p in self.players.values()
        )
        if all_stamina_out:
            self.done = True
            self.done_reason = "体力耗尽或全员到达出口"
        return self.done

    # ── 观测 ─────────────────────────────────────────────────

    def get_observation(self, player_id: str) -> Observation:
        p = self.players.get(player_id)
        if not p:
            self._add_player(player_id)
            p = self.players[player_id]
        
        opponent_id = "agent_b" if player_id == "agent_a" else "agent_a"
        opp = self.players.get(opponent_id)
        
        gem_positions = {
            obj.color: pos
            for pos, obj in self.objects.items()
            if obj.kind == "gem"
        }
        chest_pos = next(
            (pos for pos, obj in self.objects.items() if obj.kind == "chest"),
            None
        )
        
        # 构建地图快照
        snapshot = [row[:] for row in self.grid]
        for pos, obj in self.objects.items():
            if obj.kind == "gem":
                snapshot[pos.row][pos.col] = obj.color
            elif obj.kind == "chest":
                snapshot[pos.row][pos.col] = "C"
        for pid, ps in self.players.items():
            snapshot[ps.pos.row][ps.pos.col] = "A" if pid == "agent_a" else "B"
        
        rules_hint = (
            f"宝石分值: {self.rules.gem_score} | "
            f"套装加分: {self.rules.gem_set_bonus} | "
            f"宝箱奖励: {self.rules.chest_rewards}(各{int(self.rules.chest_probs[0]*100)}%) | "
            f"出口加分: {self.rules.exit_bonus} | "
            f"重生规则: {self.rules.gem_respawn}"
        )
        
        return Observation(
            player_id=player_id,
            player_pos=p.pos,
            stamina=p.stamina,
            score=p.score,
            gems_collected=dict(p.gems_collected),
            map_snapshot=snapshot,
            gem_positions=gem_positions,
            chest_pos=chest_pos,
            exit_pos=self.exit_pos,
            opponent_pos=opp.pos if opp else None,
            rules_hint=rules_hint,
            turn_number=self.turn
        )

    def render(self, show_objects=True) -> str:
        snapshot = [row[:] for row in self.grid]
        for pos, obj in self.objects.items():
            if obj.kind == "gem":
                snapshot[pos.row][pos.col] = obj.color
            elif obj.kind == "chest":
                snapshot[pos.row][pos.col] = "C"
        for pid, ps in self.players.items():
            snapshot[ps.pos.row][ps.pos.col] = "A" if pid == "agent_a" else "B"
        lines = [" ".join(row) for row in snapshot]
        
        if show_objects:
            lines.append("")
            for pid, ps in self.players.items():
                tag = "A" if pid == "agent_a" else "B"
                lines.append(f"  [{tag}] 分={ps.score} 体力={ps.stamina} 宝石={ps.gems_collected}")
        return "\n".join(lines)

    def get_state_dict(self) -> Dict:
        """序列化为字典（API 传输用）"""
        return {
            "turn": self.turn,
            "done": self.done,
            "done_reason": self.done_reason,
            "players": {
                pid: {
                    "pos": [p.pos.row, p.pos.col],
                    "score": p.score,
                    "stamina": p.stamina,
                    "gems_collected": p.gems_collected,
                    "actions_taken": p.actions_taken,
                    "reached_exit": p.reached_exit
                }
                for pid, p in self.players.items()
            },
            "objects": {
                f"{pos.row},{pos.col}": {"kind": obj.kind, "color": obj.color}
                for pos, obj in self.objects.items()
            },
            "exit": [self.exit_pos.row, self.exit_pos.col] if self.exit_pos else None,
            "map_seed": self.rules.map_seed
        }
