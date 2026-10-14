# Mathics backend

This worker uses the independent, pinned `Mathics3==10.0.1` engine. It does not
load or execute a Wolfram installation. Run it using the project's Python
virtual environment:

```sh
.venv/bin/python backend/kernel.py
```

stdin and stdout carry one JSON object per line. The first stdout message is
`{"event":"ready","engine":"Mathics3","version":"10.0.1","protocol":1}`.
Initialization errors go to stderr and exit with status 1, without announcing
readiness. Import diagnostics and language `Print` never become protocol lines.

Requests require a string or integer `id`. Operations:

- `evaluate`: `source` string plus optional `notebook_id` (default `"default"`)
  and `controls` object mapping declared interactive symbols to numeric values.
  Returns `text`, `line`, `elapsed_ms`, `messages`, `prints`, `suppressed`, and
  optional derived `latex`, `svg`, `graphics3d` and `interactive`.
- `reset`: optional `notebook_id`. Replaces that notebook's language session,
  clearing variables and input/output history. Returns `reset: true` and `line: 0`.
- `health`: returns engine version, readiness and session count.

Every response is `{"id":...,"ok":true,"result":...}` or
`{"id":...,"ok":false,"error":{"code":...,"message":...}}`.
Malformed JSON has a null response id and error code `invalid_json`.

The worker parses once with the session evaluator and calls
`Evaluation.evaluate(query, format="text")`, the history/message path used by
`MathicsSession.evaluate_as_in_cli`. It updates `$Line`, `In` and `Out`, returns
`Print` events and evaluator messages,
and suppresses a `Null` result caused by a final semicolon. Parser messages
tagged `Syntax` become `syntax_error`; evaluator warnings stay in a successful
result. Derived display conversion uses the already evaluated `last_eval`
expression, so user assignments and other effects run once. Two-dimensional
`Graphics` use Mathics' SVG boxes formatter; other expressions use the LaTeX
formatter. A 2D/LaTeX conversion failure preserves text and adds a display
message. A failed 3D conversion returns an explicit error rather than an empty
successful visualization.

## Three-dimensional geometry

`Graphics3D` and native `Plot3D` results use Mathics' actual graphics boxes and
JSON primitive exporter. The adapter emits data-space coordinates before native
`BoxRatios` scaling. Native surface samples are retained, and display primitives
are tessellated: `Polygon`, `Line`, `Point`, `Cuboid`, `Sphere`, two-endpoint
`Cylinder` and `Cone` are supported. The equivalent `Cuboid[pmin,pmax]` syntax
is normalized to Mathics' supported `Cuboid[{pmin,pmax}]` display AST without
evaluating the expression again. Sphere/cylinder/cone mesh resolution is fixed
at 24 longitude segments (sphere has 12 latitude bands).

The result field is:

```js
graphics3d: {
  vertices: [[x,y,z]], faces: [[vertexIndex,...]],
  lines: [[[x,y,z],...]], points: [[x,y,z]],
  colors: { faces: [[r,g,b]], lines: [[r,g,b]], points: [[r,g,b]] },
  bounds: [[xmin,xmax],[ymin,ymax],[zmin,zmax]],
  boxScale: [sx,sy,sz], viewpoint: [x,y,z], axes: [true,false,false],
  coordinateSpace: "data", source: "Mathics3 graphics boxes"
}
```

Color arrays are parallel to their primitive arrays. All coordinates/colors
must be finite; colors are RGB in `[0,1]`. Limits are 50,000 unique face vertices,
30,000 faces, 10,000 lines, 10,000 points and 150,000 total coordinate references.
Exceeding a limit produces `graphics3d_too_large`. `Arrow`, `Tube`, text,
screen-space offsets and per-vertex colors are explicitly unsupported. This
mesh protocol does not reproduce opacity, lighting, point size, line thickness
or all graphics options. In pinned Mathics, 3D extent calculation uses automatic
data bounds even when explicit `PlotRange` is supplied.

Examples:

```wl
Plot3D[Sin[x y], {x,-3,3}, {y,-3,3}, PlotPoints->12, MaxRecursion->0]
Graphics3D[{Red,Sphere[{0,0,0}],Blue,Cuboid[{1,1,1},{2,2,2}]}]
```

