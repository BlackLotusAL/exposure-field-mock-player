"""L3 搜索：在 L2（greedy.py）的基础上，逐条推演候选路线上双方的到达时间，再做取舍。

与 L2 的区别见 README.md。每回合推演最多用 150 毫秒，到时就用已经推演过的最好路线。
"""
import os
import sys
import time

try:
    import arena  # noqa: F401  平台和本地工具会把 arena 放进模块搜索路径
except ImportError:  # 直接用 python3 运行本文件时，到材料包根目录去找
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from arena.sdk import run                              # noqa: E402
from arena.core import DIRS, DX, DY, OPP, PARAMS      # noqa: E402
from lib import INF, bfs, closure_gain  # noqa: E402
from greedy import GreedyBot                 # noqa: E402

BUDGET = 0.15                     # 每回合推演限时（秒），规则时限 300 毫秒
BIG = [(8, 12), (10, 14), (12, 18), (14, 20)]


class SearchBot(GreedyBot):
    margin = 1
    sizes = [(3, 4), (4, 6), (5, 8), (6, 9), (5, 6), (7, 10), (3, 6), (2, 4), (3, 3), (2, 2)] + BIG
    big = True
    remote_n = 4

    def act(self, st):
        self.t0 = time.time()
        g, s, me = st.game, st.seat, st.me
        if not me.alive:
            self.plan = []
            return me.dir
        f = self.facts(st)
        # 1. 回家
        if not f['home'] and f['threat'] <= f['d_home'] + self.margin and f['home_dir']:
            self.plan = []
            return self.dodge(st, f, f['home_dir'])
        # 2. 赛跑式进攻
        a = self.attack(st, f) or self.item(st, f)
        if a and self.ok_step(g, me, s, a):
            self.plan = []
            return self.dodge(st, f, a)
        # 3. 推演选路线
        if not self.plan:
            if not f['home']:
                return self.dodge(st, f, f['home_dir'] or me.dir)
            self.plan = self.make_plan(st, f)
        d = self.plan[0]
        if not self.ok_step(g, me, s, d):
            self.plan = []
            if not f['home'] and f['home_dir']:
                return f['home_dir']
            for d2 in DIRS:
                if self.ok_step(g, me, s, d2):
                    return d2
            return me.dir
        if self.boost(st, f, d) and (f['home'] or f['d_home'] + 2 < f['threat']):
            del self.plan[:2]
            return d + '+'
        nd = self.dodge(st, f, d)
        if nd != d:
            self.plan = []
            return nd
        self.plan.pop(0)
        return d

    item_range = 16
    item_bonus = (4, 10)        # 道具周围 2 格内每格加分、道具格本身加分

    def value_of(self, st, got, steal, length):
        """占位：道具预告或出现后，把它周围的格子圈进自己的图形区更划算。"""
        v = GreedyBot.value_of(self, st, got, steal, length)
        g = st.game
        it = g.boost or g.boost_next
        if not it:
            return v
        N = g.N
        near, at = self.item_bonus
        for k in got:
            dx, dy = abs(k % N - it['x']), abs(k // N - it['y'])
            if dx == 0 and dy == 0:
                v += at
            elif max(dx, dy) <= 2:
                v += near
        return v

    def item(self, st, f):
        """道具：已出现且我先到（平手时道具格在我的图形区内也去），或已预告且掐好时间提前过去。"""
        g, s = st.game, st.seat
        if not (f['home'] or f['d_home'] + 1 < f['threat']):
            return None
        dist, first = f['mine']
        b, nb = g.boost, g.boost_next
        if b:
            k = g.idx(b['x'], b['y'])
            if 0 < dist[k] <= self.item_range and (dist[k] < f['reach'][k] or (dist[k] == f['reach'][k] and g.owner[k] == s)):
                return first[k]
        if nb:
            k = g.idx(nb['x'], nb['y'])
            # 到达回合 = 当前回合 + 步数；道具在第 at 回合末出现，最好在 at+1 回合到
            if 0 < dist[k] <= self.item_range and dist[k] <= f['reach'][k] and g.turn + dist[k] >= nb['at'] + 1:
                return first[k]
        return None

    # ---------------------------------------------------------------- 进攻
    def attack(self, st, f):
        g, s, en = st.game, st.seat, st.enemy
        N = g.N
        dist, first = f['mine']
        if not en.alive or not (f['home'] or f['d_home'] + 1 < f['threat']):
            return None
        # 对手轮廓：我先到，它还没回家
        e_here = g.idx(en.x, en.y)
        e_trail = [k for k in range(N * N) if g.trail[k] == 1 - s]
        if e_trail:
            ed, _ = bfs(g, en.x, en.y, blocked=lambda k: g.trail[k] == 1 - s and k != e_here, first_ban=OPP[en.dir])
            back = min([ed[k] for k in range(N * N) if g.owner[k] == 1 - s and ed[k] > 0] or [INF])
            back_t = (back + f['es'] - 1) // f['es']
            best, bd = INF, None
            for k in e_trail:
                if 0 < dist[k] < best:
                    best, bd = dist[k], first[k]
            if bd and best <= back_t and best <= 20:
                return bd
        return None

    # ---------------------------------------------------------------- 避免撞头
    def dodge(self, st, f, d):
        g, s, me, en = st.game, st.seat, st.me, st.enemy
        if not en.alive or d is None:
            return d
        nx, ny = me.x + DX[d], me.y + DY[d]
        if not g.inb(nx, ny) or g.owner[g.idx(nx, ny)] == s:
            return d                                     # 目标格在己方图形区：撞头时我安全
        reach = 2 if en.boost_left > 0 else 1
        if abs(en.x - nx) + abs(en.y - ny) > reach:
            return d
        for d2 in DIRS:
            if d2 == d or not self.ok_step(g, me, s, d2):
                continue
            x2, y2 = me.x + DX[d2], me.y + DY[d2]
            if abs(en.x - x2) + abs(en.y - y2) > reach or g.owner[g.idx(x2, y2)] == s:
                return d2
        return d

    # ---------------------------------------------------------------- 推演选路线

    def plan_value(self, st, f, moves, trail):
        g, s = st.game, st.seat
        T = len(moves)
        gain, steal, got = closure_gain(g, s, trail)
        if gain <= 0:
            return -INF
        v = self.value_of(st, got, steal, T)
        return v / (T + 8.0)              # 单位时间收益（L2 用 价值×10 − 步数）

    budget = BUDGET


def create():
    return SearchBot()


if __name__ == '__main__':
    run(create)
