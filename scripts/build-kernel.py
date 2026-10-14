#!/usr/bin/env python3
"""Build a relocatable macOS arm64 Mathics worker, with no network access.

Run with the project's Python 3.12 venv. The output is an onedir executable
and its _internal resources; keep the entire directory when packaging Electron.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig


PROJECT = Path(__file__).resolve().parents[1]
BUILD = PROJECT / "build"
BUNDLE = BUILD / "kernel" / "mathematics-kernel"
SOURCE = PROJECT / "backend" / "kernel.py"


SPEC = r'''
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).resolve().parents[1]
datas, binaries, hiddenimports = [], [], []

def keep_module(name):
    return not any(part in {"test", "tests", "testing", "benchmarks"}
                   for part in name.split("."))

# Mathics discovers builtins and format renderers with filesystem glob(.py).
# Their Python source files must exist beside packaged WL/JSON data, even
# when the same imports also occur in the PYZ archive.
for package in ("mathics", "mathics_scanner", "sympy", "scipy", "networkx"):
    d, b, h = collect_all(
        package, include_py_files=package in {"mathics", "mathics_scanner"},
        filter_submodules=keep_module,
        exclude_datas=["**/tests/**", "**/test/**", "**/testing/**",
                       "**/benchmarks/**", "**/__pycache__/**"],
        on_error="warn once",
    )
    datas += d
    binaries += b
    hiddenimports += h

# Kernel's version check and dependencies query distribution metadata.
datas += copy_metadata("Mathics3", recursive=True)
datas += [(str(root / "build" / "kernel-notices"), "THIRD_PARTY")]

a = Analysis(
    [str(root / "backend" / "kernel.py")],
    pathex=[str(root / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "jupyter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="mathematics-kernel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="mathematics-kernel")
'''


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_hashes() -> dict[str, str]:
    return {str(path.relative_to(PROJECT)): sha256(path)
            for path in sorted((PROJECT / "backend").rglob("*.py"))
            if "tests" not in path.parts and "__pycache__" not in path.parts}


def prepare_notices() -> dict[str, str]:
    """Preserve installed release metadata and license files, without fetching."""
    destination = BUILD / "kernel-notices"
    destination.mkdir(parents=True, exist_ok=True)
    packages = []
    versions = {}
    for distribution in sorted(metadata.distributions(),
                               key=lambda d: d.metadata.get("Name", "")):
        name = distribution.metadata.get("Name", "unknown")
        if name.lower() == "pip":
            continue
        versions[name] = distribution.version
        package_dir = destination / f"{name}-{distribution.version}"
        package_dir.mkdir(parents=True, exist_ok=True)
        package_dir.joinpath("METADATA.txt").write_text(
            distribution.read_text("METADATA") or "", encoding="utf-8")
        licenses = []
        for relative in distribution.files or []:
            if not any(token in relative.name.lower()
                       for token in ("license", "copying", "notice")):
                continue
            original = Path(distribution.locate_file(relative))
            if not original.is_file():
                continue
            # Preserve full relative names; packages can contain several
            # distinct vendored licenses sharing the same basename.
            safe_relative = Path(*[part for part in relative.parts
                                  if part not in {"..", "."}])
            target = package_dir / safe_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            licenses.append(str(safe_relative))
        packages.append({
            "name": name, "version": distribution.version,
            "license": distribution.metadata.get("License-Expression")
                       or distribution.metadata.get("License", ""),
            "project_urls": distribution.metadata.get_all("Project-URL", []),
            "license_files": licenses,
        })
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(f"Python license not found: {python_license}")
    shutil.copy2(python_license, destination / "PYTHON-LICENSE.txt")
    # Include PyInstaller's complete GPL/bootloader-exception notice above,
    # along with runtime dependencies. Tool packages are labelled by name.
    destination.joinpath("INDEX.json").write_text(json.dumps({
        "python": platform.python_version(), "packages": packages,
        "mathics_source": "https://github.com/Mathics3/mathics-core/tree/10.0.1",
        "scanner_source": "https://github.com/Mathics3/mathics-scanner/tree/10.0.1",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    destination.joinpath("README.txt").write_text(
        "This independent kernel bundles CPython, Mathics3 and Python dependencies.\n"
        "License texts and release metadata are preserved in this directory.\n"
        "Mathics3 and Mathics3-Scanner are GPL-3.0-or-later. Their Python source\n"
        "and data are also present in the adjacent _internal package trees.\n"
        "The index includes build-tool notices as well as runtime dependencies.\n"
        "No Wolfram executable, library, license or artwork is included.\n",
        encoding="utf-8")
    return versions


def smoke_test(executable: Path) -> dict:
    """Exercise the shipped Mach-O, not venv Python, from outside the source tree."""
    inputs = [
        ("factor", "Factor[x^2-1]"),
        ("derivative", "D[Sin[x],x]"),
        ("integral", "Integrate[2 x,x]"),
        ("assignment", "a=7"),
        ("variable", "a^2"),
        ("plot", "Plot[Sin[x],{x,0,2 Pi}]"),
        ("print", 'Print["kernel smoke"]'),
        ("message", "1/0"),
        ("factor-extension", "Factor[x^4+1,Extension->Sqrt[2]]"),
        ("plot3d", "Plot3D[Sin[x] Cos[y],{x,-2,2},{y,-2,2}]"),
        ("manipulate", "Manipulate[a^2,{a,0,5}]"),
        ("manipulate-update", "Manipulate[a^2,{a,0,5}]"),
        ("solve-root-quintic", "Solve[x^5-5 x+6==0,x]"),
        ("solve-root-decic", "Solve[x^10-5 x+6==0,x]"),
    ]
    requests = [{"id": label, "op": "evaluate", "source": source}
                for label, source in inputs]
    next(request for request in requests if request["id"] == "manipulate-update")["controls"] = {"a": 3}
    data = "".join(json.dumps(item) + "\n" for item in requests)
    # Python and Wolfram executable lookup cannot work through this PATH.
    # Removing these variables also proves no source-tree PYTHONPATH is needed.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("PYTHON", "WOLFRAM", "MATHEMATICA"))}
    environment["PATH"] = "/usr/bin:/bin"
    process = subprocess.run([str(executable)], input=data, text=True,
                             capture_output=True, timeout=90,
                             cwd="/private/tmp", env=environment)
    if process.returncode:
        raise RuntimeError(f"Frozen kernel exited {process.returncode}:\n{process.stderr}")
    events = [json.loads(line) for line in process.stdout.splitlines() if line]
    if not events or events[0].get("event") != "ready":
        raise RuntimeError(f"Missing ready event: {process.stdout[:2000]}")
    replies = {item.get("id"): item for item in events[1:]}
    for request in requests:
        if not replies.get(request["id"], {}).get("ok"):
            raise RuntimeError(f"Smoke input failed: {request}: {replies.get(request['id'])}")
    if replies["variable"]["result"]["text"] != "49":
        raise RuntimeError("Frozen kernel did not preserve session variables")
    factor = replies["factor"]["result"]["text"].replace(" ", "")
    if "(-1+x)" not in factor or "(1+x)" not in factor:
        raise RuntimeError("Frozen Factor did not produce both polynomial factors")
    if replies["integral"]["result"]["text"].replace(" ", "") != "x^2":
        raise RuntimeError("Frozen integral result did not match x^2")
    if "Cos[x]" not in replies["derivative"]["result"]["text"]:
        raise RuntimeError("Frozen derivative result did not match Cos[x]")
    svg = replies["plot"]["result"].get("svg", "")
    if "<svg" not in svg or "<polyline" not in svg:
        raise RuntimeError("Frozen Plot did not produce a real SVG curve")
    if "kernel smoke" not in replies["print"]["result"]["prints"]:
        raise RuntimeError("Frozen worker did not preserve Print output")
    if not replies["message"]["result"]["messages"]:
        raise RuntimeError("Frozen worker did not preserve 1/0 diagnostics")
    factor_extension = replies["factor-extension"]["result"]["text"].replace(" ", "")
    if factor_extension.count("x^2") != 2 or factor_extension.count("Sqrt[2]") != 2 or "Factor[" in factor_extension:
        raise RuntimeError("Frozen algebraic-extension factorization did not produce the two quadratic factors")
    graphics3d = replies["plot3d"]["result"].get("graphics3d", {})
    if len(graphics3d.get("vertices", [])) < 3 or not graphics3d.get("faces"):
        raise RuntimeError("Frozen Plot3D did not produce surface geometry")
    if not replies["manipulate"]["result"].get("interactive", {}).get("controls"):
        raise RuntimeError("Frozen Manipulate did not produce controls")
    if replies["manipulate-update"]["result"]["text"] != "9":
        raise RuntimeError("Frozen Manipulate parameter did not update evaluation")
    for label, count in [("solve-root-quintic", 5), ("solve-root-decic", 10)]:
        result = replies[label]["result"]
        preview = result.get("algebraic_roots", {})
        if len(preview.get("rows", [])) != count or preview.get("total") != count or preview.get("digits") != 12:
            raise RuntimeError(f"Frozen {label} did not provide every numeric root for display")
        if "Root[" not in result["text"] or any(not row.get("exact_latex") or not row.get("approximate_latex") for row in preview["rows"]):
            raise RuntimeError(f"Frozen {label} did not retain exact roots beside its preview")
    report = {
        "environment": "PATH=/usr/bin:/bin, no PYTHON*/WOLFRAM*/MATHEMATICA*",
        "cwd": "/private/tmp", "event": events[0],
        "outputs": {name: {key: value for key, value in reply["result"].items()
                            if key not in {"svg", "graphics3d"}} for name, reply in replies.items()},
        "plot_svg_bytes": len(svg.encode()),
        "plot3d_geometry": {"vertices": len(graphics3d["vertices"]), "faces": len(graphics3d["faces"])},
        "stderr": process.stderr,
    }
    return report


def audit_bundle() -> dict:
    """Reject native load commands which still depend on the build machine."""
    macho_magic = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                   b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
                   b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
    native_files = []
    byte_count = 0
    seen = set()
    for path in BUNDLE.rglob("*"):
        if not path.is_file() or path.resolve() in seen:
            continue
        seen.add(path.resolve())
        byte_count += path.stat().st_size
        with path.open("rb") as stream:
            if stream.read(4) in macho_magic:
                native_files.append(path)
    load_commands = {}
    invalid_paths = []
    for path in native_files:
        result = subprocess.run(["/usr/bin/otool", "-L", str(path)],
                                text=True, capture_output=True, check=True)
        dependencies = [line.strip().split(" (compatibility version", 1)[0]
                        for line in result.stdout.splitlines()[1:]
                        if line.startswith("\t")]
        load_commands[str(path.relative_to(BUNDLE))] = dependencies
        invalid_paths.extend((str(path.relative_to(BUNDLE)), dependency)
                             for dependency in dependencies
                             if dependency.startswith("/") and not
                             dependency.startswith(("/usr/lib/", "/System/Library/")))
    if invalid_paths:
        raise RuntimeError(f"Nonportable native dependencies: {invalid_paths}")
    return {"bundle_unique_file_bytes": byte_count,
            "native_file_count": len(native_files),
            "load_commands": load_commands,
            "external_non_system_native_dependencies": invalid_paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true",
                        help="Verify an already-built worker without rebuilding")
    options = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("Build on macOS arm64 with an arm64 Python runtime")
    if not options.verify_only:
        if metadata.version("Mathics3") != "10.0.1":
            raise RuntimeError("Install Mathics3==10.0.1 in the project venv first")
        versions = prepare_notices()
        spec_dir = BUILD / "pyinstaller-kernel"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec = spec_dir / "mathematics-kernel.spec"
        spec.write_text(SPEC.lstrip(), encoding="utf-8")
        environment = os.environ.copy()
        # Keep PyInstaller cache writes within this workspace.
        environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "pyinstaller-cache")
        subprocess.run([
            sys.executable, "-m", "PyInstaller", str(spec),
            "--noconfirm", "--distpath", str(BUILD / "kernel"),
            "--workpath", str(BUILD / "pyinstaller-work"),
            "--log-level", "INFO",
        ], cwd=PROJECT, env=environment, check=True)
        manifest = {"versions": versions, "python": platform.python_version(),
                    "architecture": platform.machine(),
                    "backend_source_sha256": source_hashes(),
                    "kernel_source_sha256": sha256(SOURCE)}
        BUNDLE.joinpath("BUILD-INFO.json").write_text(json.dumps(manifest, indent=2),
                                                 encoding="utf-8")
    executable = BUNDLE / "mathematics-kernel"
    manifest = json.loads(BUNDLE.joinpath("BUILD-INFO.json").read_text(encoding="utf-8"))
    if manifest.get("backend_source_sha256") != source_hashes():
        raise RuntimeError("The backend source changed after packaging; rebuild the kernel")
    report = smoke_test(executable)
    report["bundle_audit"] = audit_bundle()
    report["executable_sha256"] = sha256(executable)
    report["kernel_source_sha256"] = sha256(SOURCE)
    report["backend_source_sha256"] = source_hashes()
    report_path = BUILD / "kernel-smoke.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"Verified standalone kernel: {executable}")
    print(f"Verification report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
