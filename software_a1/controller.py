"""独立外部程序：HTTP 下发路径，等待每一段真正到达，再发送下一段。"""

import argparse
import json
import math
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from protocol import load_route

ROOT = Path(__file__).resolve().parent


class ControlError(RuntimeError):
    pass


def request_json(base_url: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, allow_nan=False).encode("utf-8") if payload is not None else None
    request = Request(base_url.rstrip("/") + path, data=data,
                      headers={"Content-Type": "application/json"} if data is not None else {})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ControlError(f"HTTP {error.code}: {detail}") from None
    except (URLError, TimeoutError, OSError) as error:
        raise ControlError(f"无法连接服务：{error}") from None


def run_route(base_url: str, path: Path, timeout: float, speed_scale: float, report: dict):
    route = load_route(path)
    route_data = route.model_dump()
    for segment in route_data["segments"]:
        segment["speed"] *= speed_scale
    # 整条修改后的路径再次验证，拒绝溢出 / 非法速度。
    from protocol import Route
    route_data = Route.model_validate(route_data).model_dump()
    deadline = time.monotonic() + timeout
    print("等待三维页面连接，请保持页面在前台……", flush=True)
    while True:
        state = request_json(base_url, "/api/state")
        if state["viewer_ready"] and state["viewer_visible"]:
            break
        if time.monotonic() >= deadline:
            raise ControlError("等待页面超时，请先打开浏览器并保持三维页面在前台。")
        time.sleep(0.2)
    request_json(base_url, "/api/route", route_data)
    report.update(route=route_data, status="running", started_at=time.time())
    run_id = uuid.uuid4().hex[:12]
    for index, segment in enumerate(route_data["segments"], start=1):
        command_id = f"{run_id}-{index:03}"
        response = request_json(base_url, "/api/move", {"type": "move", "command_id": command_id, **segment})
        report["active_command_id"] = command_id
        command = response["command"]
        report["commands"].append(command)
        print(f"[{index}/{len(route_data['segments'])}] 已接收 {command_id}，目标 {segment['target']}，速度 {segment['speed']:.3f} m/s", flush=True)
        start = time.monotonic()
        deadline = start + max(timeout, command["expected_motion_s"] * 2 + 10)
        last_phase = None
        while True:
            current = request_json(base_url, f"/api/commands/{command_id}")
            report["commands"][-1] = current
            phase = current["status"]
            if phase != last_phase and phase == "paused":
                print(f"  已暂停：{current.get('reason') or '等待继续'}", flush=True)
            last_phase = phase
            if phase == "arrived":
                current["controller_wall_elapsed_s"] = time.monotonic() - start
                print(f"  已到达，运动时间 {current['motion_elapsed_s']:.3f}s，理论时间 {current['expected_motion_s']:.3f}s", flush=True)
                break
            if phase in {"cancelled", "error"}:
                raise ControlError(f"命令未完成：{current.get('reason') or phase}")
            if time.monotonic() >= deadline:
                raise ControlError(f"命令 {command_id} 等待到达超时。")
            time.sleep(0.05)
        report["active_command_id"] = None
    report.update(status="completed", final_position=request_json(base_url, "/api/state")["position"])


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="通过 HTTP 控制 Three.js 方块依次经过配置路径。")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--path", type=Path, default=ROOT / "path.example.json")
    parser.add_argument("--timeout", type=float, default=30, help="等待连接 / 每段最短超时秒数；长距离自动延长。")
    parser.add_argument("--speed-scale", type=float, default=1.0, help="所有路段的速度倍率。")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    if not all(math.isfinite(value) and value > 0 for value in (args.timeout, args.speed_scale)):
        parser.error("timeout 和 speed-scale 必须有限且大于零")
    report = {"exercise": "A1", "status": "not_started", "commands": [], "active_command_id": None}
    try:
        run_route(args.url, args.path, args.timeout, args.speed_scale, report)
    except (ControlError, ValueError, OSError, KeyboardInterrupt) as error:
        report.update(status="failed", error=str(error) or "用户中断")
        if report["active_command_id"]:
            try:
                request_json(args.url, "/api/control", {"action": "stop", "command_id": report["active_command_id"]})
            except ControlError:
                pass
        print(f"执行未完成：{report['error']}", file=sys.stderr)
    finally:
        report["finished_at"] = time.time()
        try:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            output = args.output_dir / "last_run.json"
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(f"实际执行记录：{output.resolve()}", flush=True)
        except (OSError, ValueError) as error:
            report.update(status="failed")
            print(f"保存失败：{error}", file=sys.stderr)
    if report["status"] == "completed":
        print("全部路段已到达：PASS", flush=True)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
