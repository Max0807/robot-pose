"""第2题：正解、固定安装链合并、当前法兰反解和下料反解。

两个求解路径只共用输入和展示格式，不互相读取中间求解结果。
所有内部角度为弧度，平移为米，四元数顺序为 (x, y, z, w)。
"""

import math
from dataclasses import dataclass

from .geometry import (
    Matrix, Quaternion, Vector3, canonical_quaternion, degrees, make_transform,
    matmul, matrix_to_quaternion, matrix_to_rpy, max_abs_difference,
    normalize_quaternion, quaternion_distance, quaternion_inverse,
    quaternion_multiply, quaternion_rotate, quaternion_to_matrix, radians,
    rigid_inverse, rpy_to_matrix, rpy_to_quaternion, split_transform,
)

TOLERANCE = 1e-9

# 所有阶段都有明确的父/子坐标系；这些名称也作为 JSON 字段。
STAGE_LABELS = (
    ("tcp_in_base", "TCP 在基座下的当前位姿 T_B_G"),
    ("object_in_base", "工件在基座下的当前位姿 T_B_O"),
    ("object_in_flange", "合并的固定安装链 T_F_O"),
    ("recovered_flange_in_base", "由当前工件反解恢复的法兰位姿 T_B_F"),
    ("target_flange_in_base", "下料时法兰目标位姿 T_B_F_target"),
    ("reconstructed_target_object_in_base", "用完整安装链回代的下料工件位姿 T_B_O_target"),
)


@dataclass(frozen=True)
class Exercise2Input:
    """题面数据；注意 object_* 表示工件相对夹持中心，而非相对基座。"""

    flange_translation: Vector3 = (0.420, 0.150, 0.560)
    flange_rpy: Vector3 = radians((150.0, 0.0, 45.0))
    gripper_translation: Vector3 = (0.0, 0.0, 0.165)
    gripper_rpy: Vector3 = radians((0.0, 0.0, 90.0))
    object_translation: Vector3 = (0.025, 0.0, 0.060)
    object_rpy: Vector3 = radians((0.0, 0.0, 0.0))
    target_translation: Vector3 = (0.350, -0.450, 0.090)
    target_rpy: Vector3 = radians((180.0, 0.0, 0.0))


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
        return {
            "translation_m": self.translation,
            "rotation_matrix": self.rotation,
            "rpy_rad": self.rpy,
            "rpy_deg": degrees(self.rpy),
            "quaternion_xyzw": self.quaternion,
            "transform_matrix": self.transform,
        }


@dataclass(frozen=True)
class PathSolution:
    tcp_in_base: PoseSolution
    object_in_base: PoseSolution
    object_in_flange: PoseSolution
    recovered_flange_in_base: PoseSolution
    target_flange_in_base: PoseSolution
    reconstructed_target_object_in_base: PoseSolution

    def to_dict(self) -> dict:
        return {name: getattr(self, name).to_dict() for name, _ in STAGE_LABELS}


@dataclass(frozen=True)
class Exercise2Result:
    inputs: Exercise2Input
    matrix_path: PathSolution
    quaternion_path: PathSolution
    errors: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(math.isfinite(value) and value < TOLERANCE for value in self.errors.values())

    def to_dict(self) -> dict:
        inputs = {}
        for name, translation, rpy in (
            ("flange_in_base", self.inputs.flange_translation, self.inputs.flange_rpy),
            ("gripper_in_flange", self.inputs.gripper_translation, self.inputs.gripper_rpy),
            ("object_in_gripper", self.inputs.object_translation, self.inputs.object_rpy),
            ("target_object_in_base", self.inputs.target_translation, self.inputs.target_rpy),
        ):
            inputs[name] = {"translation_m": translation, "rpy_rad": rpy, "rpy_deg": degrees(rpy)}
        return {
            "exercise": "B2",
            "convention": {
                "transform": "T_A_B maps coordinates from B to A",
                "rotation": "Rz(rz) @ Ry(ry) @ Rx(rx)",
                "internal_angle_unit": "rad",
                "translation_unit": "m",
                "quaternion_order": "xyzw",
                "rigid_grasp": "T_G_O stays constant for this grasp",
            },
            "inputs": inputs,
            "matrix_path": self.matrix_path.to_dict(),
            "quaternion_path": self.quaternion_path.to_dict(),
            "validation": {"tolerance": TOLERANCE, "errors": self.errors, "passed": self.passed},
        }


def solve_matrix_path(inputs: Exercise2Input) -> PathSolution:
    base_flange = make_transform(rpy_to_matrix(inputs.flange_rpy), inputs.flange_translation)
    flange_gripper = make_transform(rpy_to_matrix(inputs.gripper_rpy), inputs.gripper_translation)
    gripper_object = make_transform(rpy_to_matrix(inputs.object_rpy), inputs.object_translation)
    base_target_object = make_transform(rpy_to_matrix(inputs.target_rpy), inputs.target_translation)

    # 正解：沿 B -> F -> G -> O 安装链逐段组合。
    base_gripper = matmul(base_flange, flange_gripper)
    base_object = matmul(base_gripper, gripper_object)
    # 固定链中 25 mm 偏心先旋转到法兰系，再与安装平移相加。
    flange_object = matmul(flange_gripper, gripper_object)
    inverse_tool = rigid_inverse(flange_object)
    recovered_flange = matmul(base_object, inverse_tool)
    # 下料反解必须使用整条 F -> O 链，不能漏掉夹持偏心和伸出量。
    target_flange = matmul(base_target_object, inverse_tool)
    # 回代展开完整安装链，另外也会检查缓存链的等价性。
    reconstructed_target_object = matmul(matmul(target_flange, flange_gripper), gripper_object)
    return PathSolution(*(
        PoseSolution.from_matrix(transform) for transform in (
            base_gripper, base_object, flange_object, recovered_flange,
            target_flange, reconstructed_target_object,
        )
    ))


