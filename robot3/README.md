# 机器人应用实践：第3题

使用给定像素、轴向深度、相机内参和眼在手外标定结果，求圆盘中心在基座下的位置，再按选定的抓取姿态求法兰目标。相机外参和工具反解分别用矩阵、四元数独立计算，并检查逆变换、重投影和抓取回代。

独立项目路径为 `D:\GithubCode\robot-pose\robot3`，包含自己的数学模块、测试、结果和调试配置。

## 1. 运行

需要 Python 3.10 或以上，主程序只使用标准库。

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot3'
python main.py
```

也可以从总目录启动：

```powershell
Set-Location 'D:\GithubCode\robot-pose'
python .\robot3\main.py
```

当前机器已验证的解释器是 Python 3.12.4，可显式指定：

```powershell
& 'D:\software\Anaconda\python.exe' 'D:\GithubCode\robot-pose\robot3\main.py'
```

结果固定保存到本题默认输出目录，与终端所在目录无关：

- `D:\GithubCode\robot-pose\robot3\output\robot3.txt`：中文结果、公式说明和验证误差。
- `D:\GithubCode\robot-pose\robot3\output\robot3.json`：输入、约定、两条路径的完整精度结果。

每次运行更新这两个文件。所有数值检查通过且保存成功时退出码为 0，否则为 1。

如需保留多次试算结果：

```powershell
python main.py --output-dir 'D:\GithubCode\robot-pose\robot3\output\my-run'
```

## 2. 文件职责与阅读顺序

```text
main.py                          第三题入口、中文报告和文件保存
robot_pose/
  camera.py                      相机内参、像素反投影、重投影、输入检查
  geometry.py                    本题独立的矩阵、RPY、四元数和刚体运算
  robot3.py                   题面输入、双路径求解和验证
tests/
  test_camera.py                 反投影、焦距、像素、轴向深度及非法输入
  test_geometry.py               已知旋转、180° 转换、RPY 奇异位置等
  test_robot3.py              本题答案、一般外参、抓取约定和路径独立性
  test_cli.py                    跨目录启动、文件归属、完整精度和失败退出
  test_scipy_reference.py         可选 SciPy / NumPy 外部交叉验证
