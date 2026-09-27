/* 状态键盘试验 —— 原生 JavaScript 前端 */

"use strict";

// 含死键的示例：
// - 键 "'" 是经典死键（dead key）：本身不输出，只把状态切到 accent，
//   随后按 a/e 才输出带重音符的 á/é；
// - 键 "x" 没有任何转移，是完全的死键，按下无效；
// - 键 "ab" 演示一次输出多个字符。
const EXAMPLE_SPEC = {
  states: ["q0", "accent"],
  initial: "q0",
  finals: ["q0"],
  keys: [
    { id: "a", cost: 1 },
    { id: "e", cost: 1 },
    { id: "'", cost: 1 },
    { id: "ab", cost: 3 },
    { id: "x", cost: 9 }
  ],
  transitions: [
    { state: "q0", key: "a", output: "a", next: "q0" },
    { state: "q0", key: "e", output: "e", next: "q0" },
    { state: "q0", key: "'", output: "", next: "accent" },
    { state: "q0", key: "ab", output: "ab", next: "q0" },
    { state: "accent", key: "a", output: "á", next: "q0" },
    { state: "accent", key: "e", output: "é", next: "q0" }
  ]
};
const EXAMPLE_TARGET = "áé";
const EXAMPLE_SWITCH = 1;

const $ = (id) => document.getElementById(id);

const specEl = $("spec");
const targetEl = $("target");
const switchEl = $("switch-cost");
const counterEl = $("target-counter");

let currentSteps = [];   // 当前解的步骤
let shown = 0;       // 已展示到第几步
let playTimer = null;

/* ---------- 工具 ---------- */

function codePoints(str) {
  return Array.from(str).length;
}

function updateCounter() {
  const n = codePoints(targetEl.value);
  counterEl.textContent = `${n} 码点`;
  counterEl.classList.toggle("over", n > 100);
}

function showErrors(errors) {
  const box = $("errors");
  box.hidden = false;
  box.replaceChildren();
  const title = document.createElement("p");
  title.className = "errors-title";
  title.textContent = "输入有误：";
  box.appendChild(title);
  const ul = document.createElement("ul");
  for (const e of errors) {
    const li = document.createElement("li");
    li.textContent = e;
    ul.appendChild(li);
  }
  box.appendChild(ul);
}

function resetResult() {
  stopPlay();
  $("result-panel").hidden = false;
  $("errors").hidden = true;
  $("no-solution").hidden = true;
  $("summary").hidden = true;
  $("playback").hidden = true;
  $("steps-body").replaceChildren();
  $("status-line").textContent = "";
  currentSteps = [];
  shown = 0;
}

/* ---------- 逐步展示 ---------- */

function buildRow(step) {
  const tr = document.createElement("tr");
  const cells = [
    step.step,
    step.key,
    `${step.from} → ${step.to}`,
    step.output === "" ? "（空）" : step.output,
    step.keyCost,
    step.switchCost,
    step.cumCost,
    step.produced
  ];
  for (const c of cells) {
    const td = document.createElement("td");
    td.textContent = String(c);
    tr.appendChild(td);
  }
  return tr;
}

function showUpTo(n) {
  shown = Math.max(0, Math.min(n, currentSteps.length));
  const body = $("steps-body");
  body.replaceChildren();
  for (let i = 0; i < shown; i++) {
    body.appendChild(buildRow(currentSteps[i]));
  }
  const line = $("status-line");
  if (shown === 0) {
    line.textContent = currentSteps.length === 0
      ? "目标为空且初态即终态：无需按键，总成本 0。"
      : "尚未按键。";
  } else {
    const s = currentSteps[shown - 1];
    line.textContent =
      `第 ${shown}/${currentSteps.length} 步：按下「${s.key}」，` +
      `状态 ${s.from} → ${s.to}，输出 ${s.output === "" ? "（空）" : `「${s.output}」`}，` +
      `累计成本 ${s.cumCost}，已产出「${s.produced}」。`;
  }
  $("btn-prev").disabled = shown === 0;
  $("btn-next").disabled = shown >= currentSteps.length;
}

function stopPlay() {
  if (playTimer !== null) {
    clearInterval(playTimer);
    playTimer = null;
    $("btn-play").textContent = "自动播放";
  }
}

function togglePlay() {
  if (playTimer !== null) {
    stopPlay();
    return;
  }
  if (shown >= currentSteps.length) showUpTo(0);
  $("btn-play").textContent = "暂停";
  playTimer = setInterval(() => {
    if (shown >= currentSteps.length) {
      stopPlay();
      return;
    }
    showUpTo(shown + 1);
  }, 700);
}

/* ---------- 求解 ---------- */

async function doSolve() {
  resetResult();

  // 客户端预检
  const clientErrors = [];
  let spec;
  try {
    spec = JSON.parse(specEl.value);
  } catch (e) {
    clientErrors.push(`JSON 解析失败：${e.message}`);
  }
  const target = targetEl.value;
  if (codePoints(target) > 100) {
    clientErrors.push("目标文字超过 100 个 Unicode 码点");
  }
  const switchCost = Number(switchEl.value);
  if (!Number.isInteger(switchCost) || switchCost < 0 || switchCost > 100) {
    clientErrors.push("换键附加成本必须是 0～100 的整数");
  }
  if (clientErrors.length > 0) {
    showErrors(clientErrors);
    return;
  }

  let resp, data;
  try {
    resp = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...spec, target, switchCost })
    });
    data = await resp.json();
  } catch (e) {
    showErrors([`请求失败：${e.message}`]);
    return;
  }

  if (!data.ok) {
    showErrors(data.errors || ["未知错误"]);
    return;
  }

  if (!data.solved) {
    const box = $("no-solution");
    box.hidden = false;
    box.textContent = data.message;
    return;
  }

  // 汇总信息
  const summary = $("summary");
  summary.hidden = false;
  summary.replaceChildren();
  const seq = data.keys.length > 0 ? data.keys.join(" → ") : "（空序列）";
  summary.textContent =
    `最优解：按键序列 ${seq} ｜ 总成本 ${data.totalCost} ｜ 按键数 ${data.keyCount}`;

  // 逐步展示
  currentSteps = data.steps;
  $("playback").hidden = false;
  showUpTo(data.steps.length === 0 ? 0 : 1);
}

/* ---------- 事件绑定 ---------- */

$("btn-example").addEventListener("click", () => {
  specEl.value = JSON.stringify(EXAMPLE_SPEC, null, 2);
  targetEl.value = EXAMPLE_TARGET;
  switchEl.value = EXAMPLE_SWITCH;
  updateCounter();
});

$("btn-format").addEventListener("click", () => {
  try {
    specEl.value = JSON.stringify(JSON.parse(specEl.value), null, 2);
  } catch (e) {
    resetResult();
    showErrors([`JSON 解析失败：${e.message}`]);
  }
});

$("btn-solve").addEventListener("click", doSolve);
$("btn-prev").addEventListener("click", () => { stopPlay(); showUpTo(shown - 1); });
$("btn-next").addEventListener("click", () => { stopPlay(); showUpTo(shown + 1); });
$("btn-all").addEventListener("click", () => { stopPlay(); showUpTo(currentSteps.length); });
$("btn-reset").addEventListener("click", () => { stopPlay(); showUpTo(0); });
$("btn-play").addEventListener("click", togglePlay);
targetEl.addEventListener("input", updateCounter);

// 初始载入示例，方便直接试验
specEl.value = JSON.stringify(EXAMPLE_SPEC, null, 2);
targetEl.value = EXAMPLE_TARGET;
switchEl.value = EXAMPLE_SWITCH;
updateCounter();
