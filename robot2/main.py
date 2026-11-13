"""Run robot task B2 and save UTF-8 reports and full-precision JSON."""

import argparse
import json
import sys
from pathlib import Path

from robot_pose.robot2 import (
    STAGE_LABELS, TOLERANCE, Robot2Input, Robot2Result, solve_robot2,
)
from robot_pose.geometry import degrees


def format_vector(values, digits: int) -> str:
    # 只在显示时清理负零；实际计算和 JSON 不截断。
    return "(" + ", ".join(
        f"{0.0 if abs(value) < 0.5 * 10 ** (-digits) else value:.{digits}f}" for value in values
    ) + ")"


def format_report(result: Robot2Result) -> str:
    lines = [
        "B2: 法兰位姿 -> TCP / 工件位姿 -> 下料法兰目标",
        "约定: 平移 m; 内部角度 rad; R = Rz(rz) @ Ry(ry) @ Rx(rx); 四元数 xyzw",
        "正解: T_B_G = T_B_F @ T_F_G; T_B_O = T_B_G @ T_G_O",
        "合并: T_F_O = T_F_G @ T_G_O",
        "反解: T_B_F_target = T_B_O_target @ inverse(T_F_O)",
        "", "[题目输入]",
    ]
    for label, translation, rpy in (
        ("法兰在基座下 T_B_F", result.inputs.flange_translation, result.inputs.flange_rpy),
        ("夹持中心相对法兰 T_F_G", result.inputs.gripper_translation, result.inputs.gripper_rpy),
        ("工件相对夹持中心 T_G_O", result.inputs.object_translation, result.inputs.object_rpy),
        ("下料工件目标 T_B_O_target", result.inputs.target_translation, result.inputs.target_rpy),
    ):
        lines.append(f"{label}: 平移 / m {format_vector(translation, 6)}, RPY / deg {format_vector(degrees(rpy), 6)}")

    for path_name, path in (("矩阵路径", result.matrix_path), ("四元数路径", result.quaternion_path)):
        lines.extend(["", f"========== {path_name} =========="])
        for stage, label in STAGE_LABELS:
            solution = getattr(path, stage)
            lines.extend([
                "", f"[{label}]",
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="求解机器人应用第2题，输出正解、下料反解及双路径验证。")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "output",
        help="结果保存目录，默认是 robot2 项目下的 output。",
    )
    args = parser.parse_args()
    try:
        inputs = Robot2Input()
        result = solve_robot2(inputs)
        report = format_report(result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        text_path = args.output_dir / "robot2.txt"
        json_path = args.output_dir / "robot2.json"
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
