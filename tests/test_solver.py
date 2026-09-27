"""solver 单元测试（不依赖 pytest，直接 python tests/test_solver.py 运行）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.solver import MachineError, solve, validate_machine  # noqa: E402


def base_machine(**over):
    m = {
        "states": ["s"],
        "initial": "s",
        "finals": ["s"],
        "keys": [{"id": "A", "cost": 1}],
        "transitions": [{"state": "s", "key": "A", "output": "a", "next": "s"}],
    }
    m.update(over)
    return m


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("基础：重复键输出多字符")
def t_basic():
    m = validate_machine(base_machine(
        keys=[{"id": "A", "cost": 1}],
        transitions=[{"state": "s", "key": "A", "output": "hi", "next": "s"}],
    ))
    r = solve(m, "hihi", 0)
    assert r["found"]
    assert r["solution"]["key_sequence"] == ["A", "A"]
    assert r["solution"]["total_cost"] == 2
    assert r["solution"]["press_count"] == 2
    assert r["steps"][0]["output"] == "hi"
    assert r["steps"][1]["cumulative_cost"] == 2


@case("死键：空输出自循环不会卡住，终态可达")
def t_dead_loop():
    m = validate_machine({
        "states": ["base", "dead"],
        "initial": "base",
        "finals": ["base"],
        "keys": [{"id": "D", "cost": 1}, {"id": "A", "cost": 1}],
        "transitions": [
            {"state": "base", "key": "D", "output": "", "next": "dead"},
            {"state": "dead", "key": "D", "output": "", "next": "dead"},
            {"state": "dead", "key": "A", "output": "â", "next": "base"},
            {"state": "base", "key": "A", "output": "a", "next": "base"},
        ],
    })
    r = solve(m, "â", 0)
    assert r["found"]
    # D A 即到达；再多按 D 只会更贵，标签比较保证最短最优
    assert r["solution"]["key_sequence"] == ["D", "A"]
    assert r["solution"]["total_cost"] == 2
    assert [s["output"] for s in r["steps"]] == ["", "â"]


@case("换键附加成本：首键不加，相邻不同键加收")
def t_surcharge():
    m = validate_machine(base_machine(
        keys=[{"id": "A", "cost": 1}, {"id": "B", "cost": 1}],
        transitions=[
            {"state": "s", "key": "A", "output": "a", "next": "s"},
            {"state": "s", "key": "B", "output": "b", "next": "s"},
        ],
    ))
    r = solve(m, "ab", 3)
    assert r["found"]
    assert r["solution"]["key_sequence"] == ["A", "B"]
    # 1 + 1 + 一次换键 3
    assert r["solution"]["total_cost"] == 5
    assert r["steps"][0]["switch_cost"] == 0
    assert r["steps"][1]["switch_cost"] == 3
    # 同键重复不收附加
    r2 = solve(m, "aa", 3)
    assert r2["solution"]["total_cost"] == 2


@case("字典序：成本与按键数相同取键 ID 序列字典序最小")
def t_lex():
    m = validate_machine(base_machine(
        keys=[{"id": "B", "cost": 1}, {"id": "A", "cost": 1}],
        transitions=[
            {"state": "s", "key": "B", "output": "x", "next": "s"},
            {"state": "s", "key": "A", "output": "x", "next": "s"},
        ],
    ))
    r = solve(m, "x", 0)
    assert r["found"]
    assert r["solution"]["key_sequence"] == ["A"]  # A < B


@case("空目标：零按键停在初态（初态即终态）合法")
def t_empty_target():
    m = validate_machine(base_machine())
    r = solve(m, "", 0)
    assert r["found"]
    assert r["solution"]["key_sequence"] == []
    assert r["solution"]["total_cost"] == 0
    assert r["steps"] == []

    # 初态不是终态时，空目标也必须按到终态；死键环不应被选中
    m2 = validate_machine({
        "states": ["q0", "q1"],
        "initial": "q0",
        "finals": ["q1"],
        "keys": [{"id": "D", "cost": 1}],
        "transitions": [{"state": "q0", "key": "D", "output": "", "next": "q1"}],
    })
    r2 = solve(m2, "", 0)
    assert r2["found"]
    assert r2["solution"]["key_sequence"] == ["D"]


@case("无解：终态不可达 / 输出不匹配均明确提示")
def t_unsat():
    # 能产出但停在非终态
    m = validate_machine({
        "states": ["s", "t"],
        "initial": "s",
        "finals": ["t"],
        "keys": [{"id": "A", "cost": 1}],
        "transitions": [{"state": "s", "key": "A", "output": "a", "next": "s"}],
    })
    r = solve(m, "a", 0)
    assert not r["found"]
    assert "无解" in r["message"] or "不存在" in r["message"]

    # 目标无法拼出
    m2 = validate_machine(base_machine())
    r2 = solve(m2, "b", 0)
    assert not r2["found"]


@case("不做归一化：é 与 e+\\u0301 按码点严格区分")
def t_no_norm():
    m = validate_machine(base_machine(
        keys=[{"id": "E", "cost": 1}],
        transitions=[{"state": "s", "key": "E", "output": "é", "next": "s"}],
    ))
    nfc = "\u00e9"          # U+00E9 单码点（NFC）
    nfd = "e\u0301"         # U+0065 + U+0301 两个码点（NFD）
    assert solve(m, nfc, 0)["found"]
    assert not solve(m, nfd, 0)["found"]  # NFD 形式 e + ◌́
    assert len(nfc) == 1
    assert len(nfd) == 2


@case("校验错误：空终态集 / 重复 ID / 重复转移 / 无效引用 / 非正成本")
def t_validation():
    def expect_error(obj):
        try:
            validate_machine(obj)
        except MachineError:
            return
        raise AssertionError("应当抛出 MachineError")

    expect_error(base_machine(finals=[]))
    expect_error(base_machine(keys=[{"id": "A", "cost": 1}, {"id": "A", "cost": 2}]))
    expect_error(base_machine(keys=[{"id": "A", "cost": 0}]))
    expect_error(base_machine(keys=[{"id": "A", "cost": -3}]))
    expect_error(base_machine(keys=[{"id": "A ", "cost": 1}]))  # ID 含空白
    expect_error(base_machine(keys=[{"id": "é", "cost": 1}]))   # 非 ASCII
    expect_error(base_machine(transitions=[
        {"state": "s", "key": "A", "output": "", "next": "s"},
        {"state": "s", "key": "A", "output": "a", "next": "s"},
    ]))
    expect_error(base_machine(initial="x"))
    expect_error(base_machine(finals=["x"]))
    expect_error(base_machine(transitions=[
        {"state": "s", "key": "X", "output": "a", "next": "s"}
    ]))
    expect_error(base_machine(transitions=[
        {"state": "s", "key": "A", "output": "a", "next": "x"}
    ]))
    expect_error(base_machine(states=["s", "s"]))
    expect_error(base_machine(states=[]))
    expect_error(base_machine(keys=[]))


@case("参数边界：目标 101 码点 / 附加成本超界")
def t_param_bounds():
    m = validate_machine(base_machine())
    for bad in (-1, 101, 1.5, True):
        try:
            solve(m, "a", bad)
        except MachineError:
            pass
        else:
            raise AssertionError(f"surcharge={bad!r} 应报错")
    try:
        solve(m, "a" * 101, 0)
    except MachineError:
        pass
    else:
        raise AssertionError("101 码点目标应报错")


@case("内置死键示例：café 低附加成本走死键组合，高附加成本走直输键")
def t_example():
    import json
    import re
    raw = Path(__file__).resolve().parent.parent.joinpath(
        "static/app.js").read_text(encoding="utf-8").split("const EXAMPLE = ", 1)[1].split(";\n", 1)[0]
    # app.js 中是 JS 对象字面量（键名无引号、含尾随逗号），补成合法 JSON
    raw = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', raw)
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    data = json.loads(raw)
    m = validate_machine(data)
    r = solve(m, "café", 2)
    assert r["found"], "示例应当有解"
    # 低附加成本：Acute(空输出死键)+E 组合（键成本 6 + 4 次换键×2 = 14，5 键）
    seq = r["solution"]["key_sequence"]
    assert seq == ["C", "A", "F", "Acute", "E"]
    assert r["solution"]["total_cost"] == 14
    assert [s["output"] for s in r["steps"]] == ["c", "a", "f", "", "é"]
    # 高附加成本：少一次换键的 Eacute 直输更优（键成本 11 + 3 次换键×10 = 41，4 键）
    r2 = solve(m, "café", 10)
    assert r2["solution"]["key_sequence"] == ["C", "A", "F", "Eacute"]
    assert r2["solution"]["total_cost"] == 41
    # 死键可被 Space 救活输出字面符号；Hi 一次输出两个字符
    assert solve(m, "e´", 0)["solution"]["key_sequence"] == ["E", "Acute", "Space"]
    assert solve(m, "hi", 0)["solution"]["key_sequence"] == ["Hi"]


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {exc!r}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
