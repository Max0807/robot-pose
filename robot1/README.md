# 机器人应用实践：第1题

已知工件在机器人基座下的位姿，以及夹爪相对法兰的安装关系，计算法兰在基座下的位姿。

实现包含矩阵、四元数两条独立求解路径，输出平移、旋转矩阵、RPY、四元数，并进行交叉验证与回代。

## 1. 运行

需要 Python 3.10 或以上。主程序只使用 Python 标准库，不需要安装 NumPy / SciPy。

在 PowerShell 中执行：

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot1'
python main.py
```

当前机器已验证的解释器为 Python 3.12.4。如果 `python` 没有指向可用解释器，可以显式执行：

```powershell
& 'D:\software\Anaconda\python.exe' 'D:\GithubCode\robot-pose\robot1\main.py'
```

程序将打印两条路径的全部结果与误差，并保存：

- `output/robot1.txt`：便于阅读和截图的中文结果。
- `output/robot1.json`：包含输入、约定、两条路径结果、误差的完整精度数据。

默认输出目录相对于 `main.py` 所在目录确定。从其他目录启动，结果仍保存到项目的 `output` 下。

也可以指定目录：

```powershell
python main.py --output-dir 'D:\GithubCode\robot-pose\robot1\output\my-run'
```

每次运行会更新指定目录下的这两个结果文件。所有验证通过时退出码为 0，验证失败或保存失败时为 1。

## 2. 文件职责与阅读顺序

```text
main.py                         命令行入口、结果显示、保存文件
robot_pose/
  geometry.py                   自行实现的矩阵、RPY、四元数和刚体变换运算
  robot1.py                  题目输入、矩阵求解、四元数求解、误差验证
tests/
  test_geometry.py              已知几何结果、边界与输入检查
  test_robot1.py             本题答案、一般安装偏移、双路径独立性
  test_cli.py                   运行入口、中文输出、完整精度保存、失败退出
  test_scipy_reference.py        可选的 SciPy / NumPy 外部交叉验证
.vscode/launch.json             VS Code 的程序和测试调试配置
requirements-validation.txt     可选验证依赖
output/                         实际运行生成的结果
```

建议先看 `robot1.py` 中的 `Robot1Input` 和两个 `solve_*_path` 函数，再按调用关系阅读 `geometry.py`，最后查看 `main.py` 如何输出。

## 3. 坐标、单位与输入

- 右手坐标系，使用列向量。
- B：Base，基座；F：Flange，法兰；G：Gripper，夹持中心；O：Object，工件。
- 代码中的 `T_A_B` 对应题面的 $T_A^B$，将 B 系坐标变换到 A 系。
- 平移单位为米；代码内部角度统一为弧度。
- RPY 顺序为 `(rx, ry, rz)`，公式固定为 $R=R_z(r_z)R_y(r_y)R_x(r_x)$。
- 四元数采用 Hamilton 乘法，顺序为 `(x, y, z, w)`。
- 本题给定 $T_G^O=I$，即工件与夹持中心的原点、轴向都重合。

| 变换 | 平移 / m | RPY / deg |
| --- | --- | --- |
| 工件在基座下：$T_B^O$ | `(0.520, -0.180, 0.120)` | `(180, 0, -30)` |
| 夹持中心在法兰下：$T_F^G$ | `(0, 0, 0.165)` | `(0, 0, 45)` |

输入定义在 `Robot1Input`，题面角度通过 `radians(...)` 转换后保存。修改输入时应保留这个转换，不能直接把度数填进弧度字段。

本题的“反解”求出法兰位姿；题目已给出所有相关安装参数。

## 4. 矩阵路径的推导

齐次变换表示为：

$$T=\begin{bmatrix}R&t\\0&1\end{bmatrix}$$

安装链为：

$$T_B^O=T_B^F T_F^G T_G^O=T_B^F T_F^G$$

所以：

$$\boxed{T_B^F=T_B^O(T_F^G)^{-1}}$$

刚体变换求逆与组合分别为：

$$ (R,t)^{-1}=(R^\mathsf{T},-R^\mathsf{T}t) $$

$$ (R_1,t_1)(R_2,t_2)=(R_1R_2,t_1+R_1t_2) $$

`solve_matrix_path()` 从输入 RPY 构造两个 4×4 矩阵，再求逆、相乘，得到法兰位姿。矩阵相乘、求逆及姿态转换均在本项目中实现。

## 5. 四元数路径为什么是独立的

`solve_quaternion_path()` 直接使用输入 RPY 的半角公式构造四元数，不读取矩阵路径的中间值或答案。

先求法兰朝向：

$$q_B^F=q_B^O\otimes(q_F^G)^{-1}$$

对单位旋转四元数，求逆等于取共轭。再用四元数直接旋转安装偏移：

$$v_B=q_B^F\otimes(t_F^G,0)\otimes(q_B^F)^{-1}$$

取结果的前三个分量，计算：

$$t_B^F=t_B^O-v_B$$

只有完成求解后，才把最终四元数转换为矩阵，供展示和比较使用。两条路径共用输入、输出表示转换及误差检查；核心旋转与平移求解分别完成。

`quaternion_multiply()` 不会自动归一化乘积，因为这里还需要处理 `(v, 0)` 这种带长度的纯向量四元数。错误归一化会破坏 0.165 m 的安装偏移。

## 6. 数值结果与验证规则

法兰在基座下的平移为：

```text
(0.520000, -0.180000, 0.285000) m
```

旋转矩阵为：

```text
 0.965925826289   0.258819045103   0
 0.258819045103  -0.965925826289   0
 0                0              -1
