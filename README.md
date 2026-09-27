# 状态键盘试验（State Keyboard Lab）

一个基于 **FastAPI + 原生 JavaScript** 的有限状态换能器（带输出的有限状态机）试验台：
导入一张"状态键盘"定义，给定目标文字与换键附加成本，自动寻找
**输出恰好等于目标、且结束于终态**的最优按键序列，并在页面上逐步展示
每次按键、状态迁移、输出内容与累计成本。

## 一条命令启动

```bash
docker compose up --build
```

启动后浏览器访问：

- **地址：** http://localhost:8000
- **端口：** `8000`（宿主机与容器均为 8000）

停止：`docker compose down`。

> 本机直接运行（可选）：`pip install -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000`

## 键盘 JSON 格式

```json
{
  "states": ["base", "dead"],
  "initial": "base",
  "finals": ["base"],
  "keys": [
    { "id": "A", "cost": 1 },
    { "id": "Circum", "cost": 2 }
  ],
  "transitions": [
    { "state": "base", "key": "A", "output": "a", "next": "base" },
    { "state": "base", "key": "Circum", "output": "", "next": "dead" },
    { "state": "dead", "key": "A", "output": "â", "next": "base" }
  ]
}
```

| 字段 | 约束 |
| --- | --- |
| `states` | 1～12 个**非空且互不相同**的状态名 |
| `initial` | 初态，必须引用 `states` 中的状态 |
| `finals` | **非空**终态集，每个都必须有效且不重复 |
| `keys` | 1～12 个键；`id` 为**唯一的不含空白的 ASCII 字符串**，`cost` 为**正整数** |
| `transitions` | 转移表，含 `state`（当前状态）、`key`、`output`（输出串）、`next`（下一状态）；**同一状态与键只能有一条转移**，所有引用必须有效 |
| `output` | 可省略、为空串（**死键**，不输出字符），也可一次输出多个字符 |

## 求解规则

- 输入：**至多 100 个 Unicode 码点**的目标文字，以及 **0～100** 的换键附加成本。
- 按键序列输出的字符串（按转移顺序拼接）必须**逐码点恰好等于**目标，且机器结束于任一终态。
- **按原始码点比较，不做任何 Unicode 归一化**（例如 `é` U+00E9 与 `e` + 组合符 U+0301 不等价）。
- 总成本 = 各键 `cost` 之和 + **相邻两次按下不同键**时各收一次换键附加成本（**首键不加**）。
- 最优解依次按以下次序取最小：**① 总成本 → ② 按键数 → ③ 键 ID 序列字典序**（按 ASCII 码点）。
- 算法为 Dijkstra：所有成本为正 / 非负，**空输出（死键）自循环只会让成本增加**，
  不可能带来更优路径，因此不会被空循环卡住；不存在合法序列时页面与接口都会明确提示"无解"。

## 内置死键示例

页面点击 **"载入死键示例"**（默认已载入），目标 `café`，换键附加成本 `2`：

- `Acute` / `Circum` 是死键：在 `base` 下按下后**输出空串**，分别进入 `acute` / `circum` 状态，
  再按元音输出 `é/á`、`ê/â`，按 `Space` 输出字面符号 `´/ˆ`，连按两次死键则形成空输出自循环；
- 直接按 `Eacute` 也能输出 `é`（键成本 8，更贵）；
- 附加成本为 `2` 时最优解是 `C → A → F → Acute → E`（死键组合，总成本 14）；
  调到 `10` 后最优解切换为少一次换键的 `C → A → F → Eacute`（总成本 41）。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/validate` | 仅校验键盘 JSON，返回摘要或 400 错误 |
| `POST` | `/api/solve` | 请求体：键盘字段 + `target`（字符串）+ `surcharge`（0～100 整数）；返回最优序列与逐步明细 |
| `GET` | `/api/health` | 健康检查 |

```bash
curl -s http://localhost:8000/api/solve -H 'Content-Type: application/json' \
  -d '{"states":["s"],"initial":"s","finals":["s"],
       "keys":[{"id":"A","cost":1}],"transitions":[{"state":"s","key":"A","output":"hi","next":"s"}],
       "target":"hihi","surcharge":0}'
```

## 项目结构

```
├── app/
│   ├── main.py        # FastAPI：/api/validate、/api/solve、静态页面
│   └── solver.py      # JSON 校验 + Dijkstra 最优按键序列求解
├── static/
│   ├── index.html     # 单页界面
│   ├── app.js         # 原生 JavaScript（含死键示例与逐步播放器）
│   └── styles.css
├── tests/test_solver.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
