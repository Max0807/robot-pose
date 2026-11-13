"""HTTP / WebSocket 共用的数据约定；坐标 m，速度 m/s。"""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveNumber = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
CommandId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{1,80}$")]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(Message):
    x: Number
    y: Number
    z: Number

    def values(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


class Segment(Message):
    target: Point
    speed: PositiveNumber


class Route(Message):
    name: str = Field(min_length=1, max_length=80)
    initial_position: Point
    segments: list[Segment] = Field(min_length=1, max_length=1000)


class MoveRequest(Segment):
    type: Literal["move"] = "move"
    command_id: CommandId


class ControlRequest(Message):
    action: Literal["pause", "resume", "stop"]
    command_id: CommandId | None = None


class Ready(Message):
    type: Literal["ready"]
    visible: bool = Field(strict=True)


class Visibility(Message):
    type: Literal["visibility"]
    visible: bool = Field(strict=True)


class Telemetry(Message):
    type: Literal["telemetry"]
    command_id: CommandId
    phase: Literal["moving", "paused", "arrived", "cancelled", "error"]
    position: Point
    elapsed_s: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
    reason: str = Field(default="", max_length=200)


def load_route(path: Path) -> Route:
    """在发送任何命令前检查整条路径，避免执行一半才发现配置无效。"""
    return Route.model_validate(json.loads(path.read_text(encoding="utf-8")))
