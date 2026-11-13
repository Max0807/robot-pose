import math
import unittest

from robot_pose.camera import CameraIntrinsics, backproject_pixel, project_camera_point


class CameraTests(unittest.TestCase):
    def assertVectorClose(self, actual, expected, tolerance=1e-12):
        self.assertEqual(len(actual), len(expected))
        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), tolerance)

    def test_given_backprojection(self):
        self.assertVectorClose(backproject_pixel((720, 280), 0.4, CameraIntrinsics()), (0.04, -0.04, 0.4))

    def test_principal_point_is_on_optical_axis(self):
        self.assertVectorClose(backproject_pixel((640, 360), 0.7, CameraIntrinsics()), (0, 0, 0.7))

    def test_different_focal_lengths_and_offsets(self):
        intrinsics = CameraIntrinsics(fx=1000, fy=500, cx=100, cy=50, width=400, height=200)
        self.assertVectorClose(backproject_pixel((160, 30), 0.5, intrinsics), (0.03, -0.02, 0.5))

    def test_known_projection(self):
        self.assertVectorClose(project_camera_point((0.04, -0.04, 0.4), CameraIntrinsics()), (720, 280))

    def test_fractional_pixel_without_half_pixel_shift(self):
        self.assertVectorClose(backproject_pixel((640.5, 359.25), 0.8, CameraIntrinsics()), (0.0005, -0.00075, 0.8))

    def test_geometric_projection_is_not_clipped(self):
        self.assertVectorClose(project_camera_point((2, 1, 1), CameraIntrinsics()), (2240, 1160))

    def test_invalid_intrinsic_numbers_are_rejected(self):
        for field, value in (("fx", 0), ("fy", -1), ("fx", math.nan), ("fy", math.inf),
                             ("cx", math.nan), ("cy", math.inf)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                CameraIntrinsics(**{field: value})

    def test_invalid_image_dimensions_are_rejected(self):
        for field, value in (("width", 0), ("height", -1), ("width", True), ("height", 720.5)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                CameraIntrinsics(**{field: value})

    def test_invalid_depth_is_rejected(self):
        for depth in (0, -0.4, math.nan, math.inf):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                backproject_pixel((720, 280), depth, CameraIntrinsics())

    def test_invalid_or_outside_detection_pixel_is_rejected(self):
        for pixel in ((720,), (720, 280, 1), (math.nan, 280), (-1, 280), (1280, 280), (720, 720)):
            with self.subTest(pixel=pixel), self.assertRaises(ValueError):
                backproject_pixel(pixel, 0.4, CameraIntrinsics())

    def test_invalid_camera_point_is_rejected(self):
        for point in ((1, 2), (1, 2, 0), (1, 2, -1), (math.nan, 2, 1), (1, 2, math.inf)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                project_camera_point(point, CameraIntrinsics())


if __name__ == "__main__":
    unittest.main()
