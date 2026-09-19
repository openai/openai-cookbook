"""Path validation utilities for realtime eval harnesses."""

from pathlib import Path


class InvalidPathComponentError(ValueError):
    """Raised when a path component contains traversal sequences or is otherwise unsafe."""
    pass


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


def validate_safe_relative_path(path: str, base: Path, component_name: str = "path") -> Path:
    """
    Validate that a relative path resolves within the base directory.

    Args:
        path: The relative path string to validate.
        base: The base directory that the path must resolve within.
        component_name: Human-readable name for error messages.

    Returns:
        The resolved absolute Path within base.

    Raises:
        InvalidPathComponentError: If the path is absolute, contains traversal
            that escapes base, or is otherwise unsafe.
    """
    if not path or not path.strip():
        raise InvalidPathComponentError(f"{component_name} cannot be empty")

    stripped = path.strip()

    # Explicitly reject Unix-style absolute paths (starting with /) on all platforms
    # since Path.is_absolute() may not detect them on Windows
    if stripped.startswith("/"):
        raise InvalidPathComponentError(f"{component_name} must be relative, not absolute: {path!r}")

    path_obj = Path(stripped)

    if path_obj.is_absolute():
        raise InvalidPathComponentError(f"{component_name} must be relative, not absolute: {path!r}")

    # Resolve relative to base and ensure it stays within base
    try:
        resolved = (base / path_obj).resolve()
        base_resolved = base.resolve()
        resolved.relative_to(base_resolved)
    except ValueError:
        raise InvalidPathComponentError(
            f"{component_name} escapes base directory: {path!r}"
        )

    return resolved