```

一组等价的 RPY 与四元数为：

```text
RPY / deg = (180, 0, 15)
RPY / rad = (3.141592653590, 0, 0.261799387799)
q (x,y,z,w) = (0.991444861374, 0.130526192220, 0, 0)
```

几何检查：夹爪朝下，夹持中心比法兰低 0.165 m，因此法兰高度为 `0.120 + 0.165 = 0.285 m`。RPY 不能按分量直接相减。

程序检查以下误差，每项必须严格小于 `1e-9`：

| 输出字段 | 定义与单位 |
| --- | --- |
| `paths_translation_max_abs_m` | 两条路径平移分量最大绝对差，单位 m |
| `paths_rotation_max_abs` | 两条路径旋转矩阵元素最大绝对差，无量纲 |
| `paths_quaternion_sign_invariant_l2` | `min(norm(q1-q2), norm(q1+q2))`，无量纲 |
| `matrix_roundtrip_translation_max_abs_m` | 矩阵路径回代后，工件平移最大绝对误差，单位 m |
| `matrix_roundtrip_rotation_max_abs` | 矩阵路径回代后，工件旋转矩阵最大元素误差 |
| `quaternion_roundtrip_translation_max_abs_m` | 四元数路径回代后的工件平移误差，单位 m |
| `quaternion_roundtrip_rotation_max_abs` | 四元数路径回代后的工件旋转矩阵误差 |

回代使用 $T_B^F T_F^G\approx T_B^O$。输入和构造的旋转矩阵还检查正交性、行列式为 +1，避免将反射矩阵误认为旋转。

内部保留 Python 浮点数的完整精度，平移最后显示为六位小数。JSON 中保留实际浮点值，例如 `0.28500000000000003`；这种尾数属于正常浮点表示。

矩阵转四元数采用矩阵迹和最大对角元素的四分支算法，能够处理本题的 180° 旋转。四元数输出归一化后优先选取正 w；w 接近零时，选取向量部分第一个非零分量为正的等价符号。比较始终允许 q 与 -q 等价。

RPY 返回的 Pitch 在 `[-pi/2, pi/2]`，Roll 与 Yaw 在 `[-pi, pi]`。Pitch 为 ±90° 的奇异位置统一取 Yaw 为零，返回一组等价角度；验证通过重建矩阵完成，不要求角度分量相等。本题的 Roll=180° 本身不是万向节锁。

## 7. 运行测试与外部交叉验证

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot1'
python -m unittest discover -s tests -v
```

基础测试只需标准库。它们包含手算的 90° 旋转、180° 四元数各分支、带旋转的平移组合、刚体逆变换、RPY 奇异位置、双路径求解、非法输入以及命令行实际执行等检查。

