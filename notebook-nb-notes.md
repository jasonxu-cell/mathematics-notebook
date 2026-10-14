# `.nb` 文档互操作

`notebook-nb.cjs` 提供不执行代码的文本导入和规范化导出。它只支持 Wolfram Notebook 的一个明确子集；导入方应展示 `warnings`，其中每次都含“支持子集、导入不执行初始化单元”的提示。

```js
const { fromNotebook, toNotebook } = require('./notebook-nb.cjs');
const { document, warnings } = fromNotebook(source, '文件名');
const exportedSource = toNotebook(document);
```

`document` 使用 `notebook-model.cjs` 的 version 1 格式，经过 `validateDocument` 验证。标题由调用方传入；文件内的 `WindowTitle` 等前端选项不决定应用状态。解析失败会抛出异常，不返回半份笔记本。结构错误使用 `NotebookSyntaxError`，包含文本位置。

## 支持的内容

| 原始结构 | 应用内形式 |
| --- | --- |
| `Notebook[{Cell[...], ...}, options]` | 文档与按原顺序排列的单元格；选项不执行 |
| `CellGroupData[{...}, Open/Closed]` | 平铺单元格，并提示折叠状态丢失 |
| Title、Subtitle、Section、Subsection、Subsubsection | heading |
| Text | text |
| 紧接输入的 Print、Message | `result.prints/messages` 中的历史文本；无输入时为 text |
| Input、Code | input；导入不求值 |
| 紧接输入的 Output | `result.text` 中的历史文本；无输入的 Output 为 text |
| `TextData`、基础文字 `StyleBox`、内联 `Cell` | 纯文本，样式丢失会提示 |
| `BoxData`、StandardForm `FormBox`、基础 `RowBox` | 输入文本 |
| `FractionBox[a,b]` | `(a)/(b)` |
| `SuperscriptBox[a,b]` | `(a)^(b)`；导数或共轭上标拒绝推断 |
| `SqrtBox[a]`、`SubscriptBox[a,b]` | `Sqrt[a]`、`Subscript[a,b]` |
| 基础矩形 `GridBox` | 嵌套列表；排版选项被忽略并提示 |

`RowBox` 保留显示顺序，分开的相邻字母/数字记号之间加入空格，例如 `{"2","Pi"}` 转为 `2 Pi`，并提醒检查隐式乘法或符号名称。嵌套 `RowBox` 的结构可能携带运算优先级信息；当前转换会明确提示复杂分组需要核对，并保留原始 Cell。它不是完整的 Wolfram `MakeExpression` 实现。

未知 box、`InterpretationBox`、`TemplateBox`、TraditionalForm、导数上标或不规则表格不会被猜测为代码。整个原始 Cell 保留为不可执行的 text，并返回包含原因的警告。原始 Cell 文本也保存在 `cell.nbImport.original`，支持的单元格同样保留此记录。`nbImport.source/style/outputs` 用于来源和历史记录；原生 JSON 保存可保留这些字段。没有对应 Output 的 Input 不含 `result`，因而不会显示已完成或分号抑制状态；历史 Output 才生成文字 `result`。

## 导出边界

导出生成单个文本 `Notebook[...]`。输入源码经过字符串转义后放入 `BoxData`，所有输入都有 `InitializationCell -> False`。标题和正文也只作为字符串输出。未知原始 Cell 作为带引号的 Text 保存，绝不重新注入为 box 或活动选项。

导出可保留基本标题样式和纯文本输出历史，包括安全带引号的 Print、Message 和 Output Cell，重入后继续作为文本历史保存；分组、字体、布局、CellLabel、交互对象、图形对象和前端事件不复原。输出历史只说明文件中保存了这些文字，不能验证它来自当前内核运行。应用当前的 SVG/3D 结果也只导出其文字部分。因此该格式转换不是完整 `.nb` 原样往返。

解析器只识别括号、字符串、逗号和函数头等结构，不使用 `eval`、`ToExpression`、Wolfram 内核、外部程序或动态导入。嵌套 `(* ... *)` 注释和 Notebook 文件尾部的缓存轮廓注释被跳过。字符串支持引号、反斜杠、换行等转义、数字 Unicode 转义和保留的 `\\[Name]`；未知转义保留原文并警告。初始化或单元格事件选项只会被识别并提示禁用，导出时删除。用户之后明确求值 Input/Code 是独立的应用操作。

限制为 UTF-8 文本 8 MiB、括号/注释嵌套 128 层、250000 个结构节点、最多 2000 个 Cell（分组包装也计数），并遵守模型中解码后的单元格/历史文字 100000 字符限制。原始 Cell 归档单独遵守模型 `MAX_ARCHIVE = MAX_SOURCE * 6 + 4096`，允许引号、字符转义和包装造成的长度增加。导出将输出历史形成的额外 Cell 计入 2000 个上限，同样限制 8 MiB。导入返回前还检查转换后带归档的原生笔记本在格式化保存时不超过 8 MiB，因此不能导入一份随后无法保存或关闭的文档。超限、未结束注释/字符串、括号不匹配、残缺表达式和不正确的顶层结构安全失败。

## 验证与格式依据

`node --test tests/notebook-nb.test.cjs`：19 项通过，覆盖有效/损坏结构、嵌套注释、字符转义、基础数学 boxes、未知内容保留、不执行载荷、输出历史、往返和资源限制。新增回归检查 Print/Message 重入保留、3.2 MB 原文件转换后超过保存限额的失败，以及 99990 字符合法正文经过包装后仍能重入。`examples/advanced.nb` 为本项目独立编写的 fixture。

只读检查本机公开文档样本 `/Applications/Wolfram.app/Contents/Documentation/English/System/ExampleData/BasicTemplate.nb`，未启动目标软件或内核。实测导入得到 3 个单元格：带 TextForm 模板的 Title/Text 被保留为原始文本并提示；嵌套 RowBox 的绘图输入转为 `Plot[Sin[x],{x,0,2 Pi}]`。没有将该文件或 Wolfram 资产复制进项目。

Wolfram 官方文档将 Notebook 描述为由 Cell 和选项构成的表达式，且 `.nb` 使用该表达式的文本表示。[Notebook](https://reference.wolfram.com/language/ref/Notebook.html)、[NB 文件格式](https://reference.wolfram.com/language/ref/format/NB.html)、[Cell](https://reference.wolfram.com/language/ref/Cell.html)、[BoxData](https://reference.wolfram.com/language/ref/BoxData.html) 是结构依据。

官方资料说明 RowBox 的默认分组与运算优先级相关，MakeExpression 可使用自定义规则，这也是本实现对不确定语义保留来源并警告的原因。[RowBox](https://reference.wolfram.com/language/ref/RowBox.html)、[MakeExpression](https://reference.wolfram.com/language/ref/MakeExpression.html)、[文本输入输出](https://reference.wolfram.com/language/tutorial/TextualInputAndOutput.html)。

基础数学 box 转换参考各自定义；GridBox 在标准输入形式中的基础列表解释仅适用于支持的矩形内容。[FractionBox](https://reference.wolfram.com/language/ref/FractionBox.html)、[SuperscriptBox](https://reference.wolfram.com/language/ref/SuperscriptBox.html)、[SqrtBox](https://reference.wolfram.com/language/ref/SqrtBox.html)、[SubscriptBox](https://reference.wolfram.com/language/ref/SubscriptBox.html)、[GridBox](https://reference.wolfram.com/language/ref/GridBox.html)。
