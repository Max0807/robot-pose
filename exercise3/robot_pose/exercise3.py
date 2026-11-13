"""第3题：像素 / Z 深度 -> 相机系 -> 基座系 -> 抓取法兰位姿。

反投影是公共的输入转换；相机外参和工具反解分别用矩阵与四元数独立计算。
圆盘法向已知竖直向下，偏航角由抓取约定选择，不从像素中估计。
"""

import math
from dataclasses import dataclass
from collections.abc import Sequence

from .camera import CameraIntrinsics, Pixel, backproject_pixel, project_camera_point
from .geometry import (
    Matrix, Quaternion, Vector3, canonical_quaternion, degrees, make_transform,
    matmul, matvec, matrix_to_quaternion, matrix_to_rpy, max_abs_difference,
    quaternion_distance, quaternion_inverse, quaternion_multiply, quaternion_rotate,
    quaternion_to_matrix, radians, rigid_inverse, rpy_to_matrix, rpy_to_quaternion,
    split_transform,
)

TOLERANCE = 1e-9
POSE_LABELS = (
    ("object_in_base", "选定姿态后的工件位姿 T_B_O"),
    ("target_flange_in_base", "抓取法兰目标 T_B_F"),
    ("reconstructed_gripper_in_base", "回代的夹持中心位姿 T_B_G"),
)


@dataclass(frozen=True)
class Exercise3Input:
    intrinsics: CameraIntrinsics = CameraIntrinsics()
    pixel: Pixel = (720.0, 280.0)
    depth_m: float = 0.400
    camera_translation: Vector3 = (0.700, -0.200, 1.000)
    camera_rpy: Vector3 = radians((180.0, 0.0, 15.0))
    gripper_translation: Vector3 = (0.0, 0.0, 0.165)
    gripper_rpy: Vector3 = radians((0.0, 0.0, 45.0))
    # 圆盘绕竖直轴朝向无约束；本题默认选择 0，单位仍为弧度。
    object_yaw: float = 0.0

    @property
    def object_rpy(self) -> Vector3:
        return math.pi, 0.0, self.object_yaw


@dataclass(frozen=True)
class PoseSolution:
    translation: Vector3
    rotation: Matrix
    rpy: Vector3
    quaternion: Quaternion

    @classmethod
    def from_matrix(cls, transform: Matrix):
        rotation, translation = split_transform(transform)
        return cls(translation, rotation, matrix_to_rpy(rotation), matrix_to_quaternion(rotation))

    @classmethod
    def from_quaternion(cls, quaternion: Quaternion, translation: Vector3):
        quaternion = canonical_quaternion(quaternion)
        rotation = quaternion_to_matrix(quaternion)
        return cls(translation, rotation, matrix_to_rpy(rotation), quaternion)

    @property
    def transform(self) -> Matrix:
        return make_transform(self.rotation, self.translation)

    def to_dict(self) -> dict:
        return {"translation_m": self.translation, "rotation_matrix": self.rotation,
                "rpy_rad": self.rpy, "rpy_deg": degrees(self.rpy),
                "quaternion_xyzw": self.quaternion, "transform_matrix": self.transform}


@dataclass(frozen=True)
class PathSolution:
    camera_point: Vector3
    base_point: Vector3
    camera_optical_axis_in_base: Vector3
    object_normal_in_base: Vector3
    object_in_base: PoseSolution
    target_flange_in_base: PoseSolution
    reconstructed_gripper_in_base: PoseSolution
    recovered_camera_point: Vector3
    reprojected_pixel: Pixel

    def to_dict(self) -> dict:
        result = {"camera_point_m": self.camera_point, "base_point_m": self.base_point,
                  "camera_optical_axis_in_base": self.camera_optical_axis_in_base,
                  "object_normal_in_base": self.object_normal_in_base,
                  "recovered_camera_point_m": self.recovered_camera_point,
                  "reprojected_pixel_uv": self.reprojected_pixel,
                  "reprojected_depth_m": self.recovered_camera_point[2]}
        result.update({name: getattr(self, name).to_dict() for name, _ in POSE_LABELS})
        return result


