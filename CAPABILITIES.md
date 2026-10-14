# 功能覆盖与后续实施清单

目标是持续扩大独立实现的 Mathematica 兼容范围；**完整复现仍未完成**。当前 0.2 版本以 Mathics3 10.0.1 为计算基础，Notebook、文件互操作、三维显示和数值动态控件由本项目实现。不能把“名称存在”或“某个样例通过”当成一个函数完全兼容。

## 范围依据

功能分类参考 [Wolfram 官方文档目录](https://reference.wolfram.com/language/)，具体互操作参考 [Notebook](https://reference.wolfram.com/language/ref/Notebook.html)、[Manipulate](https://reference.wolfram.com/language/ref/Manipulate.html) 与 [Plot3D](https://reference.wolfram.com/language/ref/Plot3D.html)。这些文档描述目标行为；本项目只实现下面列出的范围。

本机 Wolfram 15.0.1 的 `FunctionInformation.m` 经只读结构解析，得到 66 个上下文中的 6,437 个去重名称，其中 `System` 上下文 5,404 个。这个文件是参数/选项元数据，既不是整个产品的完整功能总数，也不证明这些名称在 Mathics 中可用。原文件没有执行，清单与文件 SHA-256 保存在 [本机元数据清单](../wolfram-re-analysis/function-metadata-inventory.json)。它是后续逐符号调查的索引，不随独立应用分发。

## 当前状态

以下表格区分当前实现和未覆盖范围。计算及文件格式的测试结果见后文；0.2 最终打包应用另有 15 项桌面流程验收通过，详情见 [验收记录](VERIFICATION.md)。这些结果只验证对应流程与样例，不能扩大为整类功能完全兼容。

| 领域 | 当前实现与计算/格式验收范围 | 尚需实现或验证 |
|---|---|---|
| 文档编辑 | 输入、文字、标题、单元移动、批量求值、草稿、文件保存；⌘K 函数参考面板（搜索内核全部已实现函数，查看签名与示例并插入单元，索引由 scripts/build-function-index.py 在构建期从真实内核导出） | 分组折叠、完整样式系统、富文本、公式结构编辑、打印与排版 |
| `.nb` 互操作 | 文本 Notebook、Cell、CellGroupData 平铺及一组常用 box；导出基础 `.nb` | 全部 box、特殊样式、嵌入资源、前端事件及完整无损往返 |
| 数值与代数 | 精确分数、复数、精度样例、基础函数、Factor/Expand/Simplify；新增 Factor 的精确代数 Extension 选项 | 其他 Factor 选项、假设系统、边界分支、条件表达式及性能等价 |
| 方程与优化 | Solve、线性系统与 FindRoot 样例 | Reduce、Minimize 当前样例未通过；约束全局优化、混合整数优化 |
| 微积分 | 求导、积分、NIntegrate、Limit、Series、Sum、Product 样例 | 多种奇点、主值、积分变换、高阶/多变量细节及误差控制 |
| 微分方程 | 一阶解析 DSolve 样例 | NDSolve 当前样例未通过；PDE、DAE、边值、事件、有限元 |
| 线性代数 | Det、Inverse、LinearSolve、Eigenvalues、Rank、Power、Dot、Transpose 样例 | 大型稀疏矩阵、张量、更多分解、数值条件与稳定性 |
| 概率与统计 | Mean、Median、Variance、StandardDeviation、Quantile 样例 | 当前正态 CDF 样例未通过；分布系统、统计检验、拟合、时间序列 |
| 数论与离散数学 | Prime、PrimeQ、FactorInteger、GCD、PowerMod、进制转换样例；新增 FrobeniusNumber（n=2 公式，n≥3 残量最短路）与 FrobeniusSolve（小情形枚举） | 群论、组合结构、符号证明等完整体系 |
| 多项式与求根 | PolynomialQuotientRemainder、PolynomialExtendedGCD、Subresultants（主子式系数序列）、SymmetricPolynomial/SymmetricReduction、NRoots（含重数与排序约定）、CountRoots（Sturm 精确计数，计重数）；与 Wolfram 15.0.1 差分 73/76 一致（余 3 个为显示精度与解顺序的已知差异） | 代数数域上的完整多项式体系 |
| 常用小件 | ArgMin/ArgMax、LinearProgramming、KnapsackSolve、SolveValues/NSolveValues/DSolveValue/NDSolveValue、LinearSolveFunction、RecurrenceTable、FindLinearRecurrence（Berlekamp-Massey）、Wronskian、Residue、GeneratingFunction/ExponentialGeneratingFunction、SatisfiabilityQ（注意：Wolfram 15.0.1 对该名本身不求值，能求值的是 SatisfiableQ；本项目两者都求值）、MovingAverage/MovingMedian/ExponentialMovingAverage、MaximalBy/MinimalBy；与 Wolfram 15.0.1 差分 78/90 一致（其余为数值精度显示与 Wolfram 本身不求值的条目） | 完整渐近分析（Asymptotic*）、更一般的生成函数 |
| 图论 | Graph 惰性对象与 34 个函数：VertexList/EdgeList/VertexCount/EdgeCount/AdjacencyMatrix（稠密 List，非 SparseArray）/VertexDegree/VertexInDegree/VertexOutDegree/AdjacencyList/VertexQ/EdgeQ/DirectedGraphQ/UndirectedGraphQ、FindShortestPath/GraphDistance/GraphDistanceMatrix/VertexEccentricity/GraphDiameter/GraphRadius/GraphCenter/GraphPeriphery、ConnectedComponents（有向图强连通）/WeaklyConnectedComponents/ConnectedGraphQ/AcyclicGraphQ/TreeGraphQ/TopologicalSort/FindSpanningTree、EulerianGraphQ/FindEulerianCycle/HamiltonianGraphQ/FindHamiltonianCycle（≤14 顶点）、BreadthFirstScan/DepthFirstScan（返回访问序，不支持事件回调）；与 Wolfram 15.0.1 差分 31/31 一致。第二批新增 46 个（networkx 3.7 后端）：Subgraph/NeighborhoodGraph/GraphUnion/GraphIntersection/GraphDifference/GraphComplement/DirectedGraph/UndirectedGraph/AdjacencyGraph/IncidenceMatrix/KirchhoffMatrix/LineGraph/EdgeAdd/EdgeDelete/VertexAdd/VertexDelete/EdgeContract/GraphPower/TransitiveClosureGraph、IsomorphicGraphQ/BipartiteGraphQ/PlanarGraphQ/VertexConnectivity/EdgeConnectivity/ChromaticPolynomial/TuttePolynomial（>18 边不求值）、FindClique/FindVertexCover/FindIndependentVertexSet/FindIndependentEdgeSet/FindMaximumFlow/FindMinimumCut/FindPath/FindCycle、DegreeCentrality/BetweennessCentrality/ClosenessCentrality/EigenvectorCentrality/PageRankCentrality、CompleteGraph/CycleGraph/PathGraph/StarGraph/WheelGraph/GridGraph/HypercubeGraph；与 Wolfram 15.0.1 差分 177/179 一致（余 2 个为 FindMinimumCut 两侧均不求值，仅未求值文本形式不同） | 图的图形化绘制、带权图、TreeQ 在 Wolfram 15 中检测 Tree 对象（图用 TreeGraphQ），本项目一致 |
| 积分变换 | LaplaceTransform/InverseLaplaceTransform、FourierTransform/InverseFourierTransform/FourierCosTransform/FourierSinTransform（含 FourierParameters 选项）、MellinTransform/InverseMellinTransform、Convolve（积分法 + 卷积定理回退）、ZTransform（几何级数闭式）/InverseZTransform（留数法）；与 Wolfram 15.0.1 差分 73/75 一致（余 2 个为数学等价的另一种写法，均已验证等价） | Hankel 变换、小波变换、广义函数完整语义 |
| 插值与拟合 | Interpolation/ListInterpolation（返回与 NDSolve 相同的可调用 InterpolatingFunction，默认三次样条）、InterpolatingPolynomial、Fit（精确最小二乘）、FindFit（scipy 数值拟合）；与 Wolfram 15.0.1 差分 38/38 一致 | 多维插值、样条 Method 选项全集 |
| 语言与数据结构 | 列表、Map/Select/Fold、关联、规则、模式、Module、递归、字符串与正则样例 | 完整求值语义、编译器、调试器、所有作用域与属性交互 |
| 二维可视化 | Mathics SVG 绘图及安全显示 | 全部图形原语、图表家族、交互选取、图像编辑及排版 |
| 三维可视化 | Plot3D 与基础 Graphics3D 几何；旋转、缩放 | 全部原语、材质、纹理、复杂光照、实体几何和体渲染 |
| 动态界面 | Manipulate 的数值范围控件、多参数和三维组合 | 任意 Dynamic/DynamicModule、离散/自定义控件、事件、自动依赖跟踪 |
| 文件与数据 | 本应用文档、WL 源码及基础 NB | 所有 Import/Export 格式、Dataset、数据库、外部设备、网络协议 |
| 单位与日期 | 一项单位换算通过 | 日期差样例未通过；完整日历、时区、单位推导与不确定度 |
| 图像、音频、视频 | 未形成完整用户工作流 | 编解码、滤波、分割、识别、信号处理与交互工具 |
| 机器学习与神经网络 | 未实现 | 训练、推理、模型管理、GPU 与模型资源 |
| 地理、科学与行业数据 | 未实现独立知识库 | 地图、实体、天文、化学、生物、工程与金融数据来源和更新 |
| 自然语言与 Wolfram\|Alpha | 未实现 | 自然语言解释与大规模计算知识服务 |
| 并行、编译与部署 | 本地持久计算进程，取消与超时恢复 | 多内核调度、GPU、Compile、LibraryLink、云部署、完整 paclet 生态 |

## 可重复的计算验收

`node scripts/verify-capabilities.cjs` 在真实 Mathics 进程中执行 69 个代表性断言，当前 **61 通过、8 存在差距**。这个比例只描述该验收集，不是全部 Mathematica 函数或产品功能的覆盖率。预期来自可检查的数学结果或语言行为；本轮没有启动 Mathematica 作为对照内核，因此这不是对目标软件完整行为的差分验证。发布前使用 `--refresh-view` 同步界面的本地报告。

完整输入、实际返回值、消息和耗时见 [capability-results.json](build/capability-results.json)。界面“功能覆盖与差距”显示同一批数据，可搜索函数、表达式或仅查看差距。当前未通过的样例：

| 类别 | 未通过样例 |
|---|---|
| 代数 | `PolynomialQuotient[x^3-1,x-1,x]` |
| 不等式 | `Reduce[x^2<1,x,Reals]` |
| 数值微分方程 | `NDSolve[{y'[x]==y[x],y[0]==1},y,{x,0,1}]` |
| 概率分布 | `CDF[NormalDistribution[0,1],0]` |
| 逻辑 | `BooleanMinimize[(a && b) || (a && !b)]` |
| 优化 | `Minimize[(x-2)^2,x]` |
| 日期 | 闰年 2 月 28 日至 3 月 1 日的 `DateDifference` |

图论的 `FindShortestPath` 样例在 0.5.2 起通过（新增 34 个图论函数，见上表“图论”行），下次 `--refresh-view` 后会从未通过列表移除。

“未通过”表示当前断言未得到预期结果；不能据此断言整类功能完全不存在。下一批优先补这些实际缺口，随后扩充数据文件、Notebook 编辑和图形语义。每一批都需增加数学断言、错误处理、真实应用流程和打包运行验证。
