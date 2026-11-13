"""针孔相机的像素反投影与投影；深度指相机 Z 坐标，单位米。"""

import math
from dataclasses import dataclass
from collections.abc import Sequence

from .geometry import Matrix, Vector3

Pixel = tuple[float, float]


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float = 800.0
    fy: float = 800.0
    cx: float = 640.0
    cy: float = 360.0
    width: int = 1280
    height: int = 720

    def __post_init__(self):
        if not all(math.isfinite(value) for value in (self.fx, self.fy, self.cx, self.cy)):
            raise ValueError("Camera intrinsics must be finite.")
        if self.fx <= 0 or self.fy <= 0:
            raise ValueError("Camera focal lengths fx and fy must be positive.")
        if any(type(value) is not int or value <= 0 for value in (self.width, self.height)):
            raise ValueError("Image width and height must be positive integers.")

    @property
    def matrix(self) -> Matrix:
        return ((self.fx, 0.0, self.cx), (0.0, self.fy, self.cy), (0.0, 0.0, 1.0))

    def to_dict(self) -> dict:
        return {"fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
                "image_size_px": (self.width, self.height), "matrix": self.matrix,
                "distortion": "ignored as specified in exercise B3"}


def backproject_pixel(pixel: Sequence[float], depth_m: float, intrinsics: CameraIntrinsics) -> Vector3:
    """检测像素必须位于图像内；不裁剪坐标，不添加半像素偏移。"""
    pixel = tuple(float(value) for value in pixel)
    if len(pixel) != 2 or not all(math.isfinite(value) for value in pixel):
        raise ValueError("A pixel must contain two finite numbers (u, v).")
    u, v = pixel
    if not (0 <= u < intrinsics.width and 0 <= v < intrinsics.height):
        raise ValueError("The detected pixel must be inside the image.")
    depth_m = float(depth_m)
    if not math.isfinite(depth_m) or depth_m <= 0:
        raise ValueError("Axial depth Z_c must be finite and positive.")
    return ((u - intrinsics.cx) * depth_m / intrinsics.fx,
            (v - intrinsics.cy) * depth_m / intrinsics.fy, depth_m)


def project_camera_point(point: Sequence[float], intrinsics: CameraIntrinsics) -> Pixel:
    """投影用于回代验证；返回几何像素，不自动裁剪至图像边界。"""
    point = tuple(float(value) for value in point)
    if len(point) != 3 or not all(math.isfinite(value) for value in point):
        raise ValueError("A camera point must contain three finite numbers.")
    x, y, z = point
    if z <= 0:
        raise ValueError("A camera point must have positive Z for projection.")
    return intrinsics.fx * x / z + intrinsics.cx, intrinsics.fy * y / z + intrinsics.cy