# 四元数位姿用 (q, t) 保存，在求解完成前不构造旋转矩阵。
QuaternionTransform = tuple[Quaternion, Vector3]


def _quaternion_transform(rpy: Vector3, translation: Vector3) -> QuaternionTransform:
    translation = tuple(float(value) for value in translation)
    if len(translation) != 3 or not all(math.isfinite(value) for value in translation):
        raise ValueError("A translation must contain three finite numbers.")
    return rpy_to_quaternion(rpy), translation


def _compose_quaternions(left: QuaternionTransform, right: QuaternionTransform) -> QuaternionTransform:
    left_q, left_t = left
    right_q, right_t = right
    rotated_offset = quaternion_rotate(left_q, right_t)
    translation = tuple(a + b for a, b in zip(left_t, rotated_offset))
    quaternion = normalize_quaternion(quaternion_multiply(left_q, right_q))
    return quaternion, translation


def _inverse_quaternions(transform: QuaternionTransform) -> QuaternionTransform:
    quaternion, translation = transform
    inverse_q = quaternion_inverse(quaternion)
    inverse_t = quaternion_rotate(inverse_q, tuple(-value for value in translation))
    return inverse_q, inverse_t


def solve_quaternion_path(inputs: Exercise2Input) -> PathSolution:
    # 从原始 RPY 独立构造四元数，不调用矩阵求解器。
    base_flange = _quaternion_transform(inputs.flange_rpy, inputs.flange_translation)
    flange_gripper = _quaternion_transform(inputs.gripper_rpy, inputs.gripper_translation)
    gripper_object = _quaternion_transform(inputs.object_rpy, inputs.object_translation)
    base_target_object = _quaternion_transform(inputs.target_rpy, inputs.target_translation)

    base_gripper = _compose_quaternions(base_flange, flange_gripper)
    base_object = _compose_quaternions(base_gripper, gripper_object)
    flange_object = _compose_quaternions(flange_gripper, gripper_object)
    inverse_tool = _inverse_quaternions(flange_object)
    recovered_flange = _compose_quaternions(base_object, inverse_tool)
    target_flange = _compose_quaternions(base_target_object, inverse_tool)
    reconstructed_target_object = _compose_quaternions(
        _compose_quaternions(target_flange, flange_gripper), gripper_object
    )
    # 所有求解已完成，现在才转成矩阵和 RPY 供输出与比较。
    return PathSolution(*(
        PoseSolution.from_quaternion(quaternion, translation) for quaternion, translation in (
            base_gripper, base_object, flange_object, recovered_flange,
            target_flange, reconstructed_target_object,
        )
    ))


def _pose_errors(prefix: str, actual: PoseSolution, expected: PoseSolution) -> dict[str, float]:
    return {
        f"{prefix}_translation_max_abs_m": max(
            abs(a - b) for a, b in zip(actual.translation, expected.translation)
        ),
        f"{prefix}_rotation_max_abs": max_abs_difference(actual.rotation, expected.rotation),
    }


def solve_exercise2(inputs: Exercise2Input | None = None) -> Exercise2Result:
    inputs = inputs if inputs is not None else Exercise2Input()
    matrix_path = solve_matrix_path(inputs)
    quaternion_path = solve_quaternion_path(inputs)
    errors = {}
    for stage, _ in STAGE_LABELS:
        first, second = getattr(matrix_path, stage), getattr(quaternion_path, stage)
        errors.update(_pose_errors(f"paths_{stage}", first, second))
        errors[f"paths_{stage}_quaternion_sign_invariant_l2"] = quaternion_distance(
            first.quaternion, second.quaternion
        )

    expected_flange = PoseSolution.from_matrix(
        make_transform(rpy_to_matrix(inputs.flange_rpy), inputs.flange_translation)
    )
    expected_target = PoseSolution.from_matrix(
        make_transform(rpy_to_matrix(inputs.target_rpy), inputs.target_translation)
    )
    for name, solution in (("matrix", matrix_path), ("quaternion", quaternion_path)):
        errors.update(_pose_errors(f"{name}_recover_flange", solution.recovered_flange_in_base, expected_flange))
        errors.update(_pose_errors(
            f"{name}_target_roundtrip", solution.reconstructed_target_object_in_base, expected_target
        ))
        # 使用合并链计算当前工件，应与逐段计算的结果一致。
        cached_object = PoseSolution.from_matrix(matmul(expected_flange.transform, solution.object_in_flange.transform))
        errors.update(_pose_errors(f"{name}_cached_chain", cached_object, solution.object_in_base))
    return Exercise2Result(inputs, matrix_path, quaternion_path, errors)
