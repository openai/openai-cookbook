from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx


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
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return None

    # `ctx.cursors` is recreated for each rerun, which lets us preserve the
    # "no duplicate injection in one run" behavior without breaking styling on
    # refresh or widget-triggered reruns.
    return f"{ctx.session_id}:{ctx.page_script_hash}:{id(ctx.cursors)}"


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
