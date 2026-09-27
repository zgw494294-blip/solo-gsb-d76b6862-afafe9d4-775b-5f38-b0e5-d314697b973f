"""状态键盘（有限状态换能器）的校验与最优按键序列求解。

键盘被建模为一个带输出的有限状态机：按下一个键时，
机器从当前状态沿转移走到下一状态，并输出一个字符串（可为空，即“死键”）。

求解目标：找出输出串恰好等于目标文字、且结束于终态的按键序列，
按 (总成本, 按键数, 键 ID 序列字典序) 依次取最小。

成本 = 各键成本之和 + 相邻不同键的换键附加成本（首键不加）。
由于所有成本均为正（附加成本非负），使用 Dijkstra 算法；
空输出转移形成的环永远不可能让成本更优，因此天然不会被空循环卡住。
"""

from __future__ import annotations

import heapq
from typing import Any

MAX_STATES = 12
MAX_KEYS = 12
MAX_TARGET = 100
MAX_SURCHARGE = 100


class MachineError(ValueError):
    """键盘 JSON 或求解参数不合法。"""


def _require_type(obj: Any, types: tuple[type, ...], what: str) -> None:
    if not isinstance(obj, types):
        names = "/".join(t.__name__ for t in types)
        raise MachineError(f"{what} 必须是 {names} 类型")


def _is_str(s: Any) -> bool:
    return isinstance(s, str)


def validate_machine(data: Any) -> dict[str, Any]:
    """校验导入的键盘 JSON，返回规范化（补上空转 table）后的机器定义。"""
    _require_type(data, (dict,), "顶层 JSON 必须是对象")

    # ---- 状态 ----
    states = data.get("states")
    _require_type(states, (list,), "states（状态列表）")
    if not (1 <= len(states) <= MAX_STATES):
        raise MachineError(f"状态数量必须在 1～{MAX_STATES} 个之间")
    norm_states: list[str] = []
    for i, s in enumerate(states):
        _require_type(s, (str,), f"states[{i}]")
        if not s:
            raise MachineError("状态名不得为空字符串")
        if s in norm_states:
            raise MachineError(f"状态 {s!r} 重复")
        norm_states.append(s)
    state_set = set(norm_states)

    # ---- 初态 ----
    initial = data.get("initial")
    _require_type(initial, (str,), "initial（初态）")
    if initial not in state_set:
        raise MachineError(f"初态 {initial!r} 不在状态列表中")

    # ---- 终态（非空集合）----
    finals = data.get("finals")
    _require_type(finals, (list,), "finals（终态列表）")
    if not finals:
        raise MachineError("终态集必须非空")
    norm_finals: list[str] = []
    for i, s in enumerate(finals):
        _require_type(s, (str,), f"finals[{i}]")
        if s not in state_set:
            raise MachineError(f"终态 {s!r} 不在状态列表中")
        if s in norm_finals:
            raise MachineError(f"终态 {s!r} 重复")
        norm_finals.append(s)

    # ---- 键：唯一 ASCII ID + 正整数成本 ----
    keys = data.get("keys")
    _require_type(keys, (list,), "keys（键列表）")
    if not (1 <= len(keys) <= MAX_KEYS):
        raise MachineError(f"键数量必须在 1～{MAX_KEYS} 个之间")
    norm_keys: list[dict[str, Any]] = []
    key_ids: set[str] = set()
    for i, k in enumerate(keys):
        where = f"keys[{i}]"
        _require_type(k, (dict,), where)
        kid = k.get("id")
        _require_type(kid, (str,), f"{where}.id")
        if not kid:
            raise MachineError(f"{where}.id 不得为空")
        if not all(ord(ch) < 128 and not ch.isspace() for ch in kid):
            raise MachineError(f"键 ID {kid!r} 必须为不含空白字符的 ASCII 字符串")
        if kid in key_ids:
            raise MachineError(f"键 ID {kid!r} 重复")
        cost = k.get("cost")
        # bool 是 int 的子类，显式排除
        _require_type(cost, (int,), f"{where}（键 {kid!r}）的 cost")
        if isinstance(cost, bool) or cost <= 0:
            raise MachineError(f"键 {kid!r} 的成本必须是正整数")
        key_ids.add(kid)
        norm_keys.append({"id": kid, "cost": cost})

    # ---- 转移 ----
    transitions = data.get("transitions")
    _require_type(transitions, (list,), "transitions（转移列表）")
    seen: set[tuple[str, str]] = set()
    norm_trans: list[dict[str, str]] = []
    for i, t in enumerate(transitions):
        where = f"transitions[{i}]"
        _require_type(t, (dict,), where)
        st = t.get("state")
        _require_type(st, (str,), f"{where}.state")
        if st not in state_set:
            raise MachineError(f"{where}.state {st!r} 不是有效状态")
        kid = t.get("key")
        _require_type(kid, (str,), f"{where}.key")
        if kid not in key_ids:
            raise MachineError(f"{where}.key {kid!r} 不是有效键 ID")
        if (st, kid) in seen:
            raise MachineError(f"状态 {st!r} 与键 {kid!r} 已存在转移，同一状态与键只能有一条")
        seen.add((st, kid))
        output = t.get("output", "")
        _require_type(output, (str,), f"{where}.output")
        nxt = t.get("next")
        _require_type(nxt, (str,), f"{where}.next")
        if nxt not in state_set:
            raise MachineError(f"{where}.next {nxt!r} 不是有效状态")
        norm_trans.append({"state": st, "key": kid, "output": output, "next": nxt})

    return {
        "states": norm_states,
        "initial": initial,
        "finals": norm_finals,
        "keys": norm_keys,
        "transitions": norm_trans,
    }


