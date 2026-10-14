#!/usr/bin/env python3
"""Persistent Mathics sessions exposed through a small JSON-lines protocol.

The Electron parent owns cancellation and wall-clock limits.  Evaluations and
display conversion happen once in this worker; killing it discards its sessions.
No Wolfram installation is used by this independently implemented backend.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import json
import sys
import threading
import time
import traceback
from typing import Any

from errors import RequestError


EXPECTED_VERSION = "10.0.1"
MAX_SOURCE_LENGTH = 100_000


class Kernel:
    """One stateful language session per notebook, with explicit reset."""

    def __init__(self) -> None:
        # Some optional Mathics modules print diagnostics while importing.
        # stdout is reserved exclusively for the protocol, including in tests.
        with contextlib.redirect_stdout(sys.stderr):
            self.version = importlib.metadata.version("Mathics3")
            if self.version != EXPECTED_VERSION:
                raise RuntimeError(
                    f"Mathics3 {EXPECTED_VERSION} is required; found {self.version}."
                )
            from mathics.session import MathicsSession
            from mathics.core.formatter import box_to_format
            from mathics.core.systemsymbols import SymbolStandardForm
            from mathics.core.load_builtin import import_and_load_builtins
            from mathics.format.box import format_element
            from mathics.core.evaluation import Result
            from mathics.core.rules import Rule
            from mathics.core.convert.expression import to_expression
            from mathics.eval.scoping import dynamic_scoping
            from interactive import prepare_evaluation
            from graphics3d import to_graphics3d, normalize_primitives
            from compat import register_compatibility
            from algebraic_roots import solution_preview

            self._session_type = MathicsSession
            self._box_to_format = box_to_format
            self._standard_form = SymbolStandardForm
            self._format_element = format_element
            self._result_type = Result
            self._rule_type = Rule
            self._to_expression = to_expression
            self._dynamic_scoping = dynamic_scoping
            self._prepare_evaluation = prepare_evaluation
            self._to_graphics3d = to_graphics3d
            self._normalize_graphics3d = normalize_primitives
            self._register_compatibility = register_compatibility
            self._solution_preview = solution_preview
            # The 10.0.1 wheel can raise ValueError (not the KeyError handled
            # by MathicsSession.reset) if its registry was never initialized.
            import_and_load_builtins()
            # Eager initialization catches missing engine dependencies before
            # announcing readiness, and warms Mathics' builtin registry.
            self._create_lock = threading.RLock()
            self.sessions: dict[str, Any] = {"default": self._new_session()}
            # Session creation re-parses all WL compat rules (~7 s, mostly the
            # distribution contracts). Keep one pre-warmed spare session so a
            # notebook's first cell does not pay that cost; refill in the
            # background after each take.
            self._pool_lock = threading.Lock()
            self._spare_sessions: list[Any] = []
            self._warming = False
            self._request_spare()

    def _request_spare(self) -> None:
        with self._pool_lock:
            if self._warming or self._spare_sessions:
                return
            self._warming = True
        threading.Thread(target=self._warm_spare, daemon=True).start()

    def _warm_spare(self) -> None:
        try:
            session = self._new_session()
        except Exception:
            session = None
        with self._pool_lock:
            self._warming = False
            if session is not None:
                self._spare_sessions.append(session)

    def _session_for(self, notebook_id: str) -> Any:
        session = self.sessions.get(notebook_id)
        if session is not None:
            return session
        with self._pool_lock:
            session = self._spare_sessions.pop() if self._spare_sessions else None
        if session is None:
            session = self._new_session()
        self._request_spare()
        self.sessions[notebook_id] = session
        return session

    def _new_session(self) -> Any:
        # Mathics' builtin registry is process-global during Definitions
        # construction; two concurrent creations race and corrupt it.
        with self._create_lock:
            session = self._session_type(form="text", catch_interrupt=True)
            self._register_compatibility(session)
        return session

    @staticmethod
    def _notebook_id(request: dict[str, Any]) -> str:
        value = request.get("notebook_id", "default")
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise RequestError("invalid_notebook", "notebook_id must be a nonempty string of at most 128 characters.")
        return value

    def dispatch(self, request: Any) -> dict[str, Any]:
        request_id = request.get("id") if isinstance(request, dict) else None
        try:
            if not isinstance(request, dict):
                raise RequestError("invalid_request", "The request must be a JSON object.")
            if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
                raise RequestError("invalid_request", "The request requires a string or integer id.")
            op = request.get("op")
            # WL Print and Python diagnostics must never leak into stdout.
            with contextlib.redirect_stdout(sys.stderr):
                if op == "health":
                    result = {
                        "status": "ready",
                        "engine": "Mathics3",
                        "version": self.version,
                        "session_count": len(self.sessions),
                    }
                elif op == "reset":
                    notebook_id = self._notebook_id(request)
                    self.sessions.pop(notebook_id, None)
                    self._session_for(notebook_id)
                    result = {"notebook_id": notebook_id, "line": 0, "reset": True}
                elif op == "evaluate":
                    # Mathics' parser keeps global converter state: evaluating
                    # while a background warm thread builds a spare session
                    # corrupts both. Serialize evaluation against session
                    # creation (RLock: _session_for may re-enter _new_session).
                    with self._create_lock:
                        result = self.evaluate(request)
                else:
                    raise RequestError("unknown_operation", "Supported operations are evaluate, reset and health.")
            return {"id": request_id, "ok": True, "result": result}
        except RequestError as exc:
            return {"id": request_id, "ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except (Exception, SystemExit) as exc:
            traceback.print_exc(file=sys.stderr)
            return {
                "id": request_id,
                "ok": False,
                "error": {"code": "evaluation_error", "message": f"{type(exc).__name__}: {exc}"},
            }

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        source = request.get("source")
        if not isinstance(source, str):
            raise RequestError("invalid_source", "source must be a string.")
        if not source.strip():
            raise RequestError("empty_input", "Enter an expression before evaluating.")
        if len(source) > MAX_SOURCE_LENGTH:
            raise RequestError("input_too_large", f"source exceeds {MAX_SOURCE_LENGTH} characters.")
        notebook_id = self._notebook_id(request)
        started = time.perf_counter()
        session = self._session_for(notebook_id)

        # Parse once, retaining the held AST for the numeric Manipulate subset.
        # Evaluation.evaluate is the same history/message path used by the CLI.
        plan = self._prepare_evaluation(session, source, request.get("controls"))

        def evaluate_and_render(evaluation):
            if plan.query is None:
                evaluated = self._result_type(evaluation.out, None, evaluation.definitions.get_line_no(), None, "text")
                evaluation.out = []
            else:
                evaluated = evaluation.evaluate(plan.query, format="text")
            evaluation.stopped = False
            # Preserve the actual cell input in In[n], including its control
            # declaration; Out[n] is the one evaluated body result.
            if plan.controls and evaluation.definitions.get_history_length() > 0:
                evaluation.definitions.add_rule("In", self._rule_type(self._to_expression("In", evaluated.line_no), plan.original))
                if evaluated.result is not None and evaluated.last_eval is not None:
                    # Mathics CompoundExpression can retain a Print-adjacent
                    # intermediate predetermined_out despite a later non-Null
                    # result. Interactive Out must match the actual body result.
                    stored = evaluation.get_stored_result(evaluated.last_eval, evaluation.definitions.outputforms)
                    evaluation.definitions.add_rule("Out", self._rule_type(self._to_expression("Out", evaluated.line_no), stored))
            result = self._render_result(evaluated, session)
            if result.get("algebraic_roots") and evaluation.definitions.get_history_length() > 0:
                # A Print-adjacent CompoundExpression inside Solve can leave
                # Mathics' predetermined_out pointing at an intermediate
                # value. Store the actual exact result, never the preview.
                stored = evaluation.get_stored_result(evaluated.last_eval, evaluation.definitions.outputforms)
                evaluation.definitions.add_rule("Out", self._rule_type(self._to_expression("Out", evaluated.line_no), stored))
            if plan.controls and not result["suppressed"]:
                result["interactive"] = {"controls": plan.controls}
            return result

        # Local bindings remain active through box conversion: Graphics can
        # retain unevaluated coordinates. Mathics restores user definitions in
        # a finally block even if evaluation or display conversion raises.
        if plan.bindings:
            result = self._dynamic_scoping(evaluate_and_render, plan.bindings, session.evaluation)
        else:
            result = evaluate_and_render(session.evaluation)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return result

    def _render_result(self, evaluated, session) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        prints: list[str] = []
        syntax_messages: list[str] = []
        for item in evaluated.out:
            text = str(item.text)
            if item.is_message:
                messages.append({"text": text, "kind": "warning"})
                if str(getattr(item, "symbol", "")).rsplit("`", 1)[-1] == "Syntax":
                    syntax_messages.append(text)
            else:
                prints.append(text)
        # Parser failure otherwise looks like the legitimate Null result of
        # a semicolon.  Preserve it as an error instead of claiming success.
        if syntax_messages:
            raise RequestError("syntax_error", "\n".join(syntax_messages))

        suppressed = evaluated.result is None
        result: dict[str, Any] = {
            "text": "" if suppressed else str(evaluated.result),
            "line": int(evaluated.line_no),
            "messages": messages,
            "prints": prints,
            "suppressed": suppressed,
        }
        expression = evaluated.last_eval
        if not suppressed and expression is not None:
            try:
                if expression.get_head_name() == "System`Graphics3D":
                    boxes = self._format_element(self._normalize_graphics3d(expression), session.evaluation, self._standard_form)
                    result["graphics3d"] = self._to_graphics3d(boxes, session.evaluation)
                elif expression.get_head_name() == "System`Graphics":
                    boxes = self._format_element(expression, session.evaluation, self._standard_form)
                    svg = self._box_to_format(boxes, "svg", evaluation=session.evaluation)
                    if not isinstance(svg, str) or "<svg" not in svg:
                        raise ValueError("Mathics did not produce an SVG document.")
                    result["svg"] = svg
                else:
                    latex = session.evaluation.format_output(expression, "latex")
                    if isinstance(latex, str) and latex.strip():
                        result["latex"] = latex
                    preview = self._solution_preview(expression, session.evaluation)
                    if preview is not None:
                        result["algebraic_roots"] = preview
            except RequestError:
                raise
            except Exception as exc:
                if expression.get_head_name() == "System`Graphics3D":
                    raise RequestError("unsupported_graphics3d", f"Mathics could not create usable 3D boxes: {exc}") from exc
                # Evaluation succeeded; optional display conversion did not.
                # Keep its real text result and disclose the display fallback.
                messages.append({"text": f"Display conversion failed: {exc}", "kind": "display"})
        return result


def write_event(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        kernel = Kernel()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    write_event({"event": "ready", "engine": "Mathics3", "version": kernel.version, "protocol": 1})
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            write_event({"id": None, "ok": False, "error": {"code": "invalid_json", "message": str(exc)}})
            continue
        write_event(kernel.dispatch(request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