如果当前解释器可以导入 SciPy，还会自动执行外部验证：使用 SciPy / NumPy 独立计算转换、旋转组合、向量旋转、逆矩阵及本题的完整答案。随机旋转使用固定种子，以保证可复现。

如果没有 SciPy，这四个外部验证测试显示 `skipped`，其余测试照常运行。需要启用外部验证时，在所用 Python 环境中执行：

```powershell
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
```

只检查一个重点测试：

```powershell
python -m unittest tests.test_geometry.GeometryTests.test_matrix_to_quaternion_all_four_branches -v
```

## 8. 调试：VS Code

1. 打开整个文件夹 `D:\GithubCode\robot-pose\robot1`。
2. 安装 Microsoft 的 Python 扩展，并确认 Python Debugger 扩展可用。
3. 在命令面板选择 `Python: Select Interpreter`，选择实际运行测试的解释器。当前机器可选 `D:\software\Anaconda\python.exe`。
4. 打开 `robot_pose/robot1.py`，在 `base_flange = matmul(...)` 这一行左侧单击，设置断点。
5. 在“运行和调试”中选择“第1题：调试计算过程”，按 F5。
6. 停下后检查 `base_object`、`flange_gripper`；按 F10 执行当前行，再查看 `base_flange`。F11 可进入函数，F5 继续运行。
7. 在四元数路径的 `offset_in_base = ...` 处再加断点，单步后该变量应约为 `(0, 0, -0.165)`，随后计算出的法兰高度应为 0.285。

推荐观察的变量：

| 变量 | 应关注什么 |
| --- | --- |
| `inputs.object_rpy` | 已经是弧度，而不是 180、0、-30 |
| `base_object` | 工件在基座下的 4×4 变换 |
| `flange_gripper` | 安装偏移沿法兰 Z 轴 |
| `base_flange` | 法兰求解结果，最后一列前三项为位置 |
| `base_flange_q` | 直接由四元数组合算出的法兰朝向 |
| `offset_in_base` | 安装偏移在基座下朝向下方 |
| `result.errors` | 所有误差均应小于 `1e-9` |

也可以选择“运行全部单元测试”配置，给某个测试或数学函数设置断点。不要直接运行 `robot_pose/robot1.py`：它是包内模块，项目的程序入口是 `main.py`。

## 9. 调试：不依赖编辑器的 pdb

在项目目录运行：

```powershell
python -m pdb main.py
```

出现 `(Pdb)` 后，依次输入下面的命令。这里的 94 是当前版本矩阵求解语句的行号；修改文件后应按实际行号调整。

```text
b robot_pose/robot1.py:94
c
p base_object
p flange_gripper
n
p base_flange
c
q
```

- `b 文件:行号`：设置断点。
- `c`：继续运行到断点或结束。
- `n`：执行当前行，不进入被调用函数。
- `s`：单步进入函数。
- `p 表达式`：查看变量或表达式。
- `l`：查看附近源代码。
- `q`：退出调试器。

命令行 pdb 在程序结束后会回到入口，因此最后使用 `q` 退出。

## 10. 运行材料与常见问题

- 截图建议包含运行命令、法兰结果、两条路径误差和 `PASS`。完整输出可在 `output/robot1.txt` 中查看；截图应来自实际执行。
- 若出现模块找不到，先切换到项目根目录，使用 `python main.py`，不要直接运行包内文件。
- 若选择了不同的 Python 环境，SciPy 是否可用也可能不同。使用 `python -m pip` 可使安装目标与该解释器一致。
- 终端和结果文件均输出 UTF-8。若旧终端显示异常，可以用编辑器以 UTF-8 打开 `output/robot1.txt`；旧 PowerShell 通过管道读取时应确保其编码也为 UTF-8。
- 如果测试失败，先看失败的测试名和最大误差，再在相应数学函数处设断点。不要通过提前四舍五入或放宽 `1e-9` 阈值来掩盖问题。

参考约定：[SciPy 固定轴/随动轴与角度单位](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.from_euler.html)、[四元数顺序与等价符号](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.as_quat.html)、[Python pdb](https://docs.python.org/3/library/pdb.html)、[VS Code Python 调试](https://code.visualstudio.com/docs/python/debugging)。
