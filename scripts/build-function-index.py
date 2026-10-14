#!/usr/bin/env python3
"""Build renderer/function-index.json: every System` symbol the kernel actually
implements, with summary, usage signatures and a Chinese category.

Boots the real backend Kernel once so the index always matches the shipped
kernel (Mathics builtins plus this project's own modules). Run from the project
root:  .venv/bin/python scripts/build-function-index.py
"""

import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from kernel import Kernel  # noqa: E402
import mathics.core.load_builtin as load_builtin  # noqa: E402
from mathics.core.builtin import Builtin  # noqa: E402

# backend modules registered by compat.register_compatibility
BACKEND_MODULES = [
    "algebra_extras", "algebraic_roots", "assumption_integrate", "bernoulli",
    "dirichlet_sums", "discrete_limit", "dist_contracts", "dist_derived",
    "dist_rules", "distributions", "euler_sums_products", "graphs", "graphs2",
    "interpolation", "limit_guard", "list_rules", "list_string_extras",
    "misc_extras", "more_builtins", "numeric_extras", "plots_regions",
    "polynomial_extras", "result_polish", "series_expand", "special_functions",
    "special_functions2", "symbolic_extras", "transforms", "zeta_derivatives",
]

CATEGORIES = {
    "transforms": "积分变换", "interpolation": "插值与拟合",
    "graphs": "图论", "graphs2": "图论",
    "polynomial_extras": "多项式", "algebra_extras": "多项式",
    "misc_extras": "常用工具", "numeric_extras": "数值计算",
    "distributions": "概率统计", "dist_rules": "概率统计", "dist_derived": "概率统计",
    "special_functions": "特殊函数", "special_functions2": "特殊函数",
    "series_expand": "微积分", "limit_guard": "微积分", "discrete_limit": "微积分",
    "assumption_integrate": "微积分", "euler_sums_products": "微积分",
    "dirichlet_sums": "微积分", "zeta_derivatives": "微积分",
    "bernoulli": "数论", "list_string_extras": "列表与字符串", "list_rules": "列表与字符串",
    "plots_regions": "几何与绘图", "symbolic_extras": "符号计算",
    "more_builtins": "常用工具", "result_polish": "符号计算", "algebraic_roots": "多项式",
    "dist_contracts": "概率统计",
}
MATHICS_CATEGORIES = [
    (r"calculus|series|integr", "微积分"),
    (r"draw|graphics|plot", "绘图"),
    (r"intfns|numbertheory|combinator", "数论与组合"),
    (r"tensor|vectors|matrices|linalg", "线性代数"),
    (r"statistics|moments|distribut", "概率统计"),
    (r"specialfns|special", "特殊函数"),
    (r"arithfns|trig|hyperbolic|exptrig|elementary", "初等函数"),
    (r"algebra", "代数"), (r"numbers|atomic|numeric", "数值计算"),
    (r"string", "列表与字符串"), (r"list", "列表与字符串"),
    (r"logic|boolean", "逻辑"), (r"optimization", "优化"),
    (r"units|quantit|date", "单位与日期"), (r"image|colors", "图像"),
    (r"crypto", "密码"), (r"trace|debug|messages", "调试"),
    (r"files_io|importexport|binary|system", "文件与系统"),
    (r"options|assignments|evaluation|scoping|patterns|rules|procedural|functional", "语言核心"),
    (r"forms|layout|box|makeboxes", "排版"),
]

# Mathics docstrings: <dt>'Name'[$f$, $x$]<dd>... (quotes around the name only)
SIGNATURE_RE = re.compile(r"<dt>\s*'([^'<\[]+)'((?:\[[^\]]*\])?)")
EXAMPLE_RE = re.compile(r"^\s*>>\s+(.+)$", re.M)

# A few names whose Mathics module bucket reads wrong in Chinese.
CATEGORY_OVERRIDES = {
    "Solve": "方程与求解", "NSolve": "方程与求解", "DSolve": "方程与求解",
    "RSolve": "方程与求解", "FindRoot": "方程与求解", "SolveValues": "方程与求解",
    "NSolveValues": "方程与求解", "DSolveValue": "方程与求解", "NDSolveValue": "方程与求解",
    "Integrate": "微积分", "D": "微积分", "Sum": "微积分", "Product": "微积分",
    "Limit": "微积分", "Series": "微积分", "NDSolve": "方程与求解",
    "Minimize": "优化", "Maximize": "优化", "NMinimize": "优化", "NMaximize": "优化",
}


def signatures_of(doc: str) -> list[str]:
    if not doc:
        return []
    seen, out = set(), []
    for name, args in SIGNATURE_RE.findall(doc):
        sig = (name + args).replace("$", "").strip()
        if sig and sig not in seen:
            seen.add(sig)
            out.append(sig)
        if len(out) >= 4:
            break
    if not out:
        # No <dl><dt> usage lines: fall back to doctest examples, which double
        # as good insertion text.
        for example in EXAMPLE_RE.findall(doc):
            sig = example.strip()
            if sig and sig not in seen:
                seen.add(sig)
                out.append(sig)
            if len(out) >= 2:
                break
    return out


def mathics_category(module: str) -> str:
    for pattern, label in MATHICS_CATEGORIES:
        if re.search(pattern, module, re.I):
            return label
    return "其他"


def collect():
    Kernel()  # boot once: populates load_builtin._builtins
    entries = {}

    def put(name, summary, signatures, category):
        # Backend wrapper classes shadow Mathics builtins; keep whichever side
        # actually carries the docs rather than clobbering with empty fields.
        entry = entries.setdefault(name, {"name": name, "summary": "", "signatures": [], "category": category})
        entry["category"] = CATEGORY_OVERRIDES.get(name, category)
        if summary:
            entry["summary"] = summary
        if signatures:
            entry["signatures"] = signatures

    for fullname, instance in load_builtin._builtins.items():
        name = fullname.rsplit("`", 1)[-1]
        if name.startswith("$"):
            continue
        put(name, getattr(instance, "summary_text", "") or "",
            signatures_of(getattr(instance, "__doc__", "") or ""),
            mathics_category(type(instance).__module__))
    for module_name in BACKEND_MODULES:
        module = __import__(module_name)
        category = CATEGORIES.get(module_name, "其他")
        for _, cls in inspect.getmembers(
            module, lambda o: isinstance(o, type) and issubclass(o, Builtin) and o.__module__ == module_name
        ):
            try:
                instance = cls(expression=False)
            except Exception:
                continue
            name = (getattr(cls, "name", None) or cls.__name__).rsplit("`", 1)[-1]
            put(name, getattr(instance, "summary_text", "") or "",
                signatures_of(getattr(instance, "__doc__", "") or ""), category)
    result = [e for e in entries.values() if e["summary"] or e["signatures"]]
    result.sort(key=lambda e: e["name"].lower())
    return result


def main():
    index = collect()
    # Emit a deferred script, not raw JSON: the renderer CSP allows self scripts
    # but fetch() of a .json from the packaged file:// bundle is unreliable.
    out = ROOT / "renderer" / "function-index.js"
    payload = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    out.write_text(
        "/* Generated by scripts/build-function-index.py — do not edit. */\n"
        f"globalThis.FUNCTION_INDEX = {payload};\n",
        encoding="utf-8",
    )
    print(f"{len(index)} entries -> {out} ({out.stat().st_size} bytes)")
    for probe in ("LaplaceTransform", "Graph", "Interpolation", "FindClique", "NRoots", "ArgMin"):
        assert any(e["name"] == probe for e in index), f"missing: {probe}"
    print("probe OK")


if __name__ == "__main__":
    main()
