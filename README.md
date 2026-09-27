# 状态键盘试验

一个状态键盘（有限状态传感器）寻路实验：给定键盘机规格与目标文字，
求**输出恰好等于目标且结束于终态**的最优按键序列，并在页面上逐步展示
每一步的按键、状态转移、输出与累计成本。

- 后端：FastAPI（`POST /api/solve` 计算接口）
- 前端：原生 JavaScript 单页（无框架、无构建步骤）

## 启动

一条命令（自动构建镜像并安装依赖）：

```bash
docker compose up --build
```

访问地址：**http://localhost:8000** （端口 **8000**）

停止：`Ctrl+C` 或 `docker compose down`。

## 键盘机 JSON 格式

```json
{
  "states": ["q0", "accent"],
  "initial": "q0",
  "finals": ["q0"],
  "keys": [
    { "id": "a", "cost": 1 },
    { "id": "'", "cost": 2 }
  ],
  "transitions": [
    { "state": "q0", "key": "a", "output": "a", "next": "q0" }
  ]
}
```

校验规则：

- `states`：1～12 个非空字符串，唯一；
- `initial`：必须是已声明的状态；
- `finals`：非空，元素必须已声明；
- `keys`：1～12 个，`id` 为唯一非空 ASCII 字符串，`cost` 为正整数；
- `transitions`：`state`/`next` 必须引用已声明状态，`key` 必须引用已声明键；
  同一 `(state, key)` 只允许一条转移；`output` 可为空串或多字符串；
- 某状态下没有转移的键即**死键**，按下无效（示例中的 `x` 完全没有转移，
  `'` 在 `accent` 状态下也是死键）。

## 求解规则

- 输入：目标文字（≤ 100 个 Unicode 码点，按原始码点比较，**不做归一化**）、
  换键附加成本（0～100 的整数）；
- 总成本 = 各键成本之和 + 相邻不同键的附加成本（首键不计附加成本）；
- 优化顺序：总成本最小 → 按键数最少 → 键 ID 序列字典序最小；
- 空输出转移允许存在；算法在 `(状态, 已匹配码点数)` 有限图上做
  字典序 Dijkstra，空输出自环不会死循环，搜索必然终止；
- 无解时接口与页面都会明确提示。

## 内置示例（含死键）

页面默认载入的示例：

- 键 `'` 是经典死键：本身无输出，仅把状态切到 `accent`，
  随后按 `a`/`e` 输出 `á`/`é`（目标 `áé` 的最优序列为 `' → a → ' → e`）；
- 键 `x` 没有任何转移，是完全的死键；
- 键 `ab` 演示一次按键输出多个字符。

## API

`POST /api/solve`，请求体为键盘机 JSON 加上 `target` 与 `switchCost` 两个字段。

- 成功：`{"ok": true, "solved": true, "keys": [...], "totalCost": n, "keyCount": m, "steps": [...]}`
- 无解：`{"ok": true, "solved": false, "message": "无解：..."}`
- 规格非法：HTTP 400，`{"ok": false, "errors": [...]}`

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
cd app && uvicorn main:app --reload
```
