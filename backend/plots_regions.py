"""ContourPlot and basic region measures.

  ContourPlot[f, {x, xmin, xmax}, {y, ymin, ymax}]      contour lines of f (default 10 levels)
  ContourPlot[f == c, ...]                               single implicit curve
  ContourPlot[{f1 == c1, f2 == c2}, ...]                 several implicit curves
      options: Contours -> n | {c1, c2, ...}, PlotPoints -> n

  Area[region]            Disk, Rectangle, Polygon, Circle(=0), Triangle
  Volume[region]          Ball, Cuboid, Cylinder, Cone
  RegionMeasure[region]   dispatches on region dimension

Contours are found by marching squares on a PlotPoints×PlotPoints grid and
returned as ``Graphics[{Line[...], ...}]`` so the notebook's existing SVG
pipeline renders them.  Region measures are exact symbolic formulas.
"""

from __future__ import annotations

import math

import sympy

from mathics.core.atoms import Integer, MachineReal, Real
from mathics.core.attributes import A_HOLD_ALL, A_PROTECTED, A_READ_PROTECTED
from mathics.core.builtin import Builtin
from mathics.core.convert.sympy import from_sympy
from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.core.symbols import Symbol

SymbolGraphics = Symbol("System`Graphics")
SymbolLine = Symbol("System`Line")
SymbolRule = Symbol("System`Rule")
SymbolHue = Symbol("System`Hue")
SymbolRGBColor = Symbol("System`RGBColor")


# ---------------------------------------------------------------------------
# marching squares
# ---------------------------------------------------------------------------

def _marching_squares(grid, xs, ys, level):
    """Return a list of polylines (lists of (x, y)) for grid == level."""
    nx, ny = len(xs), len(ys)
    segs = []

    def interp(p1, v1, p2, v2):
        if v1 == v2:
            return p1
        t = (level - v1) / (v2 - v1)
        return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))

    for i in range(nx - 1):
        for j in range(ny - 1):
            v = [grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]
            if any(not math.isfinite(t) for t in v):
                continue
            p = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
            idx = sum(1 << k for k in range(4) if v[k] >= level)
            if idx in (0, 15):
                continue
            e = [interp(p[0], v[0], p[1], v[1]), interp(p[1], v[1], p[2], v[2]),
                 interp(p[2], v[2], p[3], v[3]), interp(p[3], v[3], p[0], v[0])]
            table = {
                1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 5: [(3, 0), (1, 2)],
                6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)],
                11: [(1, 2)], 12: [(1, 3)], 13: [(0, 1)], 14: [(3, 0)],
            }
            for a, b in table[idx]:
                segs.append((e[a], e[b]))
    # chain segments into polylines
    from collections import defaultdict
    key = lambda pt: (round(pt[0], 9), round(pt[1], 9))
    adj = defaultdict(list)
    for s_idx, (a, b) in enumerate(segs):
        adj[key(a)].append(s_idx)
        adj[key(b)].append(s_idx)
    used = [False] * len(segs)
    lines = []
    for s_idx in range(len(segs)):
        if used[s_idx]:
            continue
        used[s_idx] = True
        a, b = segs[s_idx]
        line = [a, b]
        for end_is_tail in (True, False):
            while True:
                cur = key(line[-1] if end_is_tail else line[0])
                nxt = next((k for k in adj[cur] if not used[k]), None)
                if nxt is None:
                    break
                used[nxt] = True
                pa, pb = segs[nxt]
                other = pb if key(pa) == cur else pa
                if end_is_tail:
                    line.append(other)
                else:
                    line.insert(0, other)
        lines.append(line)
    return lines


