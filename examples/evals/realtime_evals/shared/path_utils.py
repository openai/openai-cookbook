"""Path validation utilities for realtime eval harnesses."""

from pathlib import Path


class InvalidPathComponentError(ValueError):
    """Raised when a path component contains traversal sequences or is otherwise unsafe."""


def validate_safe_path_component(name: str, component_name: str = "path component") -> str:
    """
    Validate that a path component is safe to use in filesystem operations.

    Args:
        name: The path component to validate (e.g., example_id, simulation_id).
        component_name: Human-readable name for error messages.

    Returns:
        The validated name (stripped of whitespace).

    Raises:
        InvalidPathComponentError: If the component is empty, contains traversal
            sequences, path separators, or other unsafe characters.
    """
    if name is None:
        raise InvalidPathComponentError(f"{component_name} cannot be None")

    stripped = name.strip()
    if not stripped:
        raise InvalidPathComponentError(f"{component_name} cannot be empty or whitespace")

    # Check for path traversal and separator characters
    unsafe_patterns = ("..", "/", "\\", ":")
    for pattern in unsafe_patterns:
        if pattern in stripped:
            raise InvalidPathComponentError(
                f"{component_name} contains unsafe pattern '{pattern}': {stripped!r}"
            )

    # Reject absolute paths (Windows drive letters, Unix root)
    if stripped.startswith("/") or (len(stripped) >= 2 and stripped[1] == ":"):
        raise InvalidPathComponentError(
            f"{component_name} cannot be an absolute path: {stripped!r}"
        )

    # Reject reserved names on Windows
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    if stripped.upper() in reserved_names:
        raise InvalidPathComponentError(
            f"{component_name} uses reserved name: {stripped!r}"
        )

    return stripped


def resolve_safe_path(path_value: str, base: Path, component_name: str = "path") -> Path:
    """
    Resolve a path value from harness data files, confining relative paths to base.

    Relative paths (what the repo's own datasets use) are resolved against base
    and must stay within it, which blocks ``../`` traversal. Absolute paths are
    resolved and used as-is: the harnesses have always treated explicitly
    authored absolute paths as trusted, and existing simulation bundles rely on
    that behavior.

    Args:
        path_value: The path string from a dataset CSV or simulation JSON.
        base: The directory relative paths resolve against.
        component_name: Human-readable name for error messages.

    Returns:
        The resolved absolute Path.

    Raises:
        InvalidPathComponentError: If the value is empty, or if a relative
            path resolves outside base.
    """
    if not path_value or not path_value.strip():
        raise InvalidPathComponentError(f"{component_name} cannot be empty")

    stripped = path_value.strip()
    path_obj = Path(stripped)

    # Treat rooted paths as absolute on every platform so behavior does not
    # depend on whether the host OS reports them as absolute.
    if path_obj.is_absolute() or stripped.startswith("/"):
        return path_obj.resolve()

    try:
        resolved = (base / path_obj).resolve()
        resolved.relative_to(base.resolve())
    except ValueError:
        raise InvalidPathComponentError(
            f"{component_name} escapes base directory: {path_value!r}"
        )

    return resolved