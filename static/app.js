/* 状态键盘试验 —— 原生 JavaScript 前端（无框架、无构建步骤） */
"use strict";

/* ---------------- 死键示例 ----------------
 * base：初态 / 终态。
 * Acute / Circum 是两个死键：按下后不输出任何字符，分别进入 acute / circum 状态；
 *   在死键状态下按元音输出组合字符（é/á、ê/â）并回到 base，
 *   按 Space 输出死键本身的字面符号（´/ˆ），再按一次死键则空输出自循环。
 * Eacute 键可直接输出 é，但成本 8 远高于「Acute + E」；
 * Hi 键一次输出两个字符，演示多字符输出。 */
const EXAMPLE = {
  states: ["base", "acute", "circum"],
  initial: "base",
  finals: ["base"],
  keys: [
    { id: "C", cost: 1 },
    { id: "A", cost: 1 },
    { id: "F", cost: 1 },
    { id: "E", cost: 1 },
    { id: "Space", cost: 1 },
    { id: "Acute", cost: 2 },
    { id: "Circum", cost: 2 },
    { id: "Eacute", cost: 8 },
    { id: "Hi", cost: 2 },
  ],
  transitions: [
    { state: "base", key: "C", output: "c", next: "base" },
    { state: "base", key: "A", output: "a", next: "base" },
    { state: "base", key: "F", output: "f", next: "base" },
    { state: "base", key: "E", output: "e", next: "base" },
    { state: "base", key: "Space", output: " ", next: "base" },
    { state: "base", key: "Hi", output: "hi", next: "base" },
    { state: "base", key: "Eacute", output: "é", next: "base" },
    { state: "base", key: "Acute", output: "", next: "acute" },
    { state: "base", key: "Circum", output: "", next: "circum" },
    { state: "acute", key: "E", output: "é", next: "base" },
    { state: "acute", key: "A", output: "á", next: "base" },
    { state: "acute", key: "Space", output: "´", next: "base" },
    { state: "acute", key: "Acute", output: "", next: "acute" },
    { state: "circum", key: "E", output: "ê", next: "base" },
    { state: "circum", key: "A", output: "â", next: "base" },
    { state: "circum", key: "Space", output: "ˆ", next: "base" },
    { state: "circum", key: "Circum", output: "", next: "circum" },
  ],
};

/* ---------------- DOM ---------------- */
const $ = (id) => document.getElementById(id);
const jsonInput = $("jsonInput");
const targetInput = $("targetInput");
const surchargeInput = $("surchargeInput");
const targetCount = $("targetCount");
const validateMsg = $("validateMsg");
const solveMsg = $("solveMsg");
const machineView = $("machineView");
const resultView = $("resultView");

let lastMachine = null; // 最近一次校验通过的机器（用于渲染）
let lastResult = null; // 最近一次求解结果
let stepIndex = -1; // 播放器当前步（从 0 开始）
let autoTimer = null;

/* ---------------- 工具 ---------------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

// 以 Unicode 码点计数（与 Python len() 一致；正确处理代理对）
function codePointLength(s) {
  let n = 0;
  for (const _ of s) n++; // eslint-disable-line no-unused-vars
  return n;
}

function setMsg(el, text, kind) {
  el.textContent = text;
  el.className = "msg" + (kind ? " " + kind : "");
}

// 输出为空时显示 ε（死键）
function outputHtml(out) {
  if (out === "") return '<span class="dead-mark">ε（空 · 死键）</span>';
  return '<span class="output-cell">' + escapeHtml(out) + "</span>";
}

async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = null;
  try {
    data = await resp.json();
  } catch (_) { /* 忽略非 JSON 响应 */ }
  if (!resp.ok) {
    throw new Error((data && data.error) || `请求失败（HTTP ${resp.status}）`);
  }
  return data;
}

/* ---------------- 键盘定义渲染 ---------------- */
function renderMachine(m) {
  machineView.hidden = false;

  const chips = $("statesView");
  chips.innerHTML = "";
  for (const s of m.states) {
    const span = document.createElement("span");
    const isInit = s === m.initial;
    const isFinal = m.finals.includes(s);
    span.className = "chip " + (isInit && isFinal ? "both" : isInit ? "initial" : isFinal ? "final" : "");
    const tags = [];
    if (isInit) tags.push("初态");
    if (isFinal) tags.push("终态");
    span.textContent = s + (tags.length ? "（" + tags.join("，") + "）" : "");
    chips.appendChild(span);
  }

  const keysBody = $("keysTable").querySelector("tbody");
  keysBody.innerHTML = "";
  for (const k of m.keys) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="seq">${escapeHtml(k.id)}</td><td>${k.cost}</td>`;
    keysBody.appendChild(tr);
  }

  // 直接从 JSON 文本取原始转移，保留定义顺序与原始输出
  let raw;
  try { raw = JSON.parse(jsonInput.value); } catch (_) { raw = m; }
  const trans = raw.transitions || [];
  const body = $("transTable").querySelector("tbody");
  body.innerHTML = "";
  for (const t of trans) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${escapeHtml(t.state)}</td>` +
      `<td class="seq">${escapeHtml(t.key)}</td>` +
      `<td class="wrap">${outputHtml(t.output ?? "")}</td>` +
      `<td>${escapeHtml(t.next)}</td>`;
    body.appendChild(tr);
  }
}

