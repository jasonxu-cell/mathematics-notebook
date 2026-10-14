# 0.2 验收记录

2026-10-10 后续显示修复：虚数单位显示为小写 `i`；含 `Root` 的受支持解集逐行显示 12 位有效数字近似，并可展开精确解。新增后端回归后为 **43/43**，现有 Node 检查 **30/30**，重建内核检查 **14/14**；五次、十次方程的精确/近似公式共 30 条均通过 KaTeX 排版。更新后的桌面应用已实际显示用户九次方程的 9 个分行解，原草稿已恢复。当前修复的包哈希、部署匹配及验收范围见 [root-display/verification.json](build/root-display/verification.json)，数学独立核对见 [math-review.json](build/root-display/math-review.json)。以下 15 项桌面全量验收和旧包哈希是修复前的 0.2 历史记录；本次没有重复运行那套桌面全量测试。

日期：2026-10-10。主机为 macOS 15 / Apple Silicon。本轮没有启动 Wolfram 或调用其计算引擎。

| 层级 | 验收内容 | 已确认结果 |
|---|---|---|
| 实际计算后端 | 基础计算、历史、隔离、Print/诊断、SVG、Graphics3D/Plot3D、数值 Manipulate、Factor 代数扩域；局部参数恢复、副作用一次执行与错误路径 | 38/38 通过；`backend/tests/` |
| Node 集成与回归 | 真 worker IPC、超时/取消、并发磁盘写入；动态请求串行/合并/过期抑制；`.nb` 结构、不执行初始化、往返、打印消息与长度/大小边界 | 30/30 通过；[日志](build/node-tests-0.2.log) |
| 核心能力盘点 | 69 个数学/语言行为断言 | 61 通过，8 个差距；[完整数据](build/capability-results.json)、[功能清单](CAPABILITIES.md)。这不是全功能兼容率 |
| 冻结计算内核 | 从 `/private/tmp` 运行随应用携带的 Mach-O，PATH 仅 `/usr/bin:/bin`，移除 PYTHON/WOLFRAM/MATHEMATICA 环境变量；包含扩域分解、真实 3D 和控件更新 | 12/12 通过；[运行记录与依赖审计](build/kernel-smoke.json) |
| 0.2 最终打包应用 | 实际桌面、受控 IPC、真实计算、基础 `.nb` 导入导出、3D 旋转/缩放、控件更新、覆盖清单筛选和退出保存 | 15/15 通过；[完整桌面记录](build/application-smoke.json) |

**0.2 最终 `.app` 的 15 项桌面验收已全部通过。** `scripts/app-smoke.cjs` 的新版 [application-smoke.json](build/application-smoke.json) 标记 `passed: true`，完成时间为 2026-10-10 05:27:27 UTC。验收使用独立测试草稿目录，文件选择器限定为临时测试路径；计算、文件读写和窗口退出经过实际打包应用。真实鼠标旋转和滚轮缩放改变了三维视角及像素结果；数值控件将 `a^2` 从 0 更新为 9，三维组合控件改变曲面像素并保留当前视角。

`rendererErrors` 为空，未发现 renderer 异常或 CSP 错误。日志包含测试反复调用 `getImageData` 产生的 Canvas 读取性能提示，以及 Chromium GPU 初始化失败后的软件回退；三维渲染、旋转、缩放和参数更新的像素检查均通过，不能据此声称硬件加速已验证。

桌面截图：

- [基础计算与数学排版](build/application-smoke-results.png)
- [二维 SVG 绘图](build/application-smoke-plot.png)
- [旋转和缩放后的三维曲面](build/application-smoke-graphics3d.png)
- [Manipulate 与三维绘图组合](build/application-smoke-manipulate-plot3d.png)
- [功能差距筛选](build/application-smoke-compatibility-gaps.png)

0.1 的 8 项桌面验收是历史记录；本轮使用重新打包、重新验收的 **0.2.0** 包，不能混用旧结果。当前应用包为 **430,757,536 字节**，`Contents/Resources/app.asar` SHA-256 为 `9da114f00eb9f6a4c53c75a3c9b3b928386d5a4ce50874662b125598877889ad`。

`.nb` 导入不执行初始化代码，没有历史输出的输入不显示计算结果。未知结构保留为不可执行文本。导出保留 Print/Message 文本历史；解码内容与转义后的归档采用不同上限；转换后的文档在加载前必须可按常规 `.mnb` 形式保存。

包身份见 [application-manifest.json](build/application-manifest.json)，版本标记为 **0.2.0**，13 个运行时源码文件与 asar 内对应文件逐字节匹配；随包计算内核与已验收的冻结内核匹配，其每个 Python 模块均纳入源码哈希。许可与依赖打包见 [packaging-notes.md](packaging-notes.md)，依赖版本由 `package-lock.json` / `requirements.lock.txt` 固定。

测试只证明对应样例及流程。完整 Mathematica、全部函数选项、所有 `.nb` box、任意 Dynamic、知识库、云服务及专有模块等价性尚未建立。
