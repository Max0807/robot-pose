"""Optional external reference: not used by either production calculation path."""

import random
import unittest

from robot_pose.exercise1 import Exercise1Input, solve_exercise1
from robot_pose.geometry import (
    make_transform, matrix_to_quaternion, matrix_to_rpy, max_abs_difference,
    quaternion_distance, quaternion_multiply, quaternion_rotate,
    quaternion_to_matrix, radians, rigid_inverse, rpy_to_matrix, rpy_to_quaternion,
)

try:
    import numpy as np
    from scipy.spatial.transform import Rotation
except ImportError:
    SCIPY_AVAILABLE = False
else:
    SCIPY_AVAILABLE = True


@unittest.skipUnless(SCIPY_AVAILABLE, "Optional SciPy not installed; see requirements-validation.txt")
class SciPyReferenceTests(unittest.TestCase):
    def test_rotation_conversions_against_scipy(self):
        generator = random.Random(20261112)
        cases = [radians(values) for values in (
            (180, 0, -30), (180, 0, 15), (0, 180, 0), (0, 0, 180),
            (25, 90, 70), (-35, -90, 15), (10, 89.999999, -20),
        )]
        cases.extend(tuple(generator.uniform(-3.14, 3.14) for _ in range(3)) for _ in range(40))
        for angles in cases:
            with self.subTest(angles=angles):
                reference = Rotation.from_euler("xyz", angles)
                matrix = rpy_to_matrix(angles)
                self.assertLess(max_abs_difference(matrix, reference.as_matrix().tolist()), 1e-12)
                self.assertLess(quaternion_distance(rpy_to_quaternion(angles), reference.as_quat()), 1e-12)
                self.assertLess(quaternion_distance(
                    matrix_to_quaternion(reference.as_matrix().tolist()), reference.as_quat()), 1e-12)
                recovered = Rotation.from_euler("xyz", matrix_to_rpy(matrix)).as_matrix().tolist()
                self.assertLess(max_abs_difference(recovered, reference.as_matrix().tolist()), 1e-12)

    def test_quaternion_composition_and_vector_rotation_against_scipy(self):
        a = Rotation.from_euler("xyz", radians((35, -20, 80)))
        b = Rotation.from_euler("xyz", radians((-15, 25, 40)))
        combined = quaternion_multiply(a.as_quat(), b.as_quat())
        self.assertLess(quaternion_distance(combined, (a * b).as_quat()), 1e-12)
        actual = quaternion_rotate(combined, (0.025, -0.015, 0.165))
        expected = (a * b).apply((0.025, -0.015, 0.165))
        self.assertLess(max(abs(x - y) for x, y in zip(actual, expected)), 1e-12)
        self.assertLess(max_abs_difference(quaternion_to_matrix(combined), (a * b).as_matrix().tolist()), 1e-12)

    def test_rigid_inverse_against_numpy(self):
        transform = make_transform(rpy_to_matrix(radians((35, -20, 80))), (0.4, -0.3, 0.8))
        reference = np.linalg.inv(np.asarray(transform)).tolist()
        self.assertLess(max_abs_difference(rigid_inverse(transform), reference), 1e-12)

    def test_complete_problem_against_scipy_and_numpy(self):
        inputs = Exercise1Input()
        object_pose = np.eye(4)
        object_pose[:3, :3] = Rotation.from_euler("xyz", inputs.object_rpy).as_matrix()
        object_pose[:3, 3] = inputs.object_translation
        gripper_pose = np.eye(4)
        gripper_pose[:3, :3] = Rotation.from_euler("xyz", inputs.gripper_rpy).as_matrix()
        gripper_pose[:3, 3] = inputs.gripper_translation
        reference = (object_pose @ np.linalg.inv(gripper_pose)).tolist()
        result = solve_exercise1(inputs)
        for solution in (result.matrix_path, result.quaternion_path):
            self.assertLess(max_abs_difference(solution.transform, reference), 1e-12)


if __name__ == "__main__":
    unittest.main()
