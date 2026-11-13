import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from robot_pose.camera import CameraIntrinsics
from robot_pose.exercise3 import (
    TOLERANCE, Exercise3Input, solve_exercise3, solve_matrix_path, solve_quaternion_path,
)
from robot_pose.geometry import max_abs_difference, quaternion_distance, radians, rpy_to_matrix


class Exercise3Tests(unittest.TestCase):
    def assertVectorClose(self, actual, expected, tolerance=1e-12):
        self.assertEqual(len(actual), len(expected))
        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), tolerance)

    def assertMatrixClose(self, actual, expected, tolerance=1e-12):
        self.assertLess(max_abs_difference(actual, expected), tolerance)

    def test_given_problem_has_expected_answer(self):
        result = solve_exercise3()
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.camera_point, (0.04, -0.04, 0.4))
            self.assertVectorClose(path.base_point, (0.7282842712474619, -0.1510102051443365, 0.6))
            self.assertVectorClose(path.target_flange_in_base.translation,
                                   (0.7282842712474619, -0.1510102051443365, 0.765))
            root_half = math.sqrt(0.5)
            self.assertMatrixClose(path.target_flange_in_base.rotation,
                                   ((root_half, root_half, 0), (root_half, -root_half, 0), (0, 0, -1)))
            self.assertLess(quaternion_distance(path.target_flange_in_base.quaternion,
                (0.9238795325112867, 0.3826834323650898, 0, 0)), 1e-12)

    def test_optical_axis_and_object_normal_are_downward_directions(self):
        result = solve_exercise3()
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.camera_optical_axis_in_base, (0, 0, -1))
            self.assertVectorClose(path.object_normal_in_base, (0, 0, -1))

    def test_inverse_and_reprojection_recover_original_detection(self):
        result = solve_exercise3()
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.recovered_camera_point, (0.04, -0.04, 0.4))
            self.assertVectorClose(path.reprojected_pixel, (720, 280))

    def test_grasp_reconstructs_center_and_orientation(self):
        result = solve_exercise3()
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.reconstructed_gripper_in_base.translation, path.base_point)
            self.assertMatrixClose(path.reconstructed_gripper_in_base.rotation, ((1, 0, 0), (0, -1, 0), (0, 0, -1)))

    def test_general_extrinsic_direction_with_hand_calculated_answer(self):
        inputs = Exercise3Input(
            intrinsics=CameraIntrinsics(fx=100, fy=200, cx=100, cy=100, width=400, height=300),
            pixel=(120, 60), depth_m=0.5,
            camera_translation=(1, 2, 3), camera_rpy=radians((0, 0, 90)),
        )
        result = solve_exercise3(inputs)
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.camera_point, (0.1, -0.1, 0.5))
            self.assertVectorClose(path.base_point, (1.1, 2.1, 3.5))
            self.assertVectorClose(path.camera_optical_axis_in_base, (0, 0, 1))
            self.assertVectorClose(path.object_normal_in_base, (0, 0, -1))

    def test_tool_and_selected_yaw_do_not_change_vision_position(self):
        first = solve_exercise3()
        second = solve_exercise3(Exercise3Input(
            gripper_translation=(0.02, -0.01, 0.165), gripper_rpy=radians((10, 20, 30)),
            object_yaw=math.radians(60),
        ))
        self.assertTrue(second.passed, second.errors)
        for a, b in ((first.matrix_path, second.matrix_path), (first.quaternion_path, second.quaternion_path)):
            self.assertVectorClose(a.base_point, b.base_point)
            self.assertGreater(max_abs_difference(a.target_flange_in_base.transform,
                                                  b.target_flange_in_base.transform), 0.01)

    def test_yaw_is_a_selectable_grasp_convention(self):
        result = solve_exercise3(Exercise3Input(object_yaw=math.radians(60)))
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.object_normal_in_base, (0, 0, -1))
            self.assertMatrixClose(path.object_in_base.rotation, rpy_to_matrix(radians((180, 0, 60))))
            self.assertMatrixClose(path.target_flange_in_base.rotation, rpy_to_matrix(radians((180, 0, 105))))

    def test_depth_is_axial_and_not_euclidean_range(self):
        result = solve_exercise3()
        point = result.matrix_path.camera_point
        self.assertEqual(point[2], result.inputs.depth_m)
        self.assertGreater(math.hypot(*point), result.inputs.depth_m)

    def test_quaternion_path_does_not_use_matrix_solving(self):
        with patch("robot_pose.exercise3.solve_matrix_path", side_effect=AssertionError("shared solver")), \
             patch("robot_pose.exercise3.rpy_to_matrix", side_effect=AssertionError("shared input matrix")), \
             patch("robot_pose.exercise3.make_transform", side_effect=AssertionError("shared transform")), \
             patch("robot_pose.exercise3.rigid_inverse", side_effect=AssertionError("shared inverse")), \
             patch("robot_pose.exercise3.matmul", side_effect=AssertionError("shared matrix product")), \
             patch("robot_pose.exercise3.matvec", side_effect=AssertionError("shared matrix-vector product")):
            solution = solve_quaternion_path(Exercise3Input())
        self.assertAlmostEqual(solution.target_flange_in_base.translation[2], 0.765, places=12)

    def test_matrix_path_does_not_use_quaternion_solving(self):
        with patch("robot_pose.exercise3.solve_quaternion_path", side_effect=AssertionError("shared solver")), \
             patch("robot_pose.exercise3.rpy_to_quaternion", side_effect=AssertionError("shared input quaternion")), \
             patch("robot_pose.exercise3.quaternion_rotate", side_effect=AssertionError("shared rotation")), \
             patch("robot_pose.exercise3.quaternion_multiply", side_effect=AssertionError("shared product")):
            solution = solve_matrix_path(Exercise3Input())
        self.assertAlmostEqual(solution.target_flange_in_base.translation[2], 0.765, places=12)

    def test_invalid_extrinsic_and_yaw_are_rejected(self):
        for inputs in (Exercise3Input(camera_translation=(math.nan, 0, 0)),
                       Exercise3Input(gripper_translation=(0, 0)),
                       Exercise3Input(object_yaw=math.inf)):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                solve_exercise3(inputs)

    def test_validation_is_strict_and_rejects_nonfinite_errors(self):
        result = solve_exercise3()
        for value in (TOLERANCE, math.nan, math.inf):
            with self.subTest(error=value):
                self.assertFalse(replace(result, errors={"check": value}).passed)
        self.assertTrue(replace(result, errors={"check": TOLERANCE / 2}).passed)

    def test_grasp_validation_recomputes_from_final_flange(self):
        result = solve_exercise3()
        wrong_paths = []
        for path in (result.matrix_path, result.quaternion_path):
            x, y, z = path.target_flange_in_base.translation
            wrong_pose = replace(path.target_flange_in_base, translation=(x + 0.01, y, z))
            # 两条路径都给出相同错误法兰，且保留看似正确的缓存回代值。
            wrong_paths.append(replace(path, target_flange_in_base=wrong_pose))
        with patch("robot_pose.exercise3.solve_matrix_path", return_value=wrong_paths[0]), \
             patch("robot_pose.exercise3.solve_quaternion_path", return_value=wrong_paths[1]):
            checked = solve_exercise3()
        self.assertFalse(checked.passed)
        self.assertGreater(checked.errors["matrix_grasp_center_max_abs_m"], 0.009)
        self.assertGreater(checked.errors["quaternion_grasp_center_max_abs_m"], 0.009)


if __name__ == "__main__":
    unittest.main()
