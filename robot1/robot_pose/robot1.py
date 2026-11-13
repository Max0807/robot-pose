"""Robot task B1: object pose -> flange pose, with two independent paths."""

import math
from dataclasses import dataclass

from .geometry import (
    Matrix, Quaternion, Vector3, canonical_quaternion, degrees, make_transform,
    matmul, matrix_to_quaternion, matrix_to_rpy, max_abs_difference,
    quaternion_distance, quaternion_inverse, quaternion_multiply,
    quaternion_rotate, quaternion_to_matrix, radians, rigid_inverse,
    rpy_to_matrix, rpy_to_quaternion, split_transform,
)

TOLERANCE = 1e-9


@dataclass(frozen=True)
class Robot1Input:
    """Translations are meters; all angles stored here are radians."""

    object_translation: Vector3 = (0.520, -0.180, 0.120)
    object_rpy: Vector3 = radians((180.0, 0.0, -30.0))
    gripper_translation: Vector3 = (0.0, 0.0, 0.165)
    gripper_rpy: Vector3 = radians((0.0, 0.0, 45.0))


@dataclass(frozen=True)
class PoseSolution:
    translation: Vector3
    rotation: Matrix
    rpy: Vector3
    quaternion: Quaternion

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
class Robot1Result:
    inputs: Robot1Input
    matrix_path: PoseSolution
    quaternion_path: PoseSolution
    errors: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(math.isfinite(value) and value < TOLERANCE for value in self.errors.values())

    def to_dict(self) -> dict:
        return {
            "robot": "B1",
            "convention": {
                "transform": "T_A_B maps coordinates from B to A",
                "rotation": "Rz(rz) @ Ry(ry) @ Rx(rx)",
                "internal_angle_unit": "rad",
                "translation_unit": "m",
                "quaternion_order": "xyzw",
                "object_in_gripper": "identity",
            },
            "inputs": {
                "object_in_base": {
                    "translation_m": self.inputs.object_translation,
                    "rpy_rad": self.inputs.object_rpy,
                    "rpy_deg": degrees(self.inputs.object_rpy),
                },
                "gripper_in_flange": {
                    "translation_m": self.inputs.gripper_translation,
                    "rpy_rad": self.inputs.gripper_rpy,
                    "rpy_deg": degrees(self.inputs.gripper_rpy),
                },
            },
            "matrix_path": self.matrix_path.to_dict(),
            "quaternion_path": self.quaternion_path.to_dict(),
            "validation": {"tolerance": TOLERANCE, "errors": self.errors, "passed": self.passed},
        }


def solve_matrix_path(inputs: Robot1Input) -> PoseSolution:
    # T_B_O = T_B_F @ T_F_G because T_G_O = I in robot task B1.
    base_object = make_transform(rpy_to_matrix(inputs.object_rpy), inputs.object_translation)
    flange_gripper = make_transform(rpy_to_matrix(inputs.gripper_rpy), inputs.gripper_translation)
    # Put a breakpoint here to inspect the two input 4 x 4 transforms.
    base_flange = matmul(base_object, rigid_inverse(flange_gripper))
    rotation, translation = split_transform(base_flange)
    return PoseSolution(translation, rotation, matrix_to_rpy(rotation), matrix_to_quaternion(rotation))


def solve_quaternion_path(inputs: Robot1Input) -> PoseSolution:
    # These inputs come directly from RPY, not from the matrix path's result.
    base_object_q = rpy_to_quaternion(inputs.object_rpy)
    flange_gripper_q = rpy_to_quaternion(inputs.gripper_rpy)
    base_flange_q = canonical_quaternion(
        quaternion_multiply(base_object_q, quaternion_inverse(flange_gripper_q))
    )
    # Rotate the offset with quaternion products, without using a matrix.
    offset_in_base = quaternion_rotate(base_flange_q, inputs.gripper_translation)
    translation = tuple(a - b for a, b in zip(inputs.object_translation, offset_in_base))
    # A matrix is produced only now, for output and comparing the two paths.
    rotation = quaternion_to_matrix(base_flange_q)
    return PoseSolution(translation, rotation, matrix_to_rpy(rotation), base_flange_q)


def solve_robot1(inputs: Robot1Input | None = None) -> Robot1Result:
    inputs = inputs if inputs is not None else Robot1Input()
    matrix_path = solve_matrix_path(inputs)
    quaternion_path = solve_quaternion_path(inputs)
    errors = {
        "paths_translation_max_abs_m": max(
            abs(a - b) for a, b in zip(matrix_path.translation, quaternion_path.translation)
        ),
        "paths_rotation_max_abs": max_abs_difference(matrix_path.rotation, quaternion_path.rotation),
        "paths_quaternion_sign_invariant_l2": quaternion_distance(
            matrix_path.quaternion, quaternion_path.quaternion
        ),
    }
    base_object = make_transform(rpy_to_matrix(inputs.object_rpy), inputs.object_translation)
    flange_gripper = make_transform(rpy_to_matrix(inputs.gripper_rpy), inputs.gripper_translation)
    expected_rotation, expected_translation = split_transform(base_object)
    for name, solution in (("matrix", matrix_path), ("quaternion", quaternion_path)):
        reconstructed = matmul(solution.transform, flange_gripper)
        rotation, translation = split_transform(reconstructed)
        errors[f"{name}_roundtrip_translation_max_abs_m"] = max(
            abs(a - b) for a, b in zip(translation, expected_translation)
        )
        errors[f"{name}_roundtrip_rotation_max_abs"] = max_abs_difference(rotation, expected_rotation)
    return Robot1Result(inputs, matrix_path, quaternion_path, errors)
