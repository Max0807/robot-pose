"""Small 3-D geometry functions implemented with the Python standard library.

Convention: column vectors, R = Rz(rz) @ Ry(ry) @ Rx(rx), radians,
Hamilton quaternions in (x, y, z, w) order. A transform T_A_B maps B to A.
"""

import math
from collections.abc import Sequence

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
Matrix = tuple[tuple[float, ...], ...]
EPSILON = 1e-12


def _finite_values(values: Sequence[float], size: int) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != size or not all(math.isfinite(value) for value in result):
        raise ValueError(f"Expected {size} finite numbers.")
    return result


def _shape(matrix: Sequence[Sequence[float]]) -> tuple[int, int]:
    if not matrix or not matrix[0]:
        raise ValueError("A matrix must have at least one row and column.")
    columns = len(matrix[0])
    if any(len(row) != columns for row in matrix):
        raise ValueError("Matrix rows must have equal lengths.")
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ValueError("Matrix entries must be finite.")
    return len(matrix), columns


def identity(size: int) -> Matrix:
    if size < 1:
        raise ValueError("Identity matrix size must be positive.")
    return tuple(tuple(float(i == j) for j in range(size)) for i in range(size))


def transpose(matrix: Sequence[Sequence[float]]) -> Matrix:
    rows, columns = _shape(matrix)
    return tuple(tuple(matrix[i][j] for i in range(rows)) for j in range(columns))


def matmul(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> Matrix:
    """Matrix product; use explicit sums rather than a numerical library."""
    rows, inner = _shape(left)
    right_rows, columns = _shape(right)
    if inner != right_rows:
        raise ValueError("Matrix dimensions do not match for multiplication.")
    return tuple(
        tuple(sum(left[i][k] * right[k][j] for k in range(inner)) for j in range(columns))
        for i in range(rows)
    )


def matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> tuple[float, ...]:
    _, columns = _shape(matrix)
    values = _finite_values(vector, columns)
    return tuple(sum(a * b for a, b in zip(row, values)) for row in matrix)


def max_abs_difference(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> float:
    if _shape(left) != _shape(right):
        raise ValueError("Matrices must have the same shape for comparison.")
    return max(abs(a - b) for row_a, row_b in zip(left, right) for a, b in zip(row_a, row_b))


def _check_rotation(rotation: Sequence[Sequence[float]]) -> None:
    if _shape(rotation) != (3, 3):
        raise ValueError("A rotation matrix must be 3 x 3.")
    a, b, c = rotation
    determinant = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    orthogonality_error = max_abs_difference(matmul(transpose(rotation), rotation), identity(3))
    if orthogonality_error > 1e-9 or abs(determinant - 1.0) > 1e-9:
        raise ValueError("A rotation matrix must be orthogonal with determinant +1.")


def radians(angles_degrees: Sequence[float]) -> Vector3:
    return tuple(math.radians(value) for value in _finite_values(angles_degrees, 3))


def degrees(angles_radians: Sequence[float]) -> Vector3:
    return tuple(math.degrees(value) for value in _finite_values(angles_radians, 3))


def rpy_to_matrix(rpy: Sequence[float]) -> Matrix:
    """Fixed-axis x/y/z rotations: Rz(rz) @ Ry(ry) @ Rx(rx)."""
    rx, ry, rz = _finite_values(rpy, 3)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rotation_x = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    rotation_y = ((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy))
    rotation_z = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))
    return matmul(matmul(rotation_z, rotation_y), rotation_x)


def matrix_to_rpy(rotation: Sequence[Sequence[float]]) -> Vector3:
    """Return pitch in [-pi/2, pi/2]; at gimbal lock, choose yaw = 0.

    Equivalent input/output Euler angles need not be componentwise equal.
    Reconstruct the rotation matrix to compare their physical orientation.
    """
    _check_rotation(rotation)
    cos_pitch = math.hypot(rotation[0][0], rotation[1][0])
    pitch = math.atan2(-rotation[2][0], cos_pitch)
    if cos_pitch > EPSILON:
        roll = math.atan2(rotation[2][1], rotation[2][2])
        yaw = math.atan2(rotation[1][0], rotation[0][0])
    else:
        roll = math.atan2(-rotation[1][2], rotation[1][1])
        yaw = 0.0
    return roll, pitch, yaw


def normalize_quaternion(quaternion: Sequence[float]) -> Quaternion:
    values = _finite_values(quaternion, 4)
    norm = math.hypot(*values)
    if norm == 0.0 or not math.isfinite(norm):
        raise ValueError("A quaternion must have a finite, nonzero norm.")
    return tuple(value / norm for value in values)


def canonical_quaternion(quaternion: Sequence[float]) -> Quaternion:
    """Choose a display sign: positive w, or first positive vector term near w=0."""
    values = normalize_quaternion(quaternion)
    if abs(values[3]) > EPSILON:
        sign_reference = values[3]
    else:
        sign_reference = next(value for value in values[:3] if abs(value) > EPSILON)
    return tuple(-value for value in values) if sign_reference < 0.0 else values


