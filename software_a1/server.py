"""A1: relay external HTTP commands to one Three.js viewer via WebSocket."""

import argparse
import asyncio
import math
import sys
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from protocol import ControlRequest, MoveRequest, Point, Ready, Route, Telemetry, Visibility, load_route

ROOT = Path(__file__).resolve().parent
TERMINAL_PHASES = {"arrived", "cancelled", "error"}


class Hub:
    """单进程、单显示页面；位置由页面计算，服务保存最近确认的状态。"""

    def __init__(self):
        self.route = load_route(ROOT / "path.example.json")
        self.position = self.route.initial_position
        self.viewer: WebSocket | None = None
        self.ready = False
        self.visible = False
        self.phase = "offline"
        self.commands: OrderedDict[str, dict] = OrderedDict()
        self.active_id: str | None = None
        self.lock = asyncio.Lock()

    def state(self) -> dict:
        last = next(reversed(self.commands.values()), None) if self.commands else None
        return {"viewer_connected": self.viewer is not None, "viewer_ready": self.ready,
                "viewer_visible": self.visible, "phase": self.phase,
                "position": self.position.model_dump(), "active_command_id": self.active_id,
                "last_command": last, "route": self.route.model_dump()}

    def require_viewer(self):
        if self.viewer is None or not self.ready:
            raise HTTPException(409, "请先打开三维页面，等待显示已连接。")

    async def send(self, message: dict):
        self.require_viewer()
        try:
            await self.viewer.send_json(message)
        except (WebSocketDisconnect, RuntimeError, OSError):
            self.disconnected()
            raise HTTPException(409, "三维页面连接已断开。") from None

    def disconnected(self):
        if self.active_id:
            command = self.commands[self.active_id]
            command.update(status="cancelled", reason="显示页面已断开，运动未完成。", finished_at=time.time())
        self.active_id = None
        self.viewer, self.ready, self.visible, self.phase = None, False, False, "offline"

    def telemetry(self, event: Telemetry):
        # 旧连接或旧命令的回执不能影响新的运动。
        if event.command_id != self.active_id:
            return
        command = self.commands[event.command_id]
        if event.elapsed_s + 1e-9 < command["motion_elapsed_s"]:
            raise ValueError("运动时间不能倒退。")
        if event.phase == "arrived" and math.dist(event.position.values(), command["target"].values()) > 1e-6:
            raise ValueError("到达回执的位置与目标不一致。")
        self.position = event.position
        command.update(status=event.phase, position=event.position.model_dump(),
                       motion_elapsed_s=event.elapsed_s, reason=event.reason)
        self.phase = event.phase
        if event.phase in TERMINAL_PHASES:
            command["finished_at"] = time.time()
            self.active_id = None


def create_app() -> FastAPI:
    app = FastAPI(title="A1 三维轨迹控制台", docs_url=None, redoc_url=None)
    hub = Hub()
    app.state.hub = hub
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, error):
        # 不回显 NaN / Infinity 输入，确保错误响应本身仍是合法 JSON。
        details = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/api/state")
    async def state():
        async with hub.lock:
            return hub.state()

    @app.get("/api/commands/{command_id}")
    async def command_state(command_id: str):
        async with hub.lock:
            if command_id not in hub.commands:
                raise HTTPException(404, "命令不存在或已超出历史保留范围。")
            return hub.commands[command_id]

    @app.get("/api/route/example")
    async def example_route():
        return FileResponse(ROOT / "path.example.json", media_type="application/json", filename="path.example.json")

    @app.post("/api/route")
    async def set_route(route: Route):
        async with hub.lock:
            hub.require_viewer()
            if hub.active_id:
                raise HTTPException(409, "运动尚未结束，请先停止或等待到达。")
            hub.route, hub.position, hub.phase = route, route.initial_position, "idle"
            await hub.send({"type": "route", "route": route.model_dump()})
            return {"status": "accepted", "segments": len(route.segments)}

    @app.post("/api/move", status_code=202)
    async def move(request: MoveRequest):
        async with hub.lock:
            if request.command_id in hub.commands:
                previous = hub.commands[request.command_id]
                if previous["target"] != request.target.model_dump() or previous["speed"] != request.speed:
                    raise HTTPException(409, "相同命令编号不能使用不同目标或速度。")
                return {"status": "accepted", "command": previous, "duplicate": True}
            hub.require_viewer()
            if not hub.visible:
                raise HTTPException(409, "请将三维页面切换到前台后再开始。")
            if hub.active_id:
                raise HTTPException(409, "上一段尚未完成，请等待到达回执。")
            distance = math.dist(hub.position.values(), request.target.values())
            if not math.isfinite(distance) or not math.isfinite(distance / request.speed):
                raise HTTPException(422, "目标距离或运动时间超出了有限数值范围。")
            command = {"command_id": request.command_id, "target": request.target.model_dump(),
                       "speed": request.speed, "start": hub.position.model_dump(),
                       "position": hub.position.model_dump(), "status": "accepted",
                       "distance_m": distance, "expected_motion_s": distance / request.speed,
                       "motion_elapsed_s": 0.0, "accepted_at": time.time(), "reason": ""}
            hub.commands[request.command_id] = command
            while len(hub.commands) > 256:
                hub.commands.popitem(last=False)
            hub.active_id, hub.phase = request.command_id, "moving"
            await hub.send({"type": "move", "command": command})
            return {"status": "accepted", "command": command, "duplicate": False}

    @app.post("/api/control", status_code=202)
    async def control(request: ControlRequest):
        async with hub.lock:
            hub.require_viewer()
            if not hub.active_id:
                raise HTTPException(409, "当前没有正在执行的运动。")
            if request.command_id is not None and request.command_id != hub.active_id:
                raise HTTPException(409, "该命令已结束，不能操作另一条命令。")
            await hub.send({"type": "control", "action": request.action})
            return {"status": "accepted", "action": request.action}

    @app.websocket("/ws")
    async def viewer(websocket: WebSocket):
        await websocket.accept()
        async with hub.lock:
            if hub.viewer is not None:
                await websocket.send_json({"type": "error", "message": "已有一个显示页面连接，请关闭原页面后刷新。"})
                await websocket.close(code=4009)
                return
            hub.viewer, hub.phase = websocket, "idle"
            await websocket.send_json({"type": "hello", "state": hub.state()})
        try:
            while True:
                message = await websocket.receive_json()
                async with hub.lock:
                    if hub.viewer is not websocket:
                        break
                    try:
                        if not isinstance(message, dict):
                            raise ValueError("消息必须是 JSON 对象。")
                        if message.get("type") == "ready":
                            event = Ready.model_validate(message)
                            hub.ready, hub.visible = True, event.visible
                            await websocket.send_json({"type": "ready", "state": hub.state()})
                        elif message.get("type") == "visibility":
                            hub.visible = Visibility.model_validate(message).visible
                        elif message.get("type") == "telemetry":
                            hub.telemetry(Telemetry.model_validate(message))
                        else:
                            raise ValueError("未知的消息类型。")
                    except (ValueError, ValidationError) as error:
                        await websocket.send_json({"type": "error", "message": str(error)[:200]})
        except (WebSocketDisconnect, OSError, RuntimeError, ValueError):
            pass
        finally:
            async with hub.lock:
                if hub.viewer is websocket:
                    hub.disconnected()

    return app


app = create_app()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="启动 A1 本地三维服务。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port 必须在 1 到 65535 之间")
    import uvicorn
    # 状态保存在当前进程；保持单 worker，便于解释和复现。
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