.vscode/launch.json              只打开 robot3 时的程序 / 测试调试配置
requirements-validation.txt      可选验证依赖
output/                         实际运行生成的第三题结果
```

推荐先阅读 `Robot3Input`、`backproject_pixel()`，再看 `solve_matrix_path()`、`solve_quaternion_path()`，最后查看 `solve_robot3()` 的误差检查。

## 3. 坐标、单位与输入

- B：机器人基座；C：相机；F：法兰；G：夹持中心；O：工件。
- 代码的 `T_A_B` 对应题面的 $T_A^B$，把 B 系坐标变换到 A 系。
- 右手坐标系，列向量；平移单位 m，内部角度统一为弧度。
- RPY 顺序 `(rx, ry, rz)`，$R=R_z(r_z)R_y(r_y)R_x(r_x)$。
- 四元数使用 Hamilton 乘法，顺序 `(x, y, z, w)`。
- 相机使用题面针孔模型，按要求忽略畸变。

| 输入 | 数值 |
| --- | --- |
| 图像尺寸 | `1280 × 720` |
| 内参 / px | `fx=800, fy=800, cx=640, cy=360` |
| 圆心像素 / px | `(720, 280)` |
| 轴向深度 Zc / m | `0.400` |
| 相机在基座下的平移 / m | `(0.700, -0.200, 1.000)` |
| 相机 RPY / deg | `(180, 0, 15)` |
| 夹持中心相对法兰平移 / m | `(0, 0, 0.165)` |
| 夹持中心相对法兰 RPY / deg | `(0, 0, 45)` |
| 选定工件姿态 RPY / deg | `(180, 0, 0)` |

使用本题的 45° 夹爪安装关系。第二题的 90° 安装、25 mm 偏心和 60 mm 伸出量不适用于这里。

## 4. 像素到相机系

针孔内参矩阵为：

$$K=\begin{bmatrix}f_x&0&c_x\\0&f_y&c_y\\0&0&1\end{bmatrix}$$

题目明确深度是相机 Z 坐标，因此：

$$x_c=(u-c_x)Z_c/f_x,\quad y_c=(v-c_y)Z_c/f_y,\quad z_c=Z_c$$

得到：

$$\boxed{p_C=(0.040000,-0.040000,0.400000)\ \mathrm m}$$

Zc 与到相机原点的欧氏距离含义不同。这里相机系 Y 坐标为负，由给定像素和公式自然得到。

输入策略：fx、fy 必须为正；深度必须有限且大于零；检测像素必须有限且在 `[0,width) × [0,height)` 内。不自动裁剪、不添加半像素偏移。允许亚像素坐标。投影函数用于几何检查，可以返回图像外的像素位置，且不裁剪。

相机内参和检测像素必须对应同一图像分辨率与坐标系。实际改变图像尺寸或裁剪范围时，需要相应更新内参。

## 5. 相机系到基座系

题面给出的是相机在基座下的位姿 $T_B^C$，可以直接使用：

$$\boxed{p_B=R_B^C p_C+t_B^C}$$

相机固定在工位上，所以 $T_B^C$ 与机器人当前位姿无关；程序输入中也没有当前机器人位姿。

本题得到：

$$\boxed{p_B=(0.728284271247,-0.151010205144,0.600000000000)\ \mathrm m}$$

点使用齐次坐标 `(x, y, z, 1)`，使平移生效。光轴和法向是方向，只乘旋转部分。程序输出相机 +Z 光轴在基座下的方向，当前参数应约为 `(0,0,-1)`。

直观检查：相机高度 1.000 m、光轴向下，圆心轴向深度 0.400 m，因此圆心高度为 0.600 m。代码仍使用完整外参，并有非垂直相机姿态测试。

## 6. 工件姿态的来源

视觉像素和深度确定圆心三维位置。圆盘平放且法向已知竖直，绕法向旋转不影响抓取，因此按题意选择：

$$RPY_O=(180°,0°,0°)$$

工件 +Z 指向下方，与试题约定一致。绕竖直方向的角度是选定的抓取约定，不是视觉测量结果。长条工件的长轴方向影响夹爪对齐，通常还需提供方向信息；本题圆盘的旋转对称性使这个角度不受抓取约束。

`Robot3Input.object_yaw` 是可选的偏航角，单位 rad，默认零；工件 Roll 固定为 pi、Pitch 固定为零，保持法向向下。测试覆盖其他偏航角，验证它不改变圆心位置。

JSON 与中文报告均明确记录这个姿态选取过程，避免把输出的完整位姿误认为全部由视觉测得。

## 7. 抓取法兰反解

按题目给出的抓取公式，夹持中心与工件圆心重合，并按目标工件坐标系对齐，即 $T_G^O=I$：

$$T_B^O=T_B^F T_F^G$$

$$\boxed{T_B^F=T_B^O(T_F^G)^{-1}}$$

反解结果为：

```text
法兰平移 / m = (0.728284, -0.151010, 0.765000)
法兰 RPY / deg = (180, 0, 45)
法兰 RPY / rad = (3.141592653590, 0, 0.785398163397)
四元数 (x,y,z,w) = (0.923879532511, 0.382683432365, 0, 0)
```

法兰旋转矩阵为：

```text
 0.707106781187   0.707106781187   0
 0.707106781187  -0.707106781187   0
 0                0              -1
```

法兰高于圆心 0.165 m，与朝下的夹爪安装偏移一致。主程序同时输出工件位姿、法兰目标和回代夹持中心的完整旋转矩阵、RPY、四元数。

## 8. 两条路径与验证方式

反投影是公共输入转换；外参和法兰反解分别完成：

- 矩阵路径：从输入 RPY 构造矩阵，使用齐次点变换，按刚体逆变换公式求法兰。
- 四元数路径：从输入 RPY 的半角公式直接构造四元数，用 `q * (v,0) * q^-1` 处理相机点和工具偏移，求解完成后才转换为矩阵用于展示和比较。

四元数路径的核心公式为：

$$p_B=t_B^C+\operatorname{rotate}(q_B^C,p_C)$$

$$q_B^F=q_B^O\otimes(q_F^G)^{-1}$$

$$t_B^F=p_B-\operatorname{rotate}(q_B^F,t_F^G)$$

程序输出 26 项误差：

- 两条路径的相机点、基座点、光轴、工件法向比较，共 4 项。
- 工件、法兰目标、回代夹持中心的平移、旋转矩阵、四元数比较，共 9 项。
- 原始反投影点直接重新投影的像素误差，1 项。
- 每条路径检查相机逆变换、重投影像素、深度、抓取中心、抓取姿态和工件法向，各 6 项，共 12 项。

抓取回代会从最终法兰位姿重新计算 $T_B^F T_F^G$，检查它是否等于工件目标；不只依赖求解器先前保存的回代值。

每项误差必须有限且严格小于 `1e-9`。平移和深度误差单位 m，像素误差单位 px，旋转矩阵、单位方向和四元数误差无量纲。这个阈值用于数值计算的一致性验证。

四元数比较允许 q 和 -q 等价。RPY 通过矩阵验证，避免角度周期与奇异位置造成误判。内部保持完整浮点精度，只在显示时保留规定小数位。

## 9. 测试和可选外部验证

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot3'
python -m unittest discover -s tests -v
```

