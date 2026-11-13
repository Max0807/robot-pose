# A1：Three.js 三维场景与外部程序驱动

独立项目目录：`D:\GithubCode\robot-pose\software_a1`。

浏览器显示三维方块；独立 Python 程序通过 HTTP 下发目标位置和速度，Python 服务通过 WebSocket 转发，页面逐段匀速移动并返回到达回执。

本项目采用已确认的规则：可配置多点折线路径；每段直线匀速，到点停止并确认后再发送下一段。1 个场景单位代表 1 m，速度单位 m/s，Y 轴向上，地面为 XZ 平面，方块边长 0.4 m，默认中心高度 0.2 m。

## 1. 最快运行方式

本机已经创建了项目专用 `.venv` 并安装锁定依赖。打开两个 PowerShell 终端，依次操作。

**终端一：启动服务，保持运行。**

```powershell
Set-Location 'D:\GithubCode\robot-pose\software_a1'
.\.venv\Scripts\python.exe server.py
```

在 Chrome / Edge 中打开 [本地三维页面](http://127.0.0.1:8000/)，等待右上角显示“已连接”，保持该页面在前台。

**终端二：运行真正独立的外部控制程序。**

```powershell
Set-Location 'D:\GithubCode\robot-pose\software_a1'
.\.venv\Scripts\python.exe controller.py
```

方块应依次经过四个路段。终端会打印每段“已接收”和“已到达”，最终显示：

```text
全部路段已到达：PASS
```

页面显示当前位置、目标位置、速度、运动时间、进度、命令编号、规划路径、已走轨迹和事件日志，并提供暂停、继续、停止与复位视角。

运行结果保存在本题自己的 `output` 目录，不写入机器人 B 类题目的目录。

## 2. 在其他电脑安装

Python 3.10 或以上，建议使用与本次验证一致的 Python 3.12。浏览器需要支持 WebGL2。

```powershell
Set-Location 'D:\GithubCode\robot-pose\software_a1'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

直接指定虚拟环境中的 Python，因此不需要执行激活脚本或更改 PowerShell 执行策略。不要把整份 `.venv` 当作跨电脑可移植环境；在另一台机器重新安装依赖。

Three.js 0.187.0 已保存在 `static/vendor/three`，附官方 MIT LICENSE、来源和校验值。页面运行时不请求 CDN，不需要 npm 或前端构建步骤。Python 依赖的首次安装需要联网。

Node.js 20 或以上仅用于 JavaScript 数学测试；Playwright 仅用于可选的浏览器集成检查。运行服务和控制脚本不需要它们。

## 3. 先看这些文件各自负责什么

| 文件 | 作用 | 值得重点阅读的内容 |
| --- | --- | --- |
| [protocol.py](protocol.py) | 统一数据格式与输入检查 | `Point`、`Route`、`MoveRequest`、`Telemetry`、`load_route()` |
| [server.py](server.py) | 提供页面、HTTP 接口和 WebSocket 中转 | `Hub` 状态、`create_app()`、接收命令、处理回执、断线取消 |
| [controller.py](controller.py) | 独立的外部控制程序 | `request_json()`、`run_route()`、逐段等待、超时与结果保存 |
| [path.example.json](path.example.json) | 配置路径与每段速度 | 起点 `initial_position`，以及 `segments` 中每段的 `target`、`speed` |
| [static/index.html](static/index.html) | 网页结构 | 三维 `canvas`、状态面板、按钮、路径列表、事件表格、本地模块导入映射 |
| [static/styles.css](static/styles.css) | 网页外观与响应式布局 | 桌面双栏、窄屏重排、状态色、坐标对齐、按钮反馈 |
| [static/motion.js](static/motion.js) | 纯运动计算与运动状态机 | `advanceTowards()`、`MotionEngine.start/tick/pause/resume/cancel` |
| [static/scene.js](static/scene.js) | Three.js 场景显示 | 场景、相机、渲染器、方块、网格、路径点、实际轨迹、鼠标视角 |
| [static/main.js](static/main.js) | 串起网页通信、计算和显示 | WebSocket 消息处理、动画循环、状态更新、回执、后台暂停、重连 |
| [requirements.txt](requirements.txt) | 锁定 Python 依赖 | FastAPI、Uvicorn、WebSocket 服务支持和 Python 测试依赖 |
| [package.json](package.json) | JavaScript 测试配置 | ES module 类型声明、测试命令、可选 Playwright 版本 |
| [.vscode/launch.json](.vscode/launch.json) | Windows VS Code 调试配置 | 启动服务、调试外部程序、运行 Python 测试；使用本题专用解释器 |

推荐阅读顺序：路径配置 → `protocol.py` → `motion.js` → `controller.py` → `server.py` → `main.js` → `scene.js` → 页面与样式。

## 4. 消息怎样走完整个流程

```text
独立 controller.py
  ├─ 读取 JSON 路径并校验全部路段
  ├─ HTTP 提交起点和路径
  ├─ HTTP 提交一段目标位置、速度、命令编号
  │       ↓
  │   server.py 通过 WebSocket 转发
  │       ↓
  │   main.js 接收命令
  │       ├─ MotionEngine 计算位置
  │       ├─ scene.js 更新方块并画出来
  │       └─ WebSocket 返回当前位置 / 到达回执
  │               ↓
  ├─ HTTP 查询该命令状态，确认已到达
  └─ 发送下一段；全部到达后写入实际执行记录
```

HTTP 202 表示命令已被接收，不表示方块已到达。控制脚本必须查询对应 `command_id`，等待 `status=arrived`。

一次只执行一条运动命令。忙时收到另一条命令返回 HTTP 409；外部脚本等待到达后再发送下一条，因此正常路径执行不会互相覆盖。

## 5. protocol.py：数据格式和单位

`Point` 固定使用带名字的 x/y/z，避免坐标顺序混淆。坐标必须是有限数值，速度必须有限且大于零，未知字段会被拒绝。

路径配置由 `Route` 和 `Segment` 描述。`load_route()` 在发送任何请求前验证整条路径，避免已经执行前几段，才发现后面的速度有误。

一条运动命令示例：

```json
{
  "type": "move",
  "command_id": "example-001",
  "target": {"x": 2.0, "y": 0.2, "z": 0.0},
  "speed": 0.8
}
```

页面回执 `Telemetry` 包含命令编号、阶段、当前位置、实际累计运动时间和原因。阶段包括 `moving`、`paused`、`arrived`、`cancelled`、`error`。

## 6. motion.js：为什么速度不依赖帧率

`advanceTowards()` 只接收当前位置、目标、速度和时间差，不依赖 DOM、Three.js 或网络。

$$d=p_{target}-p,\quad L=\|d\|$$

$$s=\min(v\Delta t,L),\quad p_{new}=p+(d/L)s$$

- 已经在目标时直接返回，避免除以零。
- 正常帧按 `速度 × 真实时间差` 移动，并将方向向量归一化。
- 最后一帧把移动距离限制在剩余距离内，准确落到目标，不会冲过目标。
- 本帧实际消耗的运动时间为 `s / v`，不会把到达后的多余帧时间算进去。

`MotionEngine` 保存命令、位置、阶段、累计运动时间和暂停原因。手动暂停与页面后台暂停分别记录，切回前台不会意外解除用户的手动暂停。

`main.js` 使用动画帧时间戳，先把毫秒差除以 1000 转成秒，再调用 `tick()`。恢复运动时重设时间基准，避免把后台停留时间当成一次很大的移动时间。

## 7. scene.js 和 main.js：计算与显示分开

`scene.js` 创建 `Scene`、`PerspectiveCamera`、`WebGLRenderer`、方块形状与材质，并用 `OrbitControls` 旋转观察视角。它按照传入的位置显示方块，自身不决定运动速度。

规划路径使用蓝色虚线；已经走过的轨迹使用绿色实线。轨迹缓冲区预分配并更新，避免动态点数增长导致绘图数据被截断。尺寸变化时通过 `ResizeObserver` 更新相机和画布。

`main.js` 负责：

- 连接当前页面所在服务的 WebSocket，不把端口写死。
- 接收起点 / 路径和运动指令，调用运动计算模块。
- 每帧更新方块显示；约每 100 ms 更新状态文字和运动回执。
- 到达、暂停、停止等阶段变化立即报告，不等待下一个定时更新。
- 处理按钮、页面可见性、连接断开和重连，忽略旧连接的回调。
- 显示初始化或通信错误。WebGL2 未就绪时不发送 ready，避免控制程序误认为页面可以执行。

## 8. server.py：接口、状态和回执

`Hub` 保存当前显示页面、最近确认位置、当前命令和最多 256 条命令历史。`asyncio.Lock` 使连接和命令状态修改按顺序完成。

| 接口 | 作用 |
| --- | --- |
| `GET /` | 打开三维页面 |
| `GET /api/state` | 查询连接、位置、阶段、当前命令及路径 |
| `POST /api/route` | 显式设置起点和整条规划路径；仅在无活动命令时允许 |
| `POST /api/move` | 接收并转发一条目标 / 速度命令 |
| `GET /api/commands/{id}` | 查询指定命令是否真的到达 |
| `POST /api/control` | 请求暂停、继续、停止；等待页面实际回执 |
| `GET /api/route/example` | 下载示例路径 |
| `WebSocket /ws` | 页面握手、指令推送、可见性和运动回执 |

关键检查：

- 页面发送 `ready` 且处于前台后，才接受新的运动命令。
- 当前命令未结束时，拒绝另一条命令和路径重置。
- 同一编号、相同参数的重发不会重复执行；同一编号换参数会被拒绝。历史仅保留最近 256 条，外部程序每次运行生成新的编号。
- 回执编号必须匹配活动命令，累计运动时间不能倒退，`arrived` 的位置必须在目标的 `1e-6 m` 范围内。
- 断开连接时，未完成命令变为 `cancelled`，不会被当成已到达。
- 第一版明确使用一个显示页面和一个服务进程。第二个显示页面会被拒绝，防止不同页面给出矛盾的位置和到达回执。

状态保存在内存，重启服务会清空运行状态，因此不要为这个实现增加多 worker。

## 9. controller.py：真正独立的外部控制

控制脚本是与服务器分开的 Python 进程，使用标准库 `urllib` 发 HTTP 请求。`run_route()` 会：

1. 校验路径和速度倍率。
2. 等待页面 ready、前台可见。
3. 提交路径并显式回到配置起点。
4. 为每段生成唯一命令编号并下发。
5. 查询这一编号，直到 `arrived`，再发下一段。
6. 记录理论运动时间、页面累计运动时间、控制脚本的墙钟等待时间及最后位置。

暂停期间不计入页面的运动时间，但会计入墙钟等待时间；网络和轮询也会增加少量等待时间。默认每段至少等待 30 秒，较长运动自动延长超时。

收到取消、断线、超时或 Ctrl+C 时，控制程序返回非零退出码，并尝试停止自己已经接收的那条命令。控制操作带命令编号，避免误停其他命令。

```powershell
# 使用另一份路径文件
.\.venv\Scripts\python.exe controller.py --path my-path.json

# 全部路段速度乘 2
.\.venv\Scripts\python.exe controller.py --speed-scale 2

# 配合不同服务端口
.\.venv\Scripts\python.exe server.py --port 8765
.\.venv\Scripts\python.exe controller.py --url http://127.0.0.1:8765
```

后两条服务 / 控制命令仍应在不同终端执行；浏览器也要打开相同端口。

## 10. 修改路径

编辑 `path.example.json` 中的 `initial_position` 和 `segments`，然后重新运行控制程序。每段可以有独立速度，坐标表示方块中心。

默认四段各长 2 m，速度分别为 0.8、1.0、0.8、1.0 m/s，对应纯运动时间 2.5、2.0、2.5、2.0 s，总计 9.0 s。到点确认、网络传输和人工暂停会额外增加墙钟时间。

新增路段就在 `segments` 末尾添加一个 `target` / `speed` 对象。三个坐标都参与计算，可以使用空间折线；默认示例在水平面上。

## 11. 测试

Python：21 项测试，覆盖协议校验、页面握手、忙状态、幂等、到达核对、暂停 / 停止、旧回执、断线、重连和配置预检查。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

JavaScript：17 项纯数学 / 状态机测试，包含斜向运动、到达限幅、零距离、30 / 60 / 144 FPS 一致性、不规则帧时间、暂停原因和输入错误。

```powershell
node --test tests/motion.test.mjs
```

可选浏览器集成检查：需要先关闭普通三维页面，保持服务器运行，然后安装 Playwright 与 Chrome：

```powershell
npm install
node tools/browser_check.mjs
```

检查脚本启动隔离的 Chrome，实际运行独立 `controller.py`，验证四段运动、暂停位置不变、停止、断线取消、重连、390px 窄屏和本地资源加载，并保存实际截图和日志。浏览器使用自己的配置，不操作用户已有的浏览器标签页。

本次验证：Python 3.12.4、Node.js 24.22.1、Three.js 0.187.0；Python 21 项和 JavaScript 17 项测试通过，浏览器 8 项流程检查通过。验收使用端口 8765，普通运行默认 8000。

## 12. 调试与重点观察

### Python

VS Code 可打开总目录或只打开 `software_a1`，选择对应的 `A1：启动三维服务`、`A1：调试外部控制脚本` 或 `A1：运行 Python 测试` 配置。配置已经指定本题 `.venv`，不会使用机器人题目的环境。

建议先在终端启动服务、打开页面，再单独调试控制脚本，避免同时研究所有程序。

| 断点位置 | 观察内容 |
| --- | --- |
| `controller.py` 的 `route = load_route(path)` 后 | 整条路径、每段目标和速度 |
| `controller.py` 的 `/api/move` 请求之后 | 返回的 `command_id`、`status=accepted`、理论运动时间 |
| `controller.py` 查询命令的循环 | 状态从 moving 到 arrived，而非只凭 HTTP 成功 |
| `server.py` 的 `move()` | 输入校验、当前已确认位置、转发的命令 |
| `Hub.telemetry()` | 回执编号、当前位置、运动时间、到达判断 |

F5 继续，F10 执行一行，F11 进入函数。

### 浏览器 JavaScript

按 F12 打开开发者工具：

- Console：看模块加载或绘图错误。
- Network → WS → Messages：看 move 指令和 telemetry 回执。
- Sources → `static/motion.js`：在 `advanceTowards()` 查看剩余距离、`deltaSeconds`、`step`。
- Sources → `static/main.js`：看收到指令后如何调用运动计算，以及如何发送到达回执。

需要逐行研究计算时，优先调试纯数学测试。调试器长时间暂停页面脚本会影响真实时间差，不适合作为正常运行速度的测量依据。

## 13. 实际结果文件

| 文件 | 含义 |
| --- | --- |
| [output/process.mp4](output/process.mp4) | 运行过程演示视频，点击链接观看或下载 |
| [output/last_run.json](output/last_run.json) | 外部控制程序实际执行报告，题目标识为 `"robot": "A1"`，含每段目标、速度、运动时间、状态与最终位置 |
| [output/controller-demo.txt](output/controller-demo.txt) | 浏览器集成验收时真实控制脚本的输出 |
| [output/browser_check.json](output/browser_check.json) | 实际浏览器检查结果 |
| [output/preview-moving.png](output/preview-moving.png) | 外部指令执行过程截图 |
| [output/preview-desktop.png](output/preview-desktop.png) | 桌面端完成状态截图 |
| [output/preview-mobile.png](output/preview-mobile.png) | 390px 窄屏完成状态截图 |

`last_run.json` 指外部控制脚本最近一次运行；浏览器检查随后还会测试停止与断线，所以服务当前状态不一定等于该成功运行结束时的状态。重新运行控制程序会按配置重置起点并产生新的报告。

## 14. 常见问题

- `No module named fastapi`：使用本目录 `.venv\Scripts\python.exe`，或先安装 `requirements.txt`。
- 打开页面但控制程序一直等待：确认浏览器显示“已连接”，且没有最小化或切换到其他标签页。
- 第二个页面提示已有显示页面：关闭原显示页面后刷新，或只保留一个页面。
- 方块停止但没有 PASS：查看它是 arrived 还是 cancelled；停止 / 断线不能作为成功到达。
- 刷新 / 断线：当前命令取消。重连以服务最近确认的位置为准，旧命令不自动续跑；重新运行控制脚本会从配置起点重新开始。
- 端口被占用：给服务和控制脚本使用同一个新端口，浏览器访问对应端口。
- 暂停太久导致控制脚本超时：增加 `--timeout`；脚本超时会请求停止自己的命令。
- 不要直接双击 `index.html`：页面通过 Python 服务加载，确保模块路径、HTTP 和 WebSocket 位于同一服务。

参考：[Three.js 场景基础](https://threejs.org/manual/pages/creating-a-scene.html)、[Three.js WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html)、[FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)。
