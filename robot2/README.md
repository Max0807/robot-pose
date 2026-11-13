# 机器人应用实践：第2题

计算当前 TCP 和工件位姿、合并固定安装链，再求把工件放到目标位姿时法兰应该到达的位置与姿态。矩阵和四元数两条路径独立求解，并分别检查当前反解、放置回代和合并链。

本题完整项目位于 `D:\GithubCode\robot-pose\robot2`。第一题已经移到相邻的 `robot1`，第二题不导入第一题的代码。

## 1. 运行与结果文件

需要 Python 3.10 或以上。主程序只使用标准库，无需先安装 NumPy / SciPy。

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot2'
python main.py
```

当前机器也可显式指定已验证的解释器：

```powershell
& 'D:\software\Anaconda\python.exe' 'D:\GithubCode\robot-pose\robot2\main.py'
```

从总目录启动也可以：

```powershell
Set-Location 'D:\GithubCode\robot-pose'
python .\robot2\main.py
```

默认保存到第二题自己的目录：

- `D:\GithubCode\robot-pose\robot2\output\robot2.txt`：中文运行报告。
- `D:\GithubCode\robot-pose\robot2\output\robot2.json`：输入、约定、完整精度结果和误差。

每次运行更新这两个文件。计算和保存成功且所有验证通过时退出码为 0，验证失败或保存失败时为 1。

需要分别保存多次运行结果时：

```powershell
python main.py --output-dir 'D:\GithubCode\robot-pose\robot2\output\my-run'
```

## 2. 文件职责

```text
main.py                          第二题命令行入口、格式化和结果保存
robot_pose/
  geometry.py                    本题独立的矩阵、RPY、四元数和变换运算
  robot2.py                   输入、两个求解路径、六个阶段结果、误差验证
tests/
  test_geometry.py               基础数学、已知几何结果和奇异位置
  test_robot2.py              第二题答案、偏心、非零夹持姿态、路径独立性
  test_cli.py                    跨工作目录启动、结果归属、保存和失败退出
  test_scipy_reference.py         可选的 SciPy / NumPy 独立交叉验证
