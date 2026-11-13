import math
import unittest

from robot_pose.geometry import (
    canonical_quaternion, identity, make_transform, matmul, matrix_to_quaternion,
    matrix_to_rpy, max_abs_difference, normalize_quaternion, quaternion_distance,
    quaternion_inverse, quaternion_multiply, quaternion_rotate,
    quaternion_to_matrix, radians, rigid_inverse, rpy_to_matrix,
    rpy_to_quaternion, split_transform,
)


class GeometryTests(unittest.TestCase):
    def assertMatrixClose(self, actual, expected, tolerance=1e-12):
        self.assertLess(max_abs_difference(actual, expected), tolerance)

    def assertVectorClose(self, actual, expected, tolerance=1e-12):
        self.assertEqual(len(actual), len(expected))
        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), tolerance)

    def test_matrix_product_with_hand_calculated_answer(self):
        self.assertEqual(matmul(((1, 2), (3, 4)), ((5, 6), (7, 8))), ((19, 22), (43, 50)))

    def test_matrix_dimensions_are_checked(self):
        with self.assertRaises(ValueError):
            matmul(((1, 2),), ((1, 2),))
        with self.assertRaises(ValueError):
            matmul(((1, 2), (3,)), identity(2))

    def test_zero_angles_are_identity(self):
        self.assertMatrixClose(rpy_to_matrix((0, 0, 0)), identity(3))
        self.assertVectorClose(rpy_to_quaternion((0, 0, 0)), (0, 0, 0, 1))

    def test_known_yaw_90_matrix(self):
        expected = ((0, -1, 0), (1, 0, 0), (0, 0, 1))
        self.assertMatrixClose(rpy_to_matrix(radians((0, 0, 90))), expected)

    def test_rotation_order_is_not_commutative(self):
        rx = rpy_to_matrix(radians((90, 0, 0)))
        rz = rpy_to_matrix(radians((0, 0, 90)))
        self.assertGreater(max_abs_difference(matmul(rx, rz), matmul(rz, rx)), 0.5)
        self.assertMatrixClose(rpy_to_matrix(radians((90, 0, 90))), matmul(rz, rx))

    def test_transform_translation_is_rotated_before_addition(self):
        first = make_transform(rpy_to_matrix(radians((0, 0, 90))), (1, 0, 0))
        second = make_transform(identity(3), (1, 0, 0))
        _, translation = split_transform(matmul(first, second))
        self.assertVectorClose(translation, (1, 1, 0))

    def test_inverse_translation_has_known_nontrivial_answer(self):
        transform = make_transform(rpy_to_matrix(radians((0, 0, 90))), (1, 2, 3))
        inverse = rigid_inverse(transform)
        _, translation = split_transform(inverse)
        self.assertVectorClose(translation, (-2, 1, -3))
        self.assertMatrixClose(matmul(transform, inverse), identity(4))
        self.assertMatrixClose(matmul(inverse, transform), identity(4))

    def test_rpy_roundtrip_including_gimbal_lock(self):
        cases = ((30, 20, 45), (180, 0, -30), (25, 90, 70), (-35, -90, 15),
                 (10, 89.999999, -20), (30, 120, 40))
        for angles in cases:
            with self.subTest(angles=angles):
                original = rpy_to_matrix(radians(angles))
                self.assertMatrixClose(rpy_to_matrix(matrix_to_rpy(original)), original)

    def test_gimbal_lock_chooses_zero_yaw(self):
        result = matrix_to_rpy(rpy_to_matrix(radians((25, 90, 70))))
        self.assertEqual(result[2], 0.0)

    def test_matrix_to_quaternion_all_four_branches(self):
        # Known rotations exercise the positive trace and largest x/y/z branches.
        cases = (
            (identity(3), (0, 0, 0, 1)),
            (((1, 0, 0), (0, -1, 0), (0, 0, -1)), (1, 0, 0, 0)),
            (((-1, 0, 0), (0, 1, 0), (0, 0, -1)), (0, 1, 0, 0)),
            (((-1, 0, 0), (0, -1, 0), (0, 0, 1)), (0, 0, 1, 0)),
        )
        for rotation, expected in cases:
            with self.subTest(expected=expected):
                self.assertVectorClose(matrix_to_quaternion(rotation), expected)

    def test_quaternion_rotation_preserves_vector_length(self):
        quaternion = rpy_to_quaternion(radians((0, 0, 90)))
        self.assertVectorClose(quaternion_rotate(quaternion, (2, 0, 0)), (0, 2, 0))
        self.assertVectorClose(quaternion_rotate(quaternion, (0, 0, 0)), (0, 0, 0))

    def test_quaternion_composition_order_with_known_vectors(self):
        qx = rpy_to_quaternion(radians((90, 0, 0)))
        qz = rpy_to_quaternion(radians((0, 0, 90)))
        self.assertVectorClose(quaternion_rotate(quaternion_multiply(qz, qx), (0, 1, 0)), (0, 0, 1))
        self.assertVectorClose(quaternion_rotate(quaternion_multiply(qx, qz), (0, 1, 0)), (-1, 0, 0))

    def test_quaternion_inverse(self):
        quaternion = rpy_to_quaternion(radians((35, -20, 80)))
        self.assertVectorClose(quaternion_multiply(quaternion, quaternion_inverse(quaternion)), (0, 0, 0, 1))

    def test_quaternion_sign_is_equivalent(self):
        quaternion = rpy_to_quaternion(radians((180, 0, 15)))
        opposite = tuple(-value for value in quaternion)
        self.assertEqual(quaternion_distance(quaternion, opposite), 0.0)
        self.assertMatrixClose(quaternion_to_matrix(quaternion), quaternion_to_matrix(opposite))
        self.assertVectorClose(canonical_quaternion(opposite), canonical_quaternion(quaternion))

    def test_nonunit_quaternion_is_normalized(self):
        self.assertVectorClose(normalize_quaternion((0, 0, 0, 3)), (0, 0, 0, 1))
        self.assertMatrixClose(quaternion_to_matrix((0, 0, 0, 3)), identity(3))

    def test_invalid_angles_and_quaternions_are_rejected(self):
        for values in ((0, 0), (0, 0, math.nan), (0, math.inf, 0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                rpy_to_matrix(values)
        with self.assertRaises(ValueError):
            normalize_quaternion((0, 0, 0, 0))

    def test_reflection_is_not_a_rotation(self):
        reflection = ((1, 0, 0), (0, 1, 0), (0, 0, -1))
        with self.assertRaises(ValueError):
            matrix_to_quaternion(reflection)

    def test_invalid_homogeneous_row_is_rejected(self):
        invalid = identity(3) + ((0, 0, 0),)
        with self.assertRaises(ValueError):
            rigid_inverse(invalid)
        invalid_row = identity(4)[:3] + ((0, 0, 1, 1),)
        with self.assertRaises(ValueError):
            rigid_inverse(invalid_row)


if __name__ == "__main__":
    unittest.main()
