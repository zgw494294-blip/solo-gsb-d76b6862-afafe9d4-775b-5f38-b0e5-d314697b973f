"""状态键盘试验 —— FastAPI 后端。

接口：
  GET  /              单页试验台（原生 JavaScript，无构建步骤）
  POST /api/validate  仅校验导入的键盘 JSON
  POST /api/solve     计算最优按键序列
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .solver import MachineError, solve, validate_machine

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="状态键盘试验", version="1.0.0")


def _extract_machine(body: dict) -> dict:
    """请求体既可以直接是键盘定义，也可以包一层 {"machine": ...}。"""
    if not isinstance(body, dict):
        raise MachineError("请求体必须是 JSON 对象")
    if "machine" in body:
        return validate_machine(body["machine"])
    return validate_machine(body)


@app.exception_handler(MachineError)
async def machine_error_handler(_request: Request, exc: MachineError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/validate")
async def api_validate(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": f"JSON 解析失败：{exc.msg}"}
        )
    machine = _extract_machine(body)
    return JSONResponse(
        content={
            "ok": True,
            "message": "键盘定义有效。",
            "summary": {
                "states": machine["states"],
                "initial": machine["initial"],
                "finals": machine["finals"],
                "keys": [{"id": k["id"], "cost": k["cost"]} for k in machine["keys"]],
                "transition_count": len(machine["transitions"]),
            },
        }
    )


@app.post("/api/solve")
async def api_solve(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": f"JSON 解析失败：{exc.msg}"}
        )
    if not isinstance(body, dict):
        raise MachineError("请求体必须是 JSON 对象")

    machine = _extract_machine(body)
    target = body.get("target", "")
    surcharge = body.get("surcharge", 0)
    if not isinstance(target, str):
        raise MachineError("target（目标文字）必须是字符串")
    if isinstance(surcharge, bool) or not isinstance(surcharge, int):
        raise MachineError("surcharge（换键附加成本）必须是 0～100 的整数")

    result = solve(machine, target, surcharge)
    return JSONResponse(content={"ok": True, **result})


# 静态资源（index.html / app.js / styles.css）挂在根路径，放在最后避免覆盖 API
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
