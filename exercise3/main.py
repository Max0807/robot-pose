"""Run exercise B3 and save UTF-8 reports and full-precision JSON."""

import argparse
import json
import sys
from pathlib import Path

from robot_pose.exercise3 import (
    POSE_LABELS, TOLERANCE, Exercise3Input, Exercise3Result, solve_exercise3,
)
from robot_pose.geometry import degrees


def format_vector(values, digits: int) -> str:
    # 只在显示时清理负零；计算和 JSON 保留完整精度。
    return "(" + ", ".join(
        f"{0.0 if abs(value) < 0.5 * 10 ** (-digits) else value:.{digits}f}" for value in values
    ) + ")"


def format_report(result: Exercise3Result) -> str:
    inputs, intrinsics = result.inputs, result.inputs.intrinsics
    lines = [
        "B3: 像素与深度 -> 相机系 -> 基座系 -> 抓取法兰目标",
        "约定: 平移 m; 内部角度 rad; R = Rz(rz) @ Ry(ry) @ Rx(rx); 四元数 xyzw",
        "深度为相机轴向 Z_c，忽略畸变；眼在手外，不使用机器人当前位姿。",
        "圆盘法向竖直向下，偏航角按抓取约定选取，不是视觉测量值。",
        "抓取公式: T_B_F = T_B_O @ inverse(T_F_G), T_G_O = I",
        "", "[题目输入]",
        f"图像分辨率: {intrinsics.width} x {intrinsics.height}",
        f"内参 (fx, fy, cx, cy) / px: {format_vector((intrinsics.fx, intrinsics.fy, intrinsics.cx, intrinsics.cy), 6)}",
        f"圆心像素 (u, v): {format_vector(inputs.pixel, 6)}; Z_c / m: {inputs.depth_m:.6f}",
        f"相机在基座下平移 / m: {format_vector(inputs.camera_translation, 6)}",
        f"相机 RPY / deg: {format_vector(degrees(inputs.camera_rpy), 6)}",
        f"夹持中心相对法兰平移 / m: {format_vector(inputs.gripper_translation, 6)}",
        f"夹持中心相对法兰 RPY / deg: {format_vector(degrees(inputs.gripper_rpy), 6)}",
        f"选定的工件 RPY / deg: {format_vector(degrees(inputs.object_rpy), 6)}",
    ]
    for name, path in (("矩阵路径", result.matrix_path), ("四元数路径", result.quaternion_path)):
        lines.extend([
            "", f"========== {name} ==========",
            f"相机系圆心 / m: {format_vector(path.camera_point, 6)}",
            f"基座系圆心 / m: {format_vector(path.base_point, 6)}",
            f"相机光轴在基座下的方向: {format_vector(path.camera_optical_axis_in_base, 12)}",
            f"工件 +Z 法向在基座下的方向: {format_vector(path.object_normal_in_base, 12)}",
        ])
        for stage, label in POSE_LABELS:
            pose = getattr(path, stage)
            lines.extend([
                "", f"[{label}]", f"平移 / m: {format_vector(pose.translation, 6)}",
                "旋转矩阵:", *("  " + format_vector(row, 12) for row in pose.rotation),
                f"RPY / rad: {format_vector(pose.rpy, 12)}",
                f"RPY / deg: {format_vector(degrees(pose.rpy), 6)}",
                f"四元数 (x, y, z, w): {format_vector(pose.quaternion, 12)}",
            ])
        lines.extend([
            "", f"逆变换恢复的相机系圆心 / m: {format_vector(path.recovered_camera_point, 12)}",
            f"重投影像素: {format_vector(path.reprojected_pixel, 9)}",
            f"恢复的 Z 深度 / m: {path.recovered_camera_point[2]:.12f}",
        ])
    lines.extend(["", f"[验证: 每项误差必须严格小于 {TOLERANCE:.1e}，单位见字段名]"])
    lines.extend(f"{name}: {error:.3e}  {'PASS' if error < TOLERANCE else 'FAIL'}"
                 for name, error in result.errors.items())
    lines.append(f"总体验证: {'PASS' if result.passed else 'FAIL'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="求解机器人应用第3题，输出视觉定位、抓取目标及双路径验证。")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "output",
                        help="结果目录，默认是 exercise3 项目下的 output。")
    args = parser.parse_args()
    try:
        inputs = Exercise3Input()
        result = solve_exercise3(inputs)
        report = format_report(result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        text_path, json_path = args.output_dir / "exercise3.txt", args.output_dir / "exercise3.json"
        text_path.write_text(report, encoding="utf-8")
        json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"运行失败: {error}", file=sys.stderr)
        return 1
    print(report, end="")
    print(f"文本结果: {text_path.resolve()}")
    print(f"完整精度 JSON: {json_path.resolve()}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
