from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st


def _missing_script_run_ctx(*, suppress_warning: bool = False) -> None:
    del suppress_warning
    return None


_get_script_run_ctx: Callable[..., object | None]
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_script_run_ctx
except ImportError:
    _get_script_run_ctx = _missing_script_run_ctx


UI_DIR = Path(__file__).resolve().parent


def _resolve_css_path(path: str | Path) -> Path:
    css_path = Path(path)
    if css_path.is_absolute():
        return css_path

    module_relative_path = (UI_DIR / css_path).resolve()
    if module_relative_path.exists():
        return module_relative_path

    return (Path.cwd() / css_path).resolve()


def _current_run_token() -> str | None:
    ctx = _get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return None

    session_id = getattr(ctx, "session_id", None)
    page_script_hash = getattr(ctx, "page_script_hash", None)
    cursors = getattr(ctx, "cursors", None)
    if session_id is None or page_script_hash is None or cursors is None:
        return None

    # `ctx.cursors` is recreated for each rerun, which lets us preserve the
    # "no duplicate injection in one run" behavior without breaking styling on
    # refresh or widget-triggered reruns.
    return f"{session_id}:{page_script_hash}:{id(cursors)}"


def load_css(path: str | Path = "styles.css") -> None:
    css_path = _resolve_css_path(path)
    if not css_path.exists():
        raise FileNotFoundError(f"CSS file not found: {css_path}")

    state_key = f"_results_viewer_css_loaded::{css_path}"
    run_token = _current_run_token()
    if run_token is not None and st.session_state.get(state_key) == run_token:
        return

    # `st.html()` is Streamlit's supported path for injecting a local CSS file.
    # When given a CSS path, Streamlit wraps the file in <style> tags for us.
    st.html(css_path)
    if run_token is not None:
        st.session_state[state_key] = run_token