class ContourPlot(Builtin):
    attributes = A_HOLD_ALL | A_PROTECTED | A_READ_PROTECTED
    # Mathematica draws a ticked frame by default; the Mathics SVG renderer only
    # implements Axes, so axes through the origin are the default here.
    options = {"Contours": "10", "PlotPoints": "60", "PlotRange": "Automatic", "AspectRatio": "Automatic", "Frame": "False", "Axes": "True"}
    messages = {"invfun": "`1` is not a valid function or equation of two variables."}
    summary_text = "contour plot of a function of two variables"

    def eval(self, f, xspec, yspec, evaluation, options):
        "ContourPlot[f_, xspec_List, yspec_List, OptionsPattern[ContourPlot]]"
        if not (xspec.has_form("List", 3) and yspec.has_form("List", 3)):
            return None
        x, x0, x1 = xspec.elements
        y, y0, y1 = yspec.elements
        if not (isinstance(x, Symbol) and isinstance(y, Symbol)):
            return None
        try:
            xa, xb = float(x0.evaluate(evaluation).to_sympy()), float(x1.evaluate(evaluation).to_sympy())
            ya, yb = float(y0.evaluate(evaluation).to_sympy()), float(y1.evaluate(evaluation).to_sympy())
        except Exception:
            return None
        f_eval = f.evaluate(evaluation)
        # Determine (expression, levels) pairs
        specs = []
        items = f_eval.elements if f_eval.has_form("List", None) else (f_eval,)
        explicit_levels = None
        for it in items:
            if it.get_head_name() == "System`Equal" and len(it.elements) == 2:
                lhs, rhs = it.elements
                e = (lhs.to_sympy(), rhs.to_sympy())
                if e[0] is None or e[1] is None:
                    return None
                specs.append((e[0] - e[1], [0.0]))
            else:
                e = it.to_sympy()
                if e is None:
                    return None
                specs.append((e, None))
        cont = options.get("System`Contours")
        if cont is not None:
            if cont.has_form("List", None):
                explicit_levels = [float(c.to_sympy()) for c in cont.elements]
            else:
                n_lev = cont.get_int_value()
        else:
            n_lev = 10
        npts = options.get("System`PlotPoints").get_int_value() or 60
        npts = max(10, min(npts, 300))
        xs = [xa + (xb - xa) * i / (npts - 1) for i in range(npts)]
        ys = [ya + (yb - ya) * j / (npts - 1) for j in range(npts)]
        x_s, y_s = x.to_sympy(), y.to_sympy()
        prims = []
        for idx, (expr, levels) in enumerate(specs):
            try:
                fn = sympy.lambdify((x_s, y_s), expr, modules=["math", "numpy"])
            except Exception:
                return None
            grid = []
            for xv in xs:
                col = []
                for yv in ys:
                    try:
                        val = fn(xv, yv)
                        val = float(val.real if isinstance(val, complex) else val)
                    except Exception:
                        val = float("nan")
                    col.append(val)
                grid.append(col)
            if levels is None:
                vals = [v for col in grid for v in col if math.isfinite(v)]
                if not vals:
                    return None
                lo, hi = min(vals), max(vals)
                if explicit_levels is not None:
                    levels = explicit_levels
                else:
                    levels = [lo + (hi - lo) * (k + 1) / (n_lev + 1) for k in range(n_lev)]
            hue = idx / max(1, len(specs))
            color = Expression(SymbolHue, MachineReal(hue), MachineReal(0.75), MachineReal(0.6)) if len(specs) > 1 else Expression(SymbolRGBColor, MachineReal(0.2), MachineReal(0.35), MachineReal(0.8))
            prims.append(color)
            for lev in levels:
                for line in _marching_squares(grid, xs, ys, lev):
                    pts = ListExpression(*(ListExpression(MachineReal(px), MachineReal(py)) for px, py in line))
                    prims.append(Expression(SymbolLine, pts))
        axes = options.get("System`Axes")
        frame = options.get("System`Frame")
        show_axes = (axes is not None and axes.get_name() == "System`True") or (frame is not None and frame.get_name() == "System`True")
        aspect = options.get("System`AspectRatio")
        if aspect is None or aspect.get_name() == "System`Automatic":
            # Automatic = true geometric aspect (unit lengths equal on both axes)
            aspect_val = MachineReal(abs(yb - ya) / abs(xb - xa)) if xb != xa else Integer(1)
        else:
            aspect_val = aspect
        opts = [
            Expression(SymbolRule, Symbol("System`PlotRange"), ListExpression(ListExpression(MachineReal(xa), MachineReal(xb)), ListExpression(MachineReal(ya), MachineReal(yb)))),
            Expression(SymbolRule, Symbol("System`Axes"), Symbol("System`True" if show_axes else "System`False")),
            Expression(SymbolRule, Symbol("System`AspectRatio"), aspect_val),
        ]
        return Expression(SymbolGraphics, ListExpression(*prims), *opts)


# ---------------------------------------------------------------------------
# region measures
# ---------------------------------------------------------------------------

def _num(e):
    s = e.to_sympy()
    return s