在 Python 3.12.4、SciPy 1.13.1 环境下，49 项测试全部通过。其中 4 项使用外部库，未安装 SciPy 时显示 `skipped`，其余 45 项标准库测试可正常执行。

启用可选外部验证：

```powershell
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
```

外部验证使用 NumPy 的 `inverse(K) @ (u,v,1)` 独立检查反投影，用 SciPy 从原始外参和工具参数构造旋转，再比较圆心、方向和完整抓取变换。还覆盖不同焦距、一般相机姿态、非轴向工具偏移、其他选定偏航角和固定种子的随机输入。

基础测试还检查：主点像素、亚像素、轴向深度、图像边界、非有限输入、180° 四元数转换、RPY 奇异位置、路径独立性，以及“两条路径给出相同错误法兰时，最终回代仍能发现错误”。

只运行本题答案测试：

```powershell
python -m unittest tests.test_robot3.Robot3Tests.test_given_problem_has_expected_answer -v
```

## 10. VS Code 调试

安装 Microsoft Python 扩展，确认 Python Debugger 可用，选择实际运行测试的解释器。

可以打开总目录 `D:\GithubCode\robot-pose`，选择“第3题：调试视觉定位与抓取”；也可以只打开 `robot3`，使用本题自带的同名配置。

在 `robot_pose/robot3.py` 中设置断点：

1. `base_point = matvec(...)`，当前第 140 行：查看 `camera_point` 和 `base_camera`，执行后查看 `base_point`。
2. `reconstructed_gripper = matmul(...)`，当前第 145 行：查看已经算出的 `target_flange`，再执行并查看夹持中心回代。
3. 四元数路径的 `offset_in_base = ...`：查看安装偏移如何转到基座下，当前题面应约为 `(0,0,-0.165)`。

F5 启动 / 继续，F10 执行一行，F11 进入函数。矩阵最后一列前三项是位置；光轴和工件法向则是单位方向。

试算其他输入时，可在 `main.py` 的 `inputs = Robot3Input(...)` 处显式传参，保留题面的默认值供回归测试。角度参数使用弧度；例如 `object_yaw=math.radians(60)`，或使用 `robot_pose.geometry.radians(...)` 转换三个 RPY 角。

## 11. 命令行 pdb 调试

```powershell
Set-Location 'D:\GithubCode\robot-pose\robot3'
python -m pdb main.py
```

出现 `(Pdb)` 后输入：

```text
b robot_pose/robot3.py:140
b robot_pose/robot3.py:145
c
p camera_point
n
p base_point
c
p target_flange
n
p reconstructed_gripper
c
q
```

修改代码后，断点行号按实际位置调整。`c` 继续，`n` 执行一行，`s` 进入函数，`p` 打印变量，`l` 查看附近代码，`q` 退出。程序结束后 pdb 会回到入口，最后用 `q` 退出即可。

## 12. 结果材料与常见问题

- 入口是本题 `main.py`，不要直接执行包内的 `robot3.py`。
- 测试在 `robot3` 下运行；第一、二题分别进入各自目录，避免同名包混合导入。
- UTF-8 文本结果包含实际运行输出，可在编辑器中查看；截图或录屏应包含运行命令、关键坐标、法兰结果和 `PASS`。
- JSON 保留实际浮点值，尾数如 `0.6000000000000001` 属于正常表示，不应提前舍入。
- 若输入无效，程序明确报错；相机内参必须与像素所来自的图像对应，深度必须使用米和轴向 Z 定义。

外部验证遵循 [SciPy 轴序与角度单位](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.from_euler.html) 及 [四元数顺序和符号等价性](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.as_quat.html)。调试参考 [Python pdb](https://docs.python.org/3/library/pdb.html) 和 [VS Code Python 调试](https://code.visualstudio.com/docs/python/debugging)。