## Numeric Manipulate subset

One top-level `Manipulate` per cell is supported, optionally followed by one
semicolon. Its body is parsed and held before evaluation; range validation
does not execute the body. Accepted control forms are:

```wl
Manipulate[expr, {a,min,max}]
Manipulate[expr, {a,min,max,step}]
Manipulate[expr, {{a,initial},min,max,step}]
Manipulate[expr, {{a,initial,"Label"},min,max,step}, {b,min,max}]
```

At most 12 distinct unprotected user symbols are accepted. Bounds, initial
values and steps must be finite numeric constants; arithmetic, `Pi`, `E` and a
small set of numeric functions (`N`, `Sin`, `Cos`, `Tan`, `Exp`, `Log`, `Sqrt`,
`Abs`) are accepted. Dependent ranges, symbolic bounds, list/menu controls,
nested `Manipulate`, options and arbitrary user code in range specifications
return explicit errors. The default value is `min`; the default UI step is
`(max-min)/100`. Explicit steps constrain values to the declared step grid.

The evaluated body result includes:

```js
interactive: { controls: [
  {symbol:"a", label:"a", min:0, max:5, step:0.05, value:3}
] }
```

For example, send `source: "Manipulate[a^2,{a,0,5}]"` with `controls: {a:3}`
to obtain `text: "9"`. Updates evaluate the original parsed body once with
Mathics local bindings, including any intentional body side effects. Bindings
remain active through SVG/3D conversion and are restored on success or error;
control variables do not overwrite notebook definitions. Every update is a
normal history line: `In[n]` stores the original declaration, and `Out[n]`
stores the actual result. A trailing semicolon executes the body but suppresses
its display and controls. This is a request-driven numeric control subset,
not a full `Dynamic` dependency tracker or Mathematica frontend implementation.

```wl
Manipulate[Plot[Sin[a x],{x,-Pi,Pi}],{{a,1,"Frequency"},0.5,3,0.1}]
Manipulate[Plot3D[Sin[a x y],{x,-2,2},{y,-2,2},PlotPoints->12,
  MaxRecursion->0],{a,0.5,3}]
```

## Algebraic-field Factor option

`compat.py` registers an independent Mathics builtin adapter for `Factor` in
every new/reset notebook session. Plain `Factor[expr]` delegates to the native
Mathics implementation, preserving its list/equation/rational-expression
behavior. `Factor[expr, Extension -> algebraicNumber]` and a list of at most
eight exact algebraic numbers use Mathics AST-to-SymPy conversion followed by
`sympy.factor(..., extension=...)` and native conversion back to Mathics.
Neither the polynomial nor the option is reparsed or evaluated a second time.

For example:

```wl
Factor[x^4 + 1, Extension -> Sqrt[2]]
(* (1 - Sqrt[2] x + x^2) (1 + Sqrt[2] x + x^2) *)
```

This option supports polynomial and rational expressions, exact algebraic
generators such as `Sqrt[2]` or `I`, and lists of generators. Symbolic,
transcendental, approximate or `Automatic` extension values return
`unsupported_factor_extension`. Other Factor options, including `Modulus` and
`GaussianIntegers`, return `unsupported_factor_option`. This adapter supplies
the explicitly supported option subset; it does not claim full Factor option
compatibility. Tests assert both expanded mathematical equivalence and the
expected nontrivial factor structure.

The Electron parent owns wall-clock timeouts and cancellation by terminating
the worker. A terminated worker loses all notebook sessions, which the parent
must explain when restarting. The worker does not rely on Mathics' internal
timeout argument for this guarantee.

Tests run the real engine, including symbolic operations, state isolation,
history, `Print`, syntax errors, messages, SVG, real 3D surface samples,
primitive tessellation, numeric controls and their isolation/error behavior:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
```

API references for the fixed upstream version:

- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/session.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/core/evaluation.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/core/formatter.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/test/format/test_svg.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/format/render/json.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/format/box/graphics3d.py
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/eval/scoping.py
- https://reference.wolfram.com/language/ref/Manipulate.html
- https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/builtin/numbers/algebra.py
- https://docs.sympy.org/latest/modules/polys/reference.html#sympy.polys.polytools.factor