def _area(region):
    head = region.get_head_name().split("`")[-1]
    el = region.elements
    if head == "Disk":
        r = _num(el[1]) if len(el) >= 2 else sympy.Integer(1)
        if r is None:
            return None
        if isinstance(r, tuple) or (len(el) >= 2 and el[1].has_form("List", 2)):
            a, b = (_num(t) for t in el[1].elements)
            return sympy.pi * a * b
        if len(el) >= 3 and el[2].has_form("List", 2):
            t0, t1 = (_num(t) for t in el[2].elements)
            return r**2 * (t1 - t0) / 2
        return sympy.pi * r**2
    if head == "Circle":
        return sympy.Integer(0)
    if head == "Rectangle":
        if len(el) == 0:
            return sympy.Integer(1)
        p0 = [_num(t) for t in el[0].elements]
        p1 = [_num(t) for t in el[1].elements] if len(el) > 1 else [p0[0] + 1, p0[1] + 1]
        return sympy.Abs((p1[0] - p0[0]) * (p1[1] - p0[1]))
    if head in ("Polygon", "Triangle"):
        pts = [[_num(t) for t in p.elements] for p in el[0].elements]
        if any(len(p) != 2 for p in pts):
            return None
        s = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        return sympy.Abs(s) / 2
    if head == "RegularPolygon":
        n = el[-1].get_int_value() if el else 5
        r = _num(el[1]) if len(el) >= 3 else sympy.Integer(1)
        return sympy.Rational(n, 2) * r**2 * sympy.sin(2 * sympy.pi / n)
    return None


def _volume(region):
    head = region.get_head_name().split("`")[-1]
    el = region.elements
    if head == "Ball":
        r = _num(el[1]) if len(el) >= 2 else sympy.Integer(1)
        return sympy.Rational(4, 3) * sympy.pi * r**3
    if head == "Sphere":
        return sympy.Integer(0)
    if head == "Cuboid":
        p0 = [_num(t) for t in el[0].elements]
        p1 = [_num(t) for t in el[1].elements] if len(el) > 1 else [c + 1 for c in p0]
        v = sympy.Integer(1)
        for a, b in zip(p0, p1):
            v *= sympy.Abs(b - a)
        return v
    if head == "Cylinder":
        pts = el[0].elements if el else None
        r = _num(el[1]) if len(el) >= 2 else sympy.Integer(1)
        if pts is None:
            h = sympy.Integer(2)
        else:
            a, b = ([_num(t) for t in p.elements] for p in pts)
            h = sympy.sqrt(sum((u - v) ** 2 for u, v in zip(a, b)))
        return sympy.pi * r**2 * h
    if head == "Cone":
        pts = el[0].elements if el else None
        r = _num(el[1]) if len(el) >= 2 else sympy.Integer(1)
        if pts is None:
            h = sympy.Integer(2)
        else:
            a, b = ([_num(t) for t in p.elements] for p in pts)
            h = sympy.sqrt(sum((u - v) ** 2 for u, v in zip(a, b)))
        return sympy.pi * r**2 * h / 3
    return None


class Area(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "area of a two-dimensional region"

    def eval(self, region, evaluation):
        "Area[region_]"
        a = _area(region)
        return from_sympy(sympy.simplify(a)) if a is not None else None


class Volume(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "volume of a three-dimensional region"

    def eval(self, region, evaluation):
        "Volume[region_]"
        v = _volume(region)
        return from_sympy(sympy.simplify(v)) if v is not None else None


class RegionMeasure(Builtin):
    attributes = A_PROTECTED | A_READ_PROTECTED
    summary_text = "measure of a region"

    def eval(self, region, evaluation):
        "RegionMeasure[region_]"
        head = region.get_head_name().split("`")[-1]
        if head in ("Ball", "Cuboid", "Cylinder", "Cone"):
            v = _volume(region)
        elif head == "Sphere":
            r = _num(region.elements[1]) if len(region.elements) >= 2 else sympy.Integer(1)
            v = 4 * sympy.pi * r**2
        elif head == "Circle":
            r = _num(region.elements[1]) if len(region.elements) >= 2 else sympy.Integer(1)
            v = 2 * sympy.pi * r
        elif head == "Line":
            pts = [[_num(t) for t in p.elements] for p in region.elements[0].elements]
            v = sum(sympy.sqrt(sum((a - b) ** 2 for a, b in zip(pts[i], pts[i + 1]))) for i in range(len(pts) - 1))
        else:
            v = _area(region)
        return from_sympy(sympy.simplify(v)) if v is not None else None


def register_plots_regions(session):
    for cls in (ContourPlot, Area, Volume, RegionMeasure):
        cls(expression=False).contribute(session.definitions)
        session.definitions.clear_cache(f"System`{cls.__name__}")
    for name in ("Ball", "Cuboid", "Cylinder", "Cone", "Sphere", "Triangle", "RegularPolygon"):
        session.definitions.get_definition(f"System`{name}")