.vscode/launch.json              只打开 robot2 时可用的调试配置
requirements-validation.txt      可选验证依赖
output/                         本题实际运行生成的结果
```

建议阅读顺序：`Robot2Input` → `solve_matrix_path()` → `solve_quaternion_path()` → `solve_robot2()`，再查看它们调用的数学函数。

## 3. 约定与题目输入

- B：基座；F：法兰；G：夹爪夹持中心 / TCP；O：工件。
- 代码的 `T_A_B` 对应题面的 $T_A^B$，将 B 系坐标变换到 A 系。
- 右手坐标系，列向量；平移为米。
- 内部角度统一为弧度，题面度数通过 `radians(...)` 转换。
- RPY 按 `(rx, ry, rz)` 排列，$R=R_z(r_z)R_y(r_y)R_x(r_x)$。
- 四元数采用 Hamilton 乘法，顺序为 `(x, y, z, w)`。

| 变换 | 平移 / m | RPY / deg |
| --- | --- | --- |
| 当前法兰在基座下 $T_B^F$ | `(0.420, 0.150, 0.560)` | `(150, 0, 45)` |
| 夹持中心相对法兰 $T_F^G$ | `(0, 0, 0.165)` | `(0, 0, 90)` |
| 工件相对夹持中心 $T_G^O$ | `(0.025, 0, 0.060)` | `(0, 0, 0)` |
| 下料工件目标 $T_B^{O,target}$ | `(0.350, -0.450, 0.090)` | `(180, 0, 0)` |

与第一题相比，本题夹爪的安装角度是 90°，并且存在 25 mm 横向偏心和 60 mm 伸出量，不能沿用第一题的 45° 安装参数或 $T_G^O=I$。

“刚性夹持”表示 $T_G^O$ 在夹持期间固定。题面给定其姿态为零；程序也支持传入非零的固定夹持姿态，并有相应测试。

## 4. 矩阵路径的六个阶段

### 4.1 当前 TCP 位姿

$$T_B^G=T_B^F T_F^G$$

### 4.2 当前工件位姿

$$T_B^O=T_B^G T_G^O$$

TCP 和工件原点不重合，因此位置不同。由于本题 $R_G^O=I$，二者姿态相同。

### 4.3 合并固定安装链

$$T_F^O=T_F^G T_G^O$$

变换组合公式为：

$$R_F^O=R_F^G R_G^O$$

$$t_F^O=t_F^G+R_F^G t_G^O$$

本题 $R_F^G=R_z(90°)$，因此：

$$t_F^O=(0,0,0.165)+R_z(90°)(0.025,0,0.060)=(0,0.025,0.225)$$

25 mm 偏心是在夹爪系 X 方向，经过安装旋转后，变成法兰系 Y 方向。直接把两段平移相加会得到错误结果。

合并结果为：

$$T_F^O=\begin{bmatrix}0&-1&0&0\\1&0&0&0.025\\0&0&1&0.225\\0&0&0&1\end{bmatrix}$$

夹爪安装与工件夹持关系固定时，合并链可以缓存，用于重复正解和反解；程序在每次求解中合并一次，并复用其逆矩阵。这样可以减少重复组合、简化坐标关系并降低遗漏偏心的可能。换夹持位置或工件安装关系后，应更新这条常量链。

这里使用的是题目给定的安装参数及其合并结果，不需要额外采集标定数据。合并的 F→O 链对应此夹持方式；原始夹爪中心 F→G 与工件坐标系 F→O 应区分。

### 4.4 恢复当前法兰

$$T_B^{F,recovered}=T_B^O(T_F^O)^{-1}$$

应恢复题目给定的当前法兰。刚体变换的逆为：

$$(R,t)^{-1}=(R^\mathsf T,-R^\mathsf Tt)$$

### 4.5 下料法兰目标

$$\boxed{T_B^{F,target}=T_B^{O,target}(T_F^O)^{-1}}$$

这里必须使用整条 F→O 链，包含夹爪安装、25 mm 偏心和 60 mm 伸出量。

### 4.6 展开完整链回代下料工件

$$T_B^{O,reconstructed}=T_B^{F,target}T_F^G T_G^O$$

回代结果的位置和姿态都应与下料工件目标一致。

## 5. 四元数路径如何独立计算

用 `(q, t)` 表示一个刚体变换，四元数从输入 RPY 的半角公式直接构造。

两个变换的组合为：

$$q_{12}=q_1\otimes q_2$$

$$t_{12}=t_1+\operatorname{rotate}(q_1,t_2)$$

其中向量旋转直接使用四元数：

$$(v',0)=q\otimes(v,0)\otimes q^{-1}$$

逆变换为：

$$(q,t)^{-1}=(q^{-1},\operatorname{rotate}(q^{-1},-t))$$

`_compose_quaternions()` 和 `_inverse_quaternions()` 用这些公式独立完成同样六个阶段。全部求解结束后，才把结果转换成矩阵和 RPY，供输出和比较使用。

四元数求解不调用矩阵路径的输入旋转构造、矩阵组合或刚体矩阵求逆。测试会临时禁用这些函数，验证它仍能完成求解；矩阵路径也有相反方向的独立性检查。

## 6. 核对结果

两条路径应得到以下等价结果。表中的显示值经过四舍五入；验证和 JSON 使用完整精度。

| 阶段 | 平移 / m | 一组 RPY / deg |
| --- | --- | --- |
| 当前 TCP | `(0.478336, 0.091664, 0.417106)` | `(180, -30, -45)` |
| 当前工件 | `(0.514859, 0.055141, 0.377644)` | `(180, -30, -45)` |
| 合并安装链，工件相对法兰 | `(0, 0.025, 0.225)` | `(0, 0, 90)` |
| 恢复的当前法兰 | `(0.420000, 0.150000, 0.560000)` | `(150, 0, 45)` |
| 下料法兰目标 | `(0.325000, -0.450000, 0.315000)` | `(180, 0, 90)` |
| 下料工件回代结果 | `(0.350000, -0.450000, 0.090000)` | `(180, 0, 0)` |

TCP 和当前工件的一组四元数均为：

```text
(0.892399100833, -0.369643810614, 0.239117618394, 0.099045760541)
```

下料法兰的一组四元数为：

```text
(0.707106781187, 0.707106781187, 0, 0)
```

主程序还输出每个阶段的旋转矩阵、RPY 弧度值和四元数。

## 7. 验证标准和测试

程序共输出 30 项误差，逐项要求严格小于 `1e-9`：

- 六个阶段分别比较两条路径的平移、旋转矩阵、四元数，合计 18 项。
- 每条路径分别检查恢复当前法兰、下料工件回代、缓存链与逐段计算的等价性，每项各比较平移与旋转，合计 12 项。

平移使用各分量最大绝对差，单位 m；旋转使用矩阵元素最大绝对差。四元数使用 `min(norm(q1-q2), norm(q1+q2))`，允许 q 和 -q 表示同一个旋转。所有误差必须为有限数。

输出四元数归一化并选定等价符号；矩阵转四元数采用迹 / 最大对角元素四分支，处理 180° 旋转。RPY 奇异位置取 Yaw 为零，返回一组等价角度，比较使用矩阵。几何函数还检查旋转矩阵正交性和行列式 +1。

运行本题测试：

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot2'
python -m unittest discover -s tests -v
```

