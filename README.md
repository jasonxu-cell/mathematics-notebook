# Mathematics Notebook

独立的 macOS 数学笔记本 **0.2**，使用 **Mathics3 10.0.1**，可脱离 Wolfram 安装运行。界面与文件、进程协议为本项目实现；没有打包 Wolfram 的代码、资源、框架或内核。完整 Mathematica 复现尚未完成，已实现范围与差距见 [功能清单](CAPABILITIES.md)。

## 使用

构建产物为 `dist/Mathematics Notebook-darwin-arm64/Mathematics Notebook.app`。双击打开，在计算单元中输入 Wolfram Language 表达式并按 **Shift+Enter**。顶部“运行全部”依次计算整本；“停止”会重启内核并清空变量，笔记内容保留。当前打包目标为 Apple Silicon，数学依赖要求 macOS 14 或更高版本。

可试：

```wl
Factor[x^4 - 1]
Solve[x^2 - 5 x + 6 == 0, x]
D[Sin[x^2], x]
Integrate[Exp[-x^2], {x, -Infinity, Infinity}]
Plot[Sin[x], {x, -2 Pi, 2 Pi}]
a = 7;
a^2
```

支持计算、文字和标题单元，添加/删除/移动单元，输入与输出标签，会话变量与历史，Print、诊断、LaTeX 数学排版、二维 SVG 图形，自动草稿以及文件打开/保存。0.2 增加基础 `.nb` 互操作、可旋转缩放的三维图形、`Manipulate` 数值滑块，以及可搜索的功能覆盖清单。

`.mnb` 是自己的 JSON 文档格式，保存单元、顺序、输入和历史输出。打开文档不会恢复运行中的变量；请重新求值恢复会话。可以导出 `.wl` 源码，也可以导入 `.wl/.m`。`.nb` 支持常用文本单元与数学 box 子集；未知结构保留为不可执行文本并显示提示，导入不会执行初始化单元。具体限制见 [.nb 互操作说明](notebook-nb-notes.md)。

左侧“进阶示例”提供矩阵、微分方程、描述统计、三维曲面和数值交互的快捷输入。也可以直接输入以下表达式：

```wl
Inverse[{{1,2},{3,4}}]
Factor[x^4 + 1, Extension -> Sqrt[2]]
DSolve[y'[x] == y[x], y[x], x]
Plot3D[Sin[x] Cos[y], {x,-2,2}, {y,-2,2}]
Manipulate[Plot[Sin[a x], {x,-Pi,Pi}], {{a,1,"频率"},0.5,3,0.1}]
```

三维图形可拖动旋转、滚轮缩放。`Manipulate` 当前支持有限数值范围控件，参数在局部作用域求值；任意 `Dynamic`、自定义控件与完整前端事件尚未实现。

`Factor` 新增精确代数数域选项，例如上例会得到 `(x² − √2 x + 1)(x² + √2 x + 1)`。`Extension` 可传精确代数数或数的列表；其他 `Factor` 选项尚未覆盖。

`Solve[x^5 - 5 x + 6 == 0, x]` 等返回 `Root` 的方程，现在逐行显示 12 位有效数字的近似解；展开“查看精确解”可看原始代数根，`Out` 和保存结果保留精确值。自动近似目前针对受支持的有理系数多项式，次数最多 12；超出范围仍保留内核的精确输出。公式中的虚数单位显示为小写 `i`，输入语法仍使用 `I`。

也可打开 [进阶示例笔记本](examples/advanced.mnb) 或 [.nb 互操作示例](examples/advanced.nb)。

## 从源码运行

本次开发和打包使用 Node.js 22.23.3 / Python 3.12.3；建议用这组已验证的版本安装固定依赖。

```sh
npm ci
npx --no install-electron
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm start
```

`package-lock.json` 与 `requirements.lock.txt` 保留本次依赖版本。构建自包含计算运行时及桌面应用：

```sh
.venv/bin/python scripts/build-kernel.py
npm run package
```

开发版调用项目 venv；打包版调用应用内的 `Contents/Resources/mathematics-kernel/mathematics-kernel`。打包版携带 Python 与数学依赖，无需用户单独安装 Python。

## 验证

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
npm test
```

0.2 已确认后端 **38/38**、Node 回归 **30/30**、冻结计算内核 **12/12**、最终打包应用桌面验收 **15/15** 通过；69 个代表性能力样例中 **61 通过、8 个差距**，这不是 Mathematica 全功能兼容率。桌面验收覆盖真实三维旋转、缩放、控件重新计算、基础 `.nb` 往返及退出保存。当前状态和证据见 [VERIFICATION.md](VERIFICATION.md)。静态逆向证据和架构依据在 [上一级报告](../wolfram-re-analysis/REPORT.md)。

## 能力与许可

Mathics 提供基础符号和数值计算的兼容实现，未承诺 Mathematica 全套函数、精度行为、动态界面、全部三维语义、云服务、知识库与专有扩展的等价性。当前版本围绕明确的验收集实现，新增函数与选项需要单独验证。详情见 [Mathics3 官方项目](https://github.com/Mathics3/mathics-core/tree/10.0.1)。

本项目代码采用 GPL-3.0-or-later；Mathics3 同为 GPL-3.0-or-later。分发时保留各组件许可证及源代码。计算运行时构建脚本收集第三方许可证；Electron 及前端依赖的原始许可证也随依赖保留。此目录为源代码，不包含上一级目录的 Wolfram 分析输入。
