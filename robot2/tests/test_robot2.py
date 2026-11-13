import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from robot_pose.robot2 import (
    TOLERANCE, Robot2Input, solve_robot2, solve_matrix_path, solve_quaternion_path,
)
from robot_pose.geometry import (
    identity, max_abs_difference, quaternion_distance, radians, rpy_to_matrix,
)


class Robot2Tests(unittest.TestCase):
    def assertVectorClose(self, actual, expected, tolerance=1e-12):
        self.assertEqual(len(actual), len(expected))
        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), tolerance)

    def assertMatrixClose(self, actual, expected, tolerance=1e-12):
        self.assertLess(max_abs_difference(actual, expected), tolerance)

    def test_given_current_tcp_and_object(self):
        result = solve_robot2()
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.tcp_in_base.translation,
                                   (0.4783363094478902, 0.09166369055210986, 0.4171058083755676))
            self.assertVectorClose(path.object_in_base.translation,
                                   (0.5148588237760517, 0.05514117622394834, 0.3776442841485013))
            expected_q = (0.8923991008325228, -0.3696438106143861, 0.23911761839433449, 0.09904576054128762)
            self.assertLess(quaternion_distance(path.tcp_in_base.quaternion, expected_q), 1e-12)
            self.assertLess(quaternion_distance(path.object_in_base.quaternion, expected_q), 1e-12)

    def test_combined_chain_rotates_25_mm_offset_to_flange_y(self):
        result = solve_robot2()
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.object_in_flange.translation, (0, 0.025, 0.225))
            self.assertMatrixClose(path.object_in_flange.rotation, ((0, -1, 0), (1, 0, 0), (0, 0, 1)))

    def test_current_flange_is_recovered(self):
        inputs = Robot2Input()
        result = solve_robot2(inputs)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.recovered_flange_in_base.translation, inputs.flange_translation)
            self.assertMatrixClose(path.recovered_flange_in_base.rotation, rpy_to_matrix(inputs.flange_rpy))

    def test_placement_flange_has_expected_answer(self):
        result = solve_robot2()
        for path in (result.matrix_path, result.quaternion_path):
            target = path.target_flange_in_base
            self.assertVectorClose(target.translation, (0.325, -0.450, 0.315))
            self.assertMatrixClose(target.rotation, ((0, 1, 0), (1, 0, 0), (0, 0, -1)))
            self.assertLess(quaternion_distance(target.quaternion,
                (math.sqrt(0.5), math.sqrt(0.5), 0, 0)), 1e-12)

    def test_placement_full_chain_reconstructs_target_object(self):
        result = solve_robot2()
        for path in (result.matrix_path, result.quaternion_path):
            recovered = path.reconstructed_target_object_in_base
            self.assertVectorClose(recovered.translation, (0.350, -0.450, 0.090))
            self.assertMatrixClose(recovered.rotation, ((1, 0, 0), (0, -1, 0), (0, 0, -1)))

    def test_identity_tool_leaves_frames_coincident(self):
        inputs = Robot2Input(
            gripper_translation=(0, 0, 0), gripper_rpy=(0, 0, 0),
            object_translation=(0, 0, 0), object_rpy=(0, 0, 0),
        )
        result = solve_robot2(inputs)
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.tcp_in_base.translation, inputs.flange_translation)
            self.assertVectorClose(path.object_in_base.translation, inputs.flange_translation)
            self.assertVectorClose(path.target_flange_in_base.translation, inputs.target_translation)
            self.assertMatrixClose(path.object_in_flange.transform, identity(4))

    def test_general_object_orientation_and_offset_with_hand_calculated_answers(self):
        inputs = Robot2Input(
            flange_translation=(0.1, 0.2, 0.3), flange_rpy=(0, 0, 0),
            gripper_translation=(0, 0, 0.1), gripper_rpy=radians((0, 0, 90)),
            object_translation=(0.02, 0.03, 0.04), object_rpy=radians((90, 0, 0)),
            target_translation=(0.5, 0.6, 0.7), target_rpy=(0, 0, 0),
        )
        result = solve_robot2(inputs)
        self.assertTrue(result.passed, result.errors)
        for path in (result.matrix_path, result.quaternion_path):
            self.assertVectorClose(path.object_in_flange.translation, (-0.03, 0.02, 0.14))
            self.assertMatrixClose(path.object_in_flange.rotation, ((0, 0, 1), (1, 0, 0), (0, 1, 0)))
            self.assertVectorClose(path.object_in_base.translation, (0.07, 0.22, 0.44))
            self.assertVectorClose(path.target_flange_in_base.translation, (0.48, 0.46, 0.73))

    def test_constant_chain_does_not_depend_on_current_flange_pose(self):
        first = solve_robot2()
        second = solve_robot2(Robot2Input(
            flange_translation=(-0.2, 0.3, 0.9), flange_rpy=radians((35, -20, 80)),
        ))
        self.assertTrue(second.passed, second.errors)
        self.assertMatrixClose(first.matrix_path.object_in_flange.transform,
                               second.matrix_path.object_in_flange.transform)
        self.assertMatrixClose(first.matrix_path.target_flange_in_base.transform,
                               second.matrix_path.target_flange_in_base.transform)
        self.assertGreater(max_abs_difference(first.matrix_path.object_in_base.transform,
                                              second.matrix_path.object_in_base.transform), 0.1)

    def test_quaternion_path_does_not_use_matrix_solving(self):
        with patch("robot_pose.robot2.solve_matrix_path", side_effect=AssertionError("shared solver")), \
             patch("robot_pose.robot2.rpy_to_matrix", side_effect=AssertionError("shared input matrix")), \
             patch("robot_pose.robot2.make_transform", side_effect=AssertionError("shared transform")), \
             patch("robot_pose.robot2.rigid_inverse", side_effect=AssertionError("shared inverse")), \
             patch("robot_pose.robot2.matmul", side_effect=AssertionError("shared matrix product")):
            solution = solve_quaternion_path(Robot2Input())
        self.assertVectorClose(solution.target_flange_in_base.translation, (0.325, -0.450, 0.315))

    def test_matrix_path_does_not_use_quaternion_solving(self):
        with patch("robot_pose.robot2.solve_quaternion_path", side_effect=AssertionError("shared solver")), \
             patch("robot_pose.robot2.rpy_to_quaternion", side_effect=AssertionError("shared input quaternion")), \
             patch("robot_pose.robot2.quaternion_rotate", side_effect=AssertionError("shared rotation")), \
             patch("robot_pose.robot2.quaternion_multiply", side_effect=AssertionError("shared quaternion product")):
            solution = solve_matrix_path(Robot2Input())
        self.assertVectorClose(solution.target_flange_in_base.translation, (0.325, -0.450, 0.315))

    def test_validation_is_strict_and_rejects_nonfinite_errors(self):
        result = solve_robot2()
        for value in (TOLERANCE, math.inf, math.nan):
            with self.subTest(error=value):
                self.assertFalse(replace(result, errors={"check": value}).passed)
        self.assertTrue(replace(result, errors={"check": TOLERANCE / 2}).passed)

    def test_invalid_input_translation_is_rejected(self):
        with self.assertRaises(ValueError):
            solve_robot2(Robot2Input(object_translation=(math.nan, 0, 0)))


if __name__ == "__main__":
    unittest.main()