def quaternion_multiply(left: Sequence[float], right: Sequence[float]) -> Quaternion:
    """Hamilton product; also supports pure-vector quaternions (v, 0).

    Do not normalize here: normalizing a pure vector would lose its length.
    R(left * right) = R(left) @ R(right) for unit rotation quaternions.
    """
    ax, ay, az, aw = _finite_values(left, 4)
    bx, by, bz, bw = _finite_values(right, 4)
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quaternion_inverse(quaternion: Sequence[float]) -> Quaternion:
    """Inverse of the normalized rotation quaternion: its conjugate."""
    x, y, z, w = normalize_quaternion(quaternion)
    return -x, -y, -z, w


def quaternion_rotate(quaternion: Sequence[float], vector: Sequence[float]) -> Vector3:
    """Rotate directly with q * (v, 0) * q^-1, without constructing a matrix."""
    q = normalize_quaternion(quaternion)
    x, y, z = _finite_values(vector, 3)
    result = quaternion_multiply(quaternion_multiply(q, (x, y, z, 0.0)), quaternion_inverse(q))
    return result[:3]


def rpy_to_quaternion(rpy: Sequence[float]) -> Quaternion:
    """Independent half-angle formula; does not call rpy_to_matrix."""
    rx, ry, rz = _finite_values(rpy, 3)
    cx, sx = math.cos(rx / 2.0), math.sin(rx / 2.0)
    cy, sy = math.cos(ry / 2.0), math.sin(ry / 2.0)
    cz, sz = math.cos(rz / 2.0), math.sin(rz / 2.0)
    return normalize_quaternion((
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    ))


def quaternion_to_matrix(quaternion: Sequence[float]) -> Matrix:
    x, y, z, w = normalize_quaternion(quaternion)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def matrix_to_quaternion(rotation: Sequence[Sequence[float]]) -> Quaternion:
    """Trace/largest-diagonal branches remain stable at 180-degree rotations."""
    _check_rotation(rotation)
    m = rotation
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        scale = 2.0 * math.sqrt(1.0 + trace)  # scale = 4*w
        quaternion = ((m[2][1] - m[1][2]) / scale,
                      (m[0][2] - m[2][0]) / scale,
                      (m[1][0] - m[0][1]) / scale, scale / 4.0)
    elif m[0][0] >= m[1][1] and m[0][0] >= m[2][2]:
        scale = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])  # 4*x
        quaternion = (scale / 4.0, (m[0][1] + m[1][0]) / scale,
                      (m[0][2] + m[2][0]) / scale, (m[2][1] - m[1][2]) / scale)
    elif m[1][1] >= m[2][2]:
        scale = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])  # 4*y
        quaternion = ((m[0][1] + m[1][0]) / scale, scale / 4.0,
                      (m[1][2] + m[2][1]) / scale, (m[0][2] - m[2][0]) / scale)
    else:
        scale = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])  # 4*z
        quaternion = ((m[0][2] + m[2][0]) / scale,
                      (m[1][2] + m[2][1]) / scale, scale / 4.0,
                      (m[1][0] - m[0][1]) / scale)
    return canonical_quaternion(quaternion)


def quaternion_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Sign-invariant L2 distance; q and -q describe the same rotation."""
    a, b = normalize_quaternion(left), normalize_quaternion(right)
    return min(math.dist(a, b), math.dist(a, tuple(-value for value in b)))


def make_transform(rotation: Sequence[Sequence[float]], translation: Sequence[float]) -> Matrix:
    _check_rotation(rotation)
    position = _finite_values(translation, 3)
    return tuple(tuple(rotation[i]) + (position[i],) for i in range(3)) + ((0.0, 0.0, 0.0, 1.0),)


def split_transform(transform: Sequence[Sequence[float]]) -> tuple[Matrix, Vector3]:
    if _shape(transform) != (4, 4):
        raise ValueError("A rigid transform must be 4 x 4.")
    if any(abs(a - b) > EPSILON for a, b in zip(transform[3], (0.0, 0.0, 0.0, 1.0))):
        raise ValueError("The final row of a rigid transform must be (0, 0, 0, 1).")
    rotation = tuple(tuple(row[:3]) for row in transform[:3])
    _check_rotation(rotation)
    return rotation, tuple(transform[i][3] for i in range(3))


def rigid_inverse(transform: Sequence[Sequence[float]]) -> Matrix:
    """(R, t)^-1 = (R.T, -R.T @ t), not (R.T, -t)."""
    rotation, translation = split_transform(transform)
    inverse_rotation = transpose(rotation)
    inverse_translation = tuple(-value for value in matvec(inverse_rotation, translation))
    return make_transform(inverse_rotation, inverse_translation)