@dataclass(frozen=True)
class Exercise3Result:
    inputs: Exercise3Input
    matrix_path: PathSolution
    quaternion_path: PathSolution
    errors: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(math.isfinite(value) and value < TOLERANCE for value in self.errors.values())

    def to_dict(self) -> dict:
        return {
            "exercise": "B3",
            "convention": {"transform": "T_A_B maps coordinates from B to A",
                           "rotation": "Rz(rz) @ Ry(ry) @ Rx(rx)",
                           "translation_unit": "m", "internal_angle_unit": "rad",
                           "quaternion_order": "xyzw", "depth": "axial Z in camera frame",
                           "eye_to_hand": "fixed camera extrinsics; no current robot pose required",
                           "grasp": "T_G_O = identity at grasp; centers and orientations coincide",
                           "orientation": "vertical downward object +Z; yaw is selected, not observed"},
            "inputs": {
                "intrinsics": self.inputs.intrinsics.to_dict(),
                "detection": {"pixel_uv": self.inputs.pixel, "depth_z_m": self.inputs.depth_m},
                "camera_in_base": {"translation_m": self.inputs.camera_translation,
                                   "rpy_rad": self.inputs.camera_rpy,
                                   "rpy_deg": degrees(self.inputs.camera_rpy)},
                "gripper_in_flange": {"translation_m": self.inputs.gripper_translation,
                                      "rpy_rad": self.inputs.gripper_rpy,
                                      "rpy_deg": degrees(self.inputs.gripper_rpy)},
                "selected_object_rpy_rad": self.inputs.object_rpy,
                "selected_object_rpy_deg": degrees(self.inputs.object_rpy),
            },
            "matrix_path": self.matrix_path.to_dict(),
            "quaternion_path": self.quaternion_path.to_dict(),
            "validation": {"tolerance": TOLERANCE, "errors": self.errors, "passed": self.passed},
        }


def solve_matrix_path(inputs: Exercise3Input) -> PathSolution:
    camera_point = backproject_pixel(inputs.pixel, inputs.depth_m, inputs.intrinsics)
    camera_rotation = rpy_to_matrix(inputs.camera_rpy)
    base_camera = make_transform(camera_rotation, inputs.camera_translation)
    # 圆心是点，齐次坐标 w=1，使平移生效。
    base_point = matvec(base_camera, camera_point + (1.0,))[:3]
    object_rotation = rpy_to_matrix(inputs.object_rpy)
    base_object = make_transform(object_rotation, base_point)
    flange_gripper = make_transform(rpy_to_matrix(inputs.gripper_rpy), inputs.gripper_translation)
    target_flange = matmul(base_object, rigid_inverse(flange_gripper))
    reconstructed_gripper = matmul(target_flange, flange_gripper)
    recovered_camera_point = matvec(rigid_inverse(base_camera), base_point + (1.0,))[:3]
    # 光轴和法向是方向，只乘旋转，不能加平移。
    optical_axis = matvec(camera_rotation, (0.0, 0.0, 1.0))
    object_normal = matvec(object_rotation, (0.0, 0.0, 1.0))
    return PathSolution(
        camera_point, base_point, optical_axis, object_normal,
        PoseSolution.from_matrix(base_object), PoseSolution.from_matrix(target_flange),
        PoseSolution.from_matrix(reconstructed_gripper), recovered_camera_point,
        project_camera_point(recovered_camera_point, inputs.intrinsics),
    )


def _vector3(values: Sequence[float]) -> Vector3:
    result = tuple(float(value) for value in values)
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        raise ValueError("A translation must contain three finite numbers.")
    return result


