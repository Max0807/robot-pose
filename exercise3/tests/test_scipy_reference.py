"""Optional external reference: not used by either production calculation path."""

import random
import unittest

from robot_pose.camera import CameraIntrinsics
from robot_pose.exercise3 import Exercise3Input, solve_exercise3
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
        def reference_transform(translation, rpy):
            result = np.eye(4)
            result[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()
            result[:3, 3] = translation
            return result

        generator = random.Random(20261112)
        inputs_to_check = [Exercise3Input(), Exercise3Input(
            intrinsics=CameraIntrinsics(fx=900, fy=1100, cx=600, cy=300),
            pixel=(790, 210), depth_m=0.7,
        )]
        # General camera rotations, off-axis tools and selected yaw avoid sample-only formulas.
        for _ in range(10):
            def position():
                return tuple(generator.uniform(-0.5, 0.5) for _ in range(3))

            def angles():
                return tuple(generator.uniform(-3.14, 3.14) for _ in range(3))

            inputs_to_check.append(Exercise3Input(
                pixel=(generator.uniform(10, 1200), generator.uniform(10, 700)),
                depth_m=generator.uniform(0.1, 2.0),
                camera_translation=position(), camera_rpy=angles(),
                gripper_translation=position(), gripper_rpy=angles(),
                object_yaw=generator.uniform(-3.14, 3.14),
            ))

        for inputs in inputs_to_check:
            with self.subTest(inputs=inputs):
                # Inverting K is an independent check of the scalar backprojection formula.
                ray = np.linalg.inv(np.asarray(inputs.intrinsics.matrix)) @ np.asarray((*inputs.pixel, 1.0))
                camera_point = inputs.depth_m * ray
                bc = reference_transform(inputs.camera_translation, inputs.camera_rpy)
                base_point = (bc @ np.asarray((*camera_point, 1.0)))[:3]
                bo = reference_transform(base_point, inputs.object_rpy)
                fg = reference_transform(inputs.gripper_translation, inputs.gripper_rpy)
                target_flange = bo @ np.linalg.inv(fg)
                references = {
                    "object_in_base": bo,
                    "target_flange_in_base": target_flange,
                    "reconstructed_gripper_in_base": target_flange @ fg,
                }
                result = solve_exercise3(inputs)
                self.assertTrue(result.passed, result.errors)
                for path in (result.matrix_path, result.quaternion_path):
                    self.assertLess(max(abs(a - b) for a, b in zip(path.camera_point, camera_point)), 1e-12)
                    self.assertLess(max(abs(a - b) for a, b in zip(path.base_point, base_point)), 1e-12)
                    recovered_point = (np.linalg.inv(bc) @ np.asarray((*base_point, 1.0)))[:3]
                    self.assertLess(max(abs(a - b) for a, b in zip(path.recovered_camera_point, recovered_point)), 1e-12)
                    optical_axis = bc[:3, :3] @ np.asarray((0, 0, 1))
                    self.assertLess(max(abs(a - b) for a, b in zip(path.camera_optical_axis_in_base, optical_axis)), 1e-12)
                    for stage, reference in references.items():
                        self.assertLess(max_abs_difference(getattr(path, stage).transform, reference.tolist()), 1e-12)


if __name__ == "__main__":
    unittest.main()