/* ---------------- 求解结果渲染 ---------------- */
function renderSummary(r, target, surcharge) {
  resultView.hidden = false;
  stopAuto();

  if (!r.found) {
    $("foundPane").hidden = true;
    const box = $("noSolutionBox");
    box.hidden = false;
    box.innerHTML =
      "<strong>无解。</strong> " +
      escapeHtml(r.message || "不存在满足条件的按键序列。") +
      `<div style="margin-top:6px;opacity:0.8">搜索中展开节点数：${r.stats.expanded}</div>`;
    return;
  }

  $("noSolutionBox").hidden = true;
  $("foundPane").hidden = false;

  const sol = r.solution;
  $("solutionSummary").innerHTML = `
    <div class="summary-box">
      <div><div class="label">键 ID 序列（${sol.press_count} 次按键）</div>
        <div class="value seq">${sol.key_sequence.length ? sol.key_sequence.map(escapeHtml).join(" → ") : "（零按键）"}</div></div>
      <div><div class="label">总成本</div><div class="value">${sol.total_cost}</div></div>
      <div><div class="label">结束状态</div><div class="value">${escapeHtml(sol.final_state)}</div></div>
      <div><div class="label">输出</div><div class="value output-cell">${escapeHtml(sol.output === "" ? "（空串）" : sol.output)}</div></div>
      <div><div class="label">换键附加成本</div><div class="value">${surcharge}</div></div>
      <div><div class="label">目标码点数</div><div class="value">${codePointLength(target)}</div></div>
    </div>
  `;

  const tbody = $("stepsTable").querySelector("tbody");
  tbody.innerHTML = "";
  r.steps.forEach((st) => {
    const tr = document.createElement("tr");
    tr.dataset.index = st.index;
    const prevKey = st.index >= 2 ? r.steps[st.index - 2].key : "";
    const switchCell = st.switch_cost > 0
      ? `${st.switch_cost}（${escapeHtml(prevKey)}→${escapeHtml(st.key)}）`
      : "0";
    tr.innerHTML =
      `<td>${st.index}</td>` +
      `<td class="seq">${escapeHtml(st.key)}</td>` +
      `<td>${escapeHtml(st.from_state)} → ${escapeHtml(st.to_state)}</td>` +
      `<td class="wrap">${outputHtml(st.output)}</td>` +
      `<td>${st.key_cost}</td>` +
      `<td>${switchCell}</td>` +
      `<td>${st.step_cost}</td>` +
      `<td>${st.cumulative_cost}</td>`;
    tbody.appendChild(tr);
  });

  $("statsLine").textContent =
    `搜索中展开节点数：${r.stats.expanded}（Dijkstra 按 总成本 → 按键数 → 键 ID 字典序 出队，首个终态节点即最优解；空输出循环因成本恒增不会卡住）。`;

  // 零按键解（空目标且初态即终态）：禁用播放器
  const hasSteps = r.steps.length > 0;
  $("player").style.opacity = hasSteps ? "" : "0.55";
  for (const id of ["firstBtn", "prevBtn", "nextBtn", "lastBtn", "autoBtn"]) {
    $(id).disabled = !hasSteps;
  }
  if (hasSteps) {
    showStep(0);
  } else {
    stepIndex = -1;
    $("stepIndicator").textContent = "零按键（空目标，初态即终态）";
    $("stepDetail").innerHTML = "";
    $("progressBar").innerHTML = `<span class="todo">${escapeHtml("（空目标）")}</span>`;
  }
}

function showStep(i) {
  const steps = lastResult.steps;
  if (!steps.length) return;
  stepIndex = Math.max(0, Math.min(steps.length - 1, i));
  const st = steps[stepIndex];
  const target = lastResult.solution.output;

  $("stepIndicator").textContent = `第 ${stepIndex + 1} / ${steps.length} 步`;

  const cells = [
    ["按下的键", st.key],
    ["状态迁移", `${st.from_state} → ${st.to_state}`],
    ["本步输出", st.output === "" ? "ε（空）" : st.output],
    ["输出码点数", st.output_length],
    ["键成本", st.key_cost],
    ["换键附加", st.switch_cost],
    ["本步成本", st.step_cost],
    ["累计成本", st.cumulative_cost],
  ];
  $("stepDetail").innerHTML = cells
    .map(([label, value]) =>
      `<div class="cell"><div class="label">${label}</div><div class="value">${escapeHtml(String(value))}</div></div>`)
    .join("");

  // 输出进度：按原始码点着色，不做任何转换
  const done = st.matched_prefix;
  const rest = target.slice(codePointLength(done));
  $("progressBar").innerHTML =
    `<span class="done">${escapeHtml(done)}</span><span class="todo">${escapeHtml(rest)}</span>`;

  document.querySelectorAll("#stepsTable tbody tr").forEach((tr) => {
    tr.classList.toggle("current", Number(tr.dataset.index) === stepIndex + 1);
  });

  // 自动播放到末尾时停下
  if (stepIndex === steps.length - 1) stopAuto();
}

