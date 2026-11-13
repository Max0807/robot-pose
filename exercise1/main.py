"""Run exercise B1 and save reproducible text / full-precision JSON results."""

import argparse
import json
import sys
from pathlib import Path

from robot_pose.exercise1 import TOLERANCE, Exercise1Input, Exercise1Result, solve_exercise1
from robot_pose.geometry import degrees


def format_vector(values, digits: int) -> str:
    # Clean negative zero for display only; retain full precision in calculations / JSON.
    return "(" + ", ".join(
        f"{0.0 if abs(value) < 0.5 * 10 ** (-digits) else value:.{digits}f}" for value in values
    ) + ")"


def format_report(result: Exercise1Result) -> str:
    lines = [
        "B1: 工件位姿 -> 法兰位姿",
        "约定: 平移 m; 内部角度 rad; R = Rz(rz) @ Ry(ry) @ Rx(rx); 四元数 xyzw",
        "公式: T_B_F = T_B_O @ inverse(T_F_G), T_G_O = I",
        "",
        "[输入]",
        f"工件在基座下的平移 / m: {format_vector(result.inputs.object_translation, 6)}",
        f"工件 RPY / deg: {format_vector(degrees(result.inputs.object_rpy), 6)}",
        f"夹持中心相对法兰平移 / m: {format_vector(result.inputs.gripper_translation, 6)}",
        f"夹持中心相对法兰 RPY / deg: {format_vector(degrees(result.inputs.gripper_rpy), 6)}",
    ]
    for name, solution in (("矩阵路径", result.matrix_path), ("四元数路径", result.quaternion_path)):
        lines.extend([
            "", f"[{name}: 法兰在基座下的位姿]",
            f"平移 / m: {format_vector(solution.translation, 6)}",
            "旋转矩阵:",
            *("  " + format_vector(row, 12) for row in solution.rotation),
            f"RPY / rad: {format_vector(solution.rpy, 12)}",
            f"RPY / deg: {format_vector(degrees(solution.rpy), 6)}",
            f"四元数 (x, y, z, w): {format_vector(solution.quaternion, 12)}",
        ])
    lines.extend(["", f"[验证: 每项误差必须严格小于 {TOLERANCE:.1e}]"])
    for name, error in result.errors.items():
        lines.append(f"{name}: {error:.3e}  {'PASS' if error < TOLERANCE else 'FAIL'}")
    lines.append(f"总体验证: {'PASS' if result.passed else 'FAIL'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    # UTF-8 files are used below. Keep console text readable even in legacy terminals.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="求解机器人应用第1题，输出双路径结果与误差。")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "output",
        help="结果保存目录，默认是项目目录下的 output。",
    )
    args = parser.parse_args()
    try:
        # Change inputs here (or in Exercise1Input), always keeping internal angles in radians.
        inputs = Exercise1Input()
        result = solve_exercise1(inputs)
        report = format_report(result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        text_path = args.output_dir / "exercise1.txt"
        json_path = args.output_dir / "exercise1.json"
        text_path.write_text(report, encoding="utf-8")
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as error:
        print(f"运行失败: {error}", file=sys.stderr)
        return 1
    print(report, end="")
    print(f"文本结果: {text_path.resolve()}")
    print(f"完整精度 JSON: {json_path.resolve()}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
