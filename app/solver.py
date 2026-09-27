"""状态键盘求解器：规格校验 + 最优按键序列搜索。

搜索算法：在 (当前状态, 已匹配目标码点数) 构成的有限图上做 Dijkstra，
优先级为 (总成本, 按键数, 键 ID 序列) 的字典序。由于键成本为正整数，
每条边的优先级严格递增，空输出自环不会造成死循环；节点数有限
(状态数 × (目标长度 + 1))，算法必然终止。
"""

from __future__ import annotations

import heapq

MAX_STATES = 12
MAX_KEYS = 12
MAX_TARGET_CODEPOINTS = 100
MAX_SWITCH_COST = 100


class SpecError(Exception):
    """机器规格或输入非法，携带全部错误信息。"""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


def _is_int(value):
    # 注意 bool 是 int 的子类，这里排除
    return isinstance(value, int) and not isinstance(value, bool)


def validate(spec):
    """校验请求 JSON，返回规范化后的机器描述；非法时抛出 SpecError。"""
    errors = []

    if not isinstance(spec, dict):
        raise SpecError(["请求体必须是 JSON 对象"])

    # ---- 状态集：1～12 个、非空、唯一 ----
    states = spec.get("states")
    if not isinstance(states, list) or not (1 <= len(states) <= MAX_STATES):
        errors.append(f"states 必须是 1～{MAX_STATES} 个状态的数组")
        states = []
    elif any(not isinstance(s, str) or not s for s in states):
        errors.append("每个状态必须是非空字符串")
        states = [s for s in states if isinstance(s, str) and s]
    if len(set(states)) != len(states):
        errors.append("状态 ID 必须唯一")
        states = list(dict.fromkeys(states))
    state_set = set(states)

    # ---- 初态 ----
    initial = spec.get("initial")
    if not isinstance(initial, str) or initial not in state_set:
        errors.append("initial 必须是 states 中已声明的状态")

    # ---- 终态集：非空、引用合法 ----
    finals = spec.get("finals")
    if not isinstance(finals, list) or len(finals) == 0:
        errors.append("finals 必须是非空数组")
        finals = []
    else:
        bad = [f for f in finals if not isinstance(f, str) or f not in state_set]
        if bad:
            errors.append(f"finals 含有未声明的状态: {bad!r}")
        if len(set(finals)) != len(finals):
            errors.append("finals 中状态重复")
            finals = list(dict.fromkeys(finals))

    # ---- 键：1～12 个、ASCII 唯一 ID、正整数成本 ----
    keys = spec.get("keys")
    key_cost = {}
    if not isinstance(keys, list) or not (1 <= len(keys) <= MAX_KEYS):
        errors.append(f"keys 必须是 1～{MAX_KEYS} 个键的数组")
        keys = []
    else:
        for i, k in enumerate(keys):
            if not isinstance(k, dict):
                errors.append(f"keys[{i}] 必须是对象")
                continue
            kid, cost = k.get("id"), k.get("cost")
            if not isinstance(kid, str) or not kid or not kid.isascii():
                errors.append(f"keys[{i}].id 必须是非空 ASCII 字符串")
                continue
            if kid in key_cost:
                errors.append(f"键 ID 重复: {kid!r}")
                continue
            if not _is_int(cost) or cost <= 0:
                errors.append(f"键 {kid!r} 的 cost 必须是正整数")
                continue
            key_cost[kid] = cost

    # ---- 转移表：引用合法、(状态, 键) 唯一 ----
    transitions = spec.get("transitions", [])
    if not isinstance(transitions, list):
        errors.append("transitions 必须是数组")
        transitions = []
    trans = {}
    for i, t in enumerate(transitions):
        if not isinstance(t, dict):
            errors.append(f"transitions[{i}] 必须是对象")
            continue
        st, kid = t.get("state"), t.get("key")
        out, nxt = t.get("output"), t.get("next")
        ok = True
        if st not in state_set:
            errors.append(f"transitions[{i}].state 未在 states 中声明: {st!r}")
            ok = False
        if kid not in key_cost:
            errors.append(f"transitions[{i}].key 未在 keys 中声明: {kid!r}")
            ok = False
        if not isinstance(out, str):
            errors.append(f"transitions[{i}].output 必须是字符串（可为空串）")
            ok = False
        if nxt not in state_set:
            errors.append(f"transitions[{i}].next 未在 states 中声明: {nxt!r}")
            ok = False
        if not ok:
            continue
        if (st, kid) in trans:
            errors.append(f"状态 {st!r} 下键 {kid!r} 的转移重复，同一状态与键只能有一条转移")
            continue
        trans[(st, kid)] = (out, nxt)

    # ---- 目标文字：至多 100 个 Unicode 码点（按原始码点，不做归一化） ----
    target = spec.get("target")
    if not isinstance(target, str):
        errors.append("target 必须是字符串")
        target = ""
    elif len(target) > MAX_TARGET_CODEPOINTS:
        errors.append(f"target 至多为 {MAX_TARGET_CODEPOINTS} 个 Unicode 码点，当前 {len(target)} 个")

    # ---- 换键附加成本：0～100 整数 ----
    switch = spec.get("switchCost")
    if not _is_int(switch) or not (0 <= switch <= MAX_SWITCH_COST):
        errors.append(f"switchCost 必须是 0～{MAX_SWITCH_COST} 的整数")
        switch = 0

    if errors:
        raise SpecError(errors)

    return {
        "states": states,
        "initial": initial,
        "finals": finals,
        "key_cost": key_cost,
        "trans": trans,
        "target": target,
        "switch": switch,
    }


def solve(machine):
    """求最优按键序列。

    返回列表 [(key_id, from_state, to_state, output, step_cost), ...]，
    无解时返回 None。目标为空且初态即终态时返回空列表（零成本解）。
    """
    target = machine["target"]
    n = len(target)
    trans = machine["trans"]
    key_cost = machine["key_cost"]
    switch = machine["switch"]
    finals = set(machine["finals"])

    start = (machine["initial"], 0)
    # 优先级：(总成本, 按键数, 键 ID 序列)，元组字典序即题目要求的取序
    best = {start: (0, 0, ())}
    parent = {}
    pq = [((0, 0, ()), start)]
    goal = None

    while pq:
        prio, node = heapq.heappop(pq)
        if prio != best.get(node):
            continue  # 已过期的堆元素
        state, pos = node
        if pos == n and state in finals:
            goal = node
            break
        cost, steps, seq = prio
        for kid in sorted(key_cost):
            edge = trans.get((state, kid))
            if edge is None:
                continue  # 死键：该状态下无转移，按下无效
            out, nxt = edge
            # 输出必须逐码点匹配目标在当前位置的内容（不做归一化）
            if not target.startswith(out, pos):
                continue
            # 首键不加附加成本；与上一键不同才加
            extra = key_cost[kid] + (switch if seq and seq[-1] != kid else 0)
            nprio = (cost + extra, steps + 1, seq + (kid,))
            nnode = (nxt, pos + len(out))
            if nnode not in best or nprio < best[nnode]:
                best[nnode] = nprio
                parent[nnode] = (node, kid, out, extra)
                heapq.heappush(pq, (nprio, nnode))

    if goal is None:
        return None

    # 回溯路径
    path = []
    node = goal
    while node != start:
        prev, kid, out, extra = parent[node]
        path.append((kid, prev[0], node[0], out, extra))
        node = prev
    path.reverse()
    return path
