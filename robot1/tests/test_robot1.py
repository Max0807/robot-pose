import unittest
from unittest.mock import patch

from robot_pose.robot1 import Robot1Input, solve_robot1, solve_quaternion_path
from robot_pose.geometry import degrees, max_abs_difference, quaternion_distance, radians


class Robot1Tests(unittest.TestCase):
    def test_given_problem_has_expected_answer(self):
        result = solve_robot1()
        self.assertTrue(result.passed, result.errors)
        for solution in (result.matrix_path, result.quaternion_path):
            for actual, expected in zip(solution.translation, (0.520, -0.180, 0.285)):
                self.assertAlmostEqual(actual, expected, places=12)
            for actual, expected in zip(degrees(solution.rpy), (180, 0, 15)):
                self.assertAlmostEqual(actual, expected, places=10)
            self.assertLess(max_abs_difference(solution.rotation, (
                (0.9659258262890683, 0.25881904510252074, 0),
                (0.25881904510252074, -0.9659258262890683, 0),
                (0, 0, -1),
            )), 1e-12)
            self.assertLess(quaternion_distance(solution.quaternion,
                (0.9914448613738104, 0.13052619222005157, 0, 0)), 1e-12)

    def test_identity_tool_leaves_object_and_flange_coincident(self):
        inputs = Robot1Input(gripper_translation=(0, 0, 0), gripper_rpy=(0, 0, 0))
        result = solve_robot1(inputs)
        self.assertTrue(result.passed, result.errors)
        self.assertEqual(result.matrix_path.translation, inputs.object_translation)

    def test_lateral_offset_and_general_rotations(self):
        # General tool geometry catches code that happens to work only for z offsets.
        result = solve_robot1(Robot1Input(
            object_translation=(0.4, -0.3, 0.8), object_rpy=radians((35, -20, 80)),
            gripper_translation=(0.025, -0.015, 0.165), gripper_rpy=radians((10, 25, -40)),
        ))
        self.assertTrue(result.passed, result.errors)

    def test_quaternion_path_does_not_use_matrix_solver(self):
        # Fail immediately if the quaternion solver reuses matrix-based solving.
        with patch("robot_pose.robot1.solve_matrix_path", side_effect=AssertionError("shared solver")), \
             patch("robot_pose.robot1.rpy_to_matrix", side_effect=AssertionError("shared RPY matrix")), \
             patch("robot_pose.robot1.rigid_inverse", side_effect=AssertionError("shared inverse")), \
             patch("robot_pose.robot1.matmul", side_effect=AssertionError("shared matrix product")):
            solution = solve_quaternion_path(Robot1Input())
        self.assertAlmostEqual(solution.translation[2], 0.285, places=12)


if __name__ == "__main__":
    unittest.main()