function toggleAuto() {
  if (autoTimer) { stopAuto(); return; }
  $("autoBtn").textContent = "⏸ 暂停";
  if (stepIndex === lastResult.steps.length - 1) showStep(0);
  autoTimer = setInterval(() => {
    if (stepIndex >= lastResult.steps.length - 1) { stopAuto(); return; }
    showStep(stepIndex + 1);
  }, 900);
}
function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  const btn = $("autoBtn");
  if (btn) btn.textContent = "▶ 自动播放";
}

/* ---------------- 播放器按钮（静态元素，只绑定一次） ---------------- */
$("firstBtn").addEventListener("click", () => showStep(0));
$("prevBtn").addEventListener("click", () => showStep(stepIndex - 1));
$("nextBtn").addEventListener("click", () => showStep(stepIndex + 1));
$("lastBtn").addEventListener("click", () => showStep(lastResult.steps.length - 1));
$("autoBtn").addEventListener("click", toggleAuto);

/* ---------------- 事件 ---------------- */
$("loadExampleBtn").addEventListener("click", () => {
  jsonInput.value = JSON.stringify(EXAMPLE, null, 2);
  targetInput.value = "café";
  surchargeInput.value = 2;
  updateTargetCount();
  machineView.hidden = true;
  resultView.hidden = true;
  setMsg(validateMsg, "已载入死键示例，点击“校验定义”或直接“寻找最优按键序列”。", "ok");
});

$("validateBtn").addEventListener("click", async () => {
  let parsed;
  try {
    parsed = JSON.parse(jsonInput.value);
  } catch (e) {
    setMsg(validateMsg, "JSON 解析失败：" + e.message, "err");
    return;
  }
  try {
    const data = await postJson("/api/validate", parsed);
    lastMachine = data.summary;
    setMsg(validateMsg, `校验通过：${data.summary.states.length} 个状态、${data.summary.keys.length} 个键、${data.summary.transition_count} 条转移。`, "ok");
    renderMachine(data.summary);
  } catch (e) {
    machineView.hidden = true;
    setMsg(validateMsg, e.message, "err");
  }
});

$("solveBtn").addEventListener("click", async () => {
  stopAuto();
  let parsed;
  try {
    parsed = JSON.parse(jsonInput.value);
  } catch (e) {
    setMsg(solveMsg, "JSON 解析失败：" + e.message, "err");
    return;
  }
  const target = targetInput.value;
  if (codePointLength(target) > 100) {
    setMsg(solveMsg, "目标文字超过 100 个 Unicode 码点。", "err");
    return;
  }
  const surcharge = Number(surchargeInput.value);
  if (!Number.isInteger(surcharge) || surcharge < 0 || surcharge > 100) {
    setMsg(solveMsg, "换键附加成本必须是 0～100 的整数。", "err");
    return;
  }
  setMsg(solveMsg, "计算中…", "");
  try {
    const data = await postJson("/api/solve", { ...parsed, target, surcharge });
    // 顺手刷新机器视图（solve 内部已做完整校验）
    if (!lastMachine) renderMachineFromPayload(parsed);
    lastResult = data;
    if (data.found) {
      const s = data.solution;
      setMsg(solveMsg,
        `找到最优解：${s.press_count} 次按键，总成本 ${s.total_cost}，结束于终态 ${s.final_state}。`, "ok");
    } else {
      setMsg(solveMsg, "无解：" + (data.message || ""), "err");
    }
    renderSummary(data, target, surcharge);
  } catch (e) {
    resultView.hidden = true;
    setMsg(solveMsg, e.message, "err");
  }
});

// 若没先点“校验”，用本地规范化的最小摘要渲染机器视图
function renderMachineFromPayload(raw) {
  const m = {
    states: raw.states,
    initial: raw.initial,
    finals: raw.finals,
    keys: raw.keys,
    transitions: raw.transitions,
  };
  lastMachine = m;
  renderMachine(m);
}

function updateTargetCount() {
  const n = codePointLength(targetInput.value);
  targetCount.textContent = `${n} / 100 码点`;
  targetCount.style.color = n > 100 ? "var(--error)" : "";
}
targetInput.addEventListener("input", updateTargetCount);

/* ---------------- 初始化 ---------------- */
jsonInput.value = JSON.stringify(EXAMPLE, null, 2);
targetInput.value = "café";
updateTargetCount();
