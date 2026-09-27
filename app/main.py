"""FastAPI 入口：提供静态页面与 /api/solve 计算接口。"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from solver import SpecError, solve, validate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="状态键盘试验")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/solve")
async def api_solve(request: Request):
    try:
        spec = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "errors": ["请求体不是合法 JSON"]}, status_code=400
        )

    try:
        machine = validate(spec)
    except SpecError as exc:
        return JSONResponse({"ok": False, "errors": exc.errors}, status_code=400)

    path = solve(machine)
    if path is None:
        return {
            "ok": True,
            "solved": False,
            "message": "无解：不存在输出恰好等于目标文字且结束于终态的按键序列。",
        }

    key_cost = machine["key_cost"]
    steps = []
    cum = 0
    produced = ""
    for i, (kid, frm, to, out, extra) in enumerate(path, 1):
        cum += extra
        produced += out
        steps.append(
            {
                "step": i,
                "key": kid,
                "from": frm,
                "to": to,
                "output": out,
                "keyCost": key_cost[kid],
                "switchCost": extra - key_cost[kid],
                "cumCost": cum,
                "produced": produced,
            }
        )

    return {
        "ok": True,
        "solved": True,
        "keys": [p[0] for p in path],
        "keyCount": len(path),
        "totalCost": cum,
        "steps": steps,
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
