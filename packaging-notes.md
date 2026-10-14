# Standalone Mathics kernel packaging

The Electron application embeds a PyInstaller `onedir` worker. It runs its
bundled CPython and Mathics dependencies directly and does not require a
system Python installation or Wolfram software.

Build on macOS arm64 using the project's Python 3.12 venv:

```sh
.venv/bin/python scripts/build-kernel.py
```

The fixed output is `build/kernel/mathematics-kernel/mathematics-kernel`,
with sibling `_internal` resources. Copy the **whole directory** into the
Electron application's resources. PyInstaller includes the Python shared
library, extension modules, and dependent scientific libraries. Mathics scans
Python files on disk when registering builtins and graphics renderers, so the
script collects raw `mathics` and `mathics_scanner` Python files as well as
their dynamically imported modules, Wolfram Language autoload files and JSON
operator/character tables. SymPy and SciPy dynamic imports and data are
collected, with development tests omitted. Distribution metadata is copied
recursively because the backend checks the Mathics version at runtime.

The build writes `BUILD-INFO.json` beside the executable and
`build/kernel-smoke.json` outside the bundle. The standalone smoke check uses
`PATH=/usr/bin:/bin`, removes Python/Wolfram environment variables, and runs
from `/private/tmp`. The 0.2 verification checks twelve real inputs: plain and
algebraic-extension Factor, D, Integrate, variables, Plot SVG, Print, diagnostic
results, Plot3D geometry and initial/updated Manipulate controls through the
worker's JSON-lines protocol. `backend_source_sha256` records every runtime
Python module, including the independent compatibility and graphics adapters.
Recheck an existing bundle with:

```sh
.venv/bin/python scripts/build-kernel.py --verify-only
```

Python and installed dependency notices, complete available license texts and
release metadata are preserved under `_internal/THIRD_PARTY`. Mathics3 and
Mathics3-Scanner are GPL-3.0-or-later. Their source/data trees are included in
`_internal/mathics` and `_internal/mathics_scanner`, and their upstream source
URLs are recorded in the notice index. The application source and license are
delivered with the project. A future public release should verify the complete
corresponding-source delivery for its selected dependency versions.

This build uses PyInstaller's automatic ad-hoc signing for macOS arm64.
It is a local development distribution; no Apple Developer ID identity or
notarization is claimed. No Wolfram executable, library, license, artwork or
other application assets are copied.

Historical 0.1 build on 2026-10-10: CPython 3.12.3, Mathics3/Scanner 10.0.1,
PyInstaller 6.22.3 and hooks-contrib 2026.8. The bundle is about **119 MiB
on disk** (122,673,751 unique file bytes) and includes **218 native files**.
`otool -L` across all native files found no absolute non-system dependency:
all libraries resolve inside the bundle or under `/usr/lib` and
`/System/Library`. The main executable is a Mach-O arm64 binary, linking
only libSystem and libz directly. The bundled CPython framework and
scientific extension dependencies are verified separately in the audit.

In that historical 0.1 build, all eight standalone smoke inputs passed with
empty stderr. These eight inputs are not the current 0.2 twelve-input check. The factor
result was `(-1 + x) (1 + x)`, the derivative `Cos[x]`, the integral `x ^ 2`,
and a remembered variable evaluated to `49`. Plot produced a 28,275-byte
SVG curve; Print and `1/0` diagnostics remained separate protocol fields.
A separate process reached the ready event in **6.682 seconds**, answered
health, and exited successfully. Initial sandboxed cold-start probes were
slower than short 10–15-second deadlines; the complete 90-second verification
passed, and the subsequent unrestricted run passed. No sandbox diagnosis is
inferred solely from that timing difference.

The historical 0.1 bundled backend source hash was:
`49404edaf439d0e0db5e11cac3ffe52f57dfb4354f2d74daa565ca50f4c1578c`.
The historical 0.1 worker executable hash before Electron app signing was
`6270ccce778eaf4e0de016127b04f15b5c1522a64d963aadf9b873b2423dccc4`.
The historical 0.1 notice index preserved **31 package records** plus the CPython license.
These results cover the tested independent kernel features, rather than
complete Mathematica compatibility. The current 0.2 hashes, native dependency
audit and twelve-input results are in `build/kernel-smoke.json` and the bundle's
`BUILD-INFO.json`. The final 0.2.0 Electron application separately passed all
15 desktop smoke checks; evidence, screenshots and the package identity are
linked from `VERIFICATION.md`. The current application's 13 runtime source
files match their packaged asar counterparts byte for byte. Historical 0.1
kernel and desktop results are not used as evidence for this 0.2 verification.

References:

- [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html)
- [Collection hooks and metadata](https://pyinstaller.org/en/stable/hooks.html)
- [macOS architecture and signing](https://pyinstaller.org/en/stable/feature-notes.html)
- [Mathics3 10.0.1 dynamic builtin loader](https://github.com/Mathics3/mathics-core/blob/10.0.1/mathics/core/load_builtin.py)