def solve_quaternion_path(inputs: Exercise3Input) -> PathSolution:
    camera_point = backproject_pixel(inputs.pixel, inputs.depth_m, inputs.intrinsics)
    camera_translation = _vector3(inputs.camera_translation)
    gripper_translation = _vector3(inputs.gripper_translation)
    camera_q = rpy_to_quaternion(inputs.camera_rpy)
    rotated_point = quaternion_rotate(camera_q, camera_point)
    base_point = tuple(a + b for a, b in zip(camera_translation, rotated_point))
    object_q = rpy_to_quaternion(inputs.object_rpy)
    gripper_q = rpy_to_quaternion(inputs.gripper_rpy)
    target_flange_q = canonical_quaternion(quaternion_multiply(object_q, quaternion_inverse(gripper_q)))
    offset_in_base = quaternion_rotate(target_flange_q, gripper_translation)
    target_flange_translation = tuple(a - b for a, b in zip(base_point, offset_in_base))
    reconstructed_q = quaternion_multiply(target_flange_q, gripper_q)
    reconstructed_translation = tuple(a + b for a, b in zip(target_flange_translation, offset_in_base))
    camera_offset = tuple(a - b for a, b in zip(base_point, camera_translation))
    recovered_camera_point = quaternion_rotate(quaternion_inverse(camera_q), camera_offset)
    optical_axis = quaternion_rotate(camera_q, (0.0, 0.0, 1.0))
    object_normal = quaternion_rotate(object_q, (0.0, 0.0, 1.0))
    # 至此求解结束；仅为输出和比较，将四元数转换为矩阵 / RPY。
    return PathSolution(
        camera_point, base_point, optical_axis, object_normal,
        PoseSolution.from_quaternion(object_q, base_point),
        PoseSolution.from_quaternion(target_flange_q, target_flange_translation),
        PoseSolution.from_quaternion(reconstructed_q, reconstructed_translation),
        recovered_camera_point, project_camera_point(recovered_camera_point, inputs.intrinsics),
    )


def _vector_error(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Vectors must have the same nonzero dimension.")
    return max(abs(a - b) for a, b in zip(left, right))


def solve_exercise3(inputs: Exercise3Input | None = None) -> Exercise3Result:
    inputs = inputs if inputs is not None else Exercise3Input()
    matrix_path = solve_matrix_path(inputs)
    quaternion_path = solve_quaternion_path(inputs)
    errors = {
        "paths_camera_point_max_abs_m": _vector_error(matrix_path.camera_point, quaternion_path.camera_point),
        "paths_base_point_max_abs_m": _vector_error(matrix_path.base_point, quaternion_path.base_point),
        "paths_camera_optical_axis_max_abs": _vector_error(
            matrix_path.camera_optical_axis_in_base, quaternion_path.camera_optical_axis_in_base),
        "paths_object_normal_max_abs": _vector_error(
            matrix_path.object_normal_in_base, quaternion_path.object_normal_in_base),
    }
    for stage, _ in POSE_LABELS:
        first, second = getattr(matrix_path, stage), getattr(quaternion_path, stage)
        errors.update({
            f"paths_{stage}_translation_max_abs_m": _vector_error(first.translation, second.translation),
            f"paths_{stage}_rotation_max_abs": max_abs_difference(first.rotation, second.rotation),
            f"paths_{stage}_quaternion_sign_invariant_l2": quaternion_distance(first.quaternion, second.quaternion),
        })
    errors["input_backprojection_reprojection_max_abs_px"] = _vector_error(
        project_camera_point(matrix_path.camera_point, inputs.intrinsics), inputs.pixel
    )
    flange_gripper = make_transform(rpy_to_matrix(inputs.gripper_rpy), inputs.gripper_translation)
    for name, solution in (("matrix", matrix_path), ("quaternion", quaternion_path)):
        # 再从最终法兰结果回代，避免只相信求解器保存的回代值。
        rotation, translation = split_transform(matmul(solution.target_flange_in_base.transform, flange_gripper))
        errors.update({
            f"{name}_camera_inverse_max_abs_m": _vector_error(solution.recovered_camera_point, solution.camera_point),
            f"{name}_reprojection_max_abs_px": _vector_error(solution.reprojected_pixel, inputs.pixel),
            f"{name}_reprojection_depth_abs_m": abs(solution.recovered_camera_point[2] - inputs.depth_m),
            f"{name}_grasp_center_max_abs_m": _vector_error(
                translation, solution.base_point),
            f"{name}_grasp_rotation_max_abs": max_abs_difference(
                rotation, solution.object_in_base.rotation),
            f"{name}_object_normal_max_abs": _vector_error(solution.object_normal_in_base, (0.0, 0.0, -1.0)),
        })
    return Exercise3Result(inputs, matrix_path, quaternion_path, errors)
