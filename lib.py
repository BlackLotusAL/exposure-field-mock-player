"""工具函数：最短路、对手到达时间、闭合收益、矩形候选路线。L2 和 L3 目录各有一份相同的拷贝。"""
from arena.core import DIRS, DX, DY, OPP, PARAMS

INF = 10 ** 9
PERP = {'U': ('L', 'R'), 'D': ('L', 'R'), 'L': ('U', 'D'), 'R': ('U', 'D')}


def bfs(g, x, y, blocked=None, first_ban=None):
    """从 (x, y) 出发的 4 邻接最短路。返回 (dist, first)：first[k] 为走向 k 的第一步方向。
    blocked(k) 为真的格不可走；first_ban 是第一步禁止的方向（不能掉头）。"""
    N = g.N
    NN = N * N
    dist = [-1] * NN
    first = [None] * NN
    s0 = y * N + x
    dist[s0] = 0
    q = [s0]
    h = 0
    terr = g.terrain
    while h < len(q):
        c = q[h]; h += 1
        cx, cy = c % N, c // N
        dc = dist[c] + 1
        fc = first[c]
        for d in DIRS:
            if c == s0 and d == first_ban:
                continue
            nx, ny = cx + DX[d], cy + DY[d]
            if nx < 0 or ny < 0 or nx >= N or ny >= N:
                continue
            k = ny * N + nx
            if dist[k] >= 0 or terr[k] == '#' or (blocked is not None and blocked(k)):
                continue
            dist[k] = dc
            first[k] = fc or d
            q.append(k)
    return dist, first


def path_to(first_dist, g, start, target):
    """沿 BFS 树从 start 走到 target 的方向序列（重新做一次带父指针的 BFS）。"""
    N = g.N
    dist, _ = first_dist
    if dist[target] < 0:
        return None
    out = []
    c = target
    while c != start:
        cx, cy = c % N, c // N
        for d in DIRS:
            px, py = cx - DX[d], cy - DY[d]
            if 0 <= px < N and 0 <= py < N:
                p = py * N + px
                if dist[p] == dist[c] - 1 and dist[p] >= 0:
                    out.append(d)
                    c = p
                    break
        else:
            return None
    out.reverse()
    return out


def enemy_reach(g, e, speed):
    """对手到每一格的回合数（按 speed 格/回合）；对手停机时加上剩余停机回合，从其校准区中心出发。"""
    if e.alive:
        dist, _ = bfs(g, e.x, e.y)
        extra = 0
    else:
        s = g.beams.index(e)
        cx, cy = g.cores[s]
        dist, _ = bfs(g, cx, cy)
        extra = e.respawn
    return [INF if d < 0 else extra + (d + speed - 1) // speed for d in dist]


def trace(g, sx, sy, moves):
    """沿 moves 走，返回经过的格子（不含起点）；撞缺陷、出界或走回头路返回 None。"""
    N = g.N
    x, y = sx, sy
    cells = []
    seen = {y * N + x}
    for d in moves:
        x += DX[d]; y += DY[d]
        if x < 0 or y < 0 or x >= N or y >= N:
            return None
        k = y * N + x
        if g.terrain[k] == '#' or k in seen:
            return None
        seen.add(k)
        cells.append(k)
    return cells


def closure_gain(g, s, trail_cells):
    """假设 trail_cells 成为 s 的轮廓后闭合，返回 (新得格的价值, 其中原属对手的价值, 新得格列表)。"""
    saved = [(k, g.trail[k]) for k in trail_cells]
    for k in trail_cells:
        g.trail[k] = s
    try:
        cells = g.fill_cells(s)
    finally:
        for k, v in saved:
            g.trail[k] = v
    gain, steal, got = 0, 0, []
    for k in cells:
        if g.owner[k] == s or g.base[k] >= 0:
            continue
        v = g.val(k)
        gain += v
        if g.owner[k] == 1 - s:
            steal += v
        got.append(k)
    return gain, steal, got


def loop_candidates(g, s, x, y, cur_dir, sizes, max_inner=30, big=False):
    """矩形绕圈候选：先在己方图形区内沿 d1 走到边缘，再走 d1×a、d2×b，然后沿最短路回家。
    逐个产出 (moves, 轮廓格列表, 图形区内的步数)。"""
    N = g.N
    owner = g.owner
    for d1 in DIRS:
        if d1 == OPP[cur_dir]:
            continue
        for d2 in PERP[d1]:
            for a, b in sizes:
                moves = []
                cx, cy = x, y
                while len(moves) < max_inner:
                    nx, ny = cx + DX[d1], cy + DY[d1]
                    if not (0 <= nx < N and 0 <= ny < N) or owner[ny * N + nx] != s:
                        break
                    cx, cy = nx, ny
                    moves.append(d1)
                inner = len(moves)
                legs = [d1] * a + [d2] * b
                cells = trace(g, cx, cy, legs)
                if not cells:
                    continue
                # 起点之后的第一格必须在图形区外
                if any(owner[k] == s for k in cells):
                    continue
                ex, ey = cells[-1] % N, cells[-1] // N
                path_set = set(cells)
                dist, first = bfs(g, ex, ey, blocked=lambda k: k in path_set and owner[k] != s,
                                  first_ban=OPP[legs[-1]])
                best, bk = INF, -1
                for k in range(N * N):
                    if owner[k] == s and 0 < dist[k] < best:
                        best, bk = dist[k], k
                if bk < 0 or best > a + b + (12 if big else 6):
                    continue
                back = path_to((dist, first), g, ey * N + ex, bk)
                if back is None:
                    continue
                full = moves + legs + back
                tr = trace(g, x, y, full)
                if tr is None:
                    continue
                trail = [k for k in tr if owner[k] != s]
                yield full, trail, inner