def solve(machine: dict[str, Any], target: str, surcharge: int) -> dict[str, Any]:
    """在已校验的机器上求解最优按键序列。

    返回 {"found": bool, ...}；found 为 True 时附带 solution、steps、
    total_cost、press_count 以及搜索统计。
    """
    if not _is_str(target):
        raise MachineError("目标文字必须是字符串")
    # len() 即 Unicode 码点数（Python str 以码点存储）
    if len(target) > MAX_TARGET:
        raise MachineError(f"目标文字至多 {MAX_TARGET} 个 Unicode 码点（当前 {len(target)} 个）")
    _require_type(surcharge, (int,), "换键附加成本")
    if isinstance(surcharge, bool):
        raise MachineError("换键附加成本必须是 0～100 的整数")
    if not (0 <= surcharge <= MAX_SURCHARGE):
        raise MachineError(f"换键附加成本必须在 0～{MAX_SURCHARGE} 之间")

    key_cost = {k["id"]: k["cost"] for k in machine["keys"]}
    final_set = set(machine["finals"])

    # 每个状态的出边：[(key_id, output, next_state)]
    out: dict[str, list[tuple[str, str, str]]] = {s: [] for s in machine["states"]}
    for t in machine["transitions"]:
        out[t["state"]].append((t["key"], t["output"], t["next"]))

    n = len(target)

    # 搜索节点：(已匹配码点位置 pos, 当前状态 state, 上一次按下的键 last_key)
    # last_key 为 None 表示尚未按过任何键（首键不收附加成本）。
    start = (0, machine["initial"], None)

    # 标签按题目要求的字典序依次比较：
    # (总成本, 按键数, 键 ID 序列)；序列是前缀时较短者更小，与 tuple 比较一致。
    best: dict[tuple, tuple] = {start: (0, 0, ())}
    prev: dict[tuple, tuple[tuple | None, str | None, str, int, int]] = {
        start: (None, None, "", 0, 0)
    }

    # 堆元素追加唯一计数器，避免标签相等时比较到节点 tuple 内部的 None
    counter = 0
    heap: list[tuple[tuple, int, tuple]] = [(best[start], counter, start)]

    goal: tuple | None = None
    expanded = 0

    while heap:
        label, _, node = heapq.heappop(heap)
        if label != best[node]:
            continue  # 已被更优标签取代的过期堆项
        expanded += 1

        pos, state, last_key = node
        if pos == n and state in final_set:
            goal = node
            break  # Dijkstra 按标签顺序出队，第一个到达的终态节点即全局最优

        for kid, output, nxt in out[state]:
            # 输出必须与目标在当前位置处逐码点前缀匹配；不做任何归一化
            end = pos + len(output)
            if end > n or target[pos:end] != output:
                continue
            added = key_cost[kid]
            if last_key is not None and kid != last_key:
                added += surcharge
            new_node = (end, nxt, kid)
            new_label = (label[0] + added, label[1] + 1, label[2] + (kid,))
            old = best.get(new_node)
            if old is None or new_label < old:
                best[new_node] = new_label
                prev[new_node] = (node, last_key, output, key_cost[kid], added)
                counter += 1
                heapq.heappush(heap, (new_label, counter, new_node))

    if goal is None:
        return {
            "found": False,
            "message": "不存在输出恰好等于目标文字且结束于终态的按键序列。",
            "stats": {"expanded": expanded, "target_length": n},
        }

    total_cost, press_count, key_seq = best[goal]

    # 回溯逐步信息
    chain: list[tuple] = []
    cur = goal
    while cur != start:
        chain.append(cur)
        cur = prev[cur][0]
    chain.reverse()

    steps: list[dict[str, Any]] = []
    pos_before = 0
    cumulative = 0
    state = machine["initial"]
    for node in chain:
        parent, _, output, base, added = prev[node]
        kid = node[2]
        switch = added - base
        cumulative += added
        emitted = target[pos_before : pos_before + len(output)]
        steps.append(
            {
                "index": len(steps) + 1,
                "key": kid,
                "from_state": state,
                "to_state": node[1],
                "output": emitted,
                "output_length": len(emitted),
                "key_cost": base,
                "switch_cost": switch,
                "step_cost": added,
                "cumulative_cost": cumulative,
                "matched_prefix": target[: pos_before + len(emitted)],
            }
        )
        pos_before += len(output)
        state = node[1]

    return {
        "found": True,
        "solution": {
            "key_sequence": list(key_seq),
            "press_count": press_count,
            "total_cost": total_cost,
            "final_state": goal[1],
            "output": target,
        },
        "steps": steps,
        "stats": {"expanded": expanded, "target_length": n},
    }