本次在 Python 3.12.4、SciPy 1.13.1 环境下，37 项测试全部通过。其中 4 项外部验证测试使用 SciPy / NumPy；未安装时会显示 `skipped`，其余 33 项标准库测试仍可执行。

启用外部验证：

```powershell
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
```

外部验证从原始输入独立构造变换，比较六个阶段的完整矩阵；还覆盖非零夹持姿态和固定种子的随机安装链。测试也包含手算偏移、零工具链、恒定安装链、非法输入、阈值边界以及从其他工作目录启动程序。

只调试下料目标的测试：

```powershell
python -m unittest tests.test_robot2.Robot2Tests.test_placement_flange_has_expected_answer -v
```

## 8. VS Code 调试

安装 Microsoft Python 扩展，确认 Python Debugger 可用，并选择实际使用的 Python 解释器。

如果打开的是总目录 `D:\GithubCode\robot-pose`，选择根目录配置“第2题：调试正解与下料”；它已指定第二题入口和工作目录。如果只打开 `robot2`，使用该题自带的同名配置即可。

推荐断点均位于 `robot_pose/robot2.py`：

1. `inverse_tool = rigid_inverse(flange_object)`：停下时 `flange_object` 已合并，最后一列前三项应约为 `(0, 0.025, 0.225)`。
2. `reconstructed_target_object = ...`：停下时 `target_flange` 已计算，最后一列前三项应约为 `(0.325, -0.450, 0.315)`；单步执行后检查下料工件回代结果。
3. 四元数路径的 `flange_object = _compose_quaternions(...)`：进入函数后观察 25 mm 偏心如何由夹爪 X 方向变为法兰 Y 方向。

F5 启动 / 继续；F10 单步执行；F11 进入函数。变量窗口可展开 4×4 元组；行的最后一个元素是该行的平移分量，最后一行为 `(0, 0, 0, 1)`。

修改参数试算时，建议在 `main.py` 的 `inputs = Robot2Input(...)` 处显式传入参数，保留题面默认值供测试使用。角度参数应先用 `robot_pose.geometry.radians(...)` 转换。不要把度数直接传给内部弧度字段。

## 9. 命令行 pdb 调试

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot2'
python -m pdb main.py
```

出现 `(Pdb)` 后输入：

```text
b robot_pose/robot2.py:139
b robot_pose/robot2.py:144
c
p flange_object
c
p target_flange
n
p reconstructed_target_object
c
q
```

139、144 是当前版本对应的两处断点行号；修改源文件后按实际行号调整。`c` 继续，`n` 执行一行，`s` 进入函数，`p` 打印变量，`l` 查看代码，`q` 退出。程序正常结束后 pdb 会回到入口，最后用 `q` 退出即可。

## 10. 常见问题和提交材料

- 运行入口是本题 `main.py`，不要直接执行包内 `robot_pose/robot2.py`。
- 运行测试前进入 `robot2`，第一题测试则进入 `robot1`。两题按独立项目运行。
- 所有结果文件均为 UTF-8；若旧终端显示异常，可用编辑器以 UTF-8 打开文本结果。
- 浮点尾数如 `0.02500000000000001` 属于正常表示。显示阶段才保留六位小数，不能提前舍入或放宽误差阈值。
- 可提交本题整个目录，附实际运行命令、关键结果和 `PASS` 的截图或录屏。`output` 中已经保存实际执行结果。

外部验证遵循 [SciPy 旋转轴序约定](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.from_euler.html) 与 [四元数顺序及等价符号](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.as_quat.html)。调试参考 [Python pdb](https://docs.python.org/3/library/pdb.html) 和 [VS Code Python 调试](https://code.visualstudio.com/docs/python/debugging)。
