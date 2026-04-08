"""Env-var fail-fast check.

Pure function taking an env dict (not os.environ directly) so tests can drive
it without mutating real process state.
"""

from collections.abc import Mapping


class MissingEnvVars(RuntimeError):
    """Raised when required env vars are absent or empty."""


def require_env_vars(env: Mapping[str, str], required: list[str]) -> None:
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise MissingEnvVars(
            f"missing required environment variables: {', '.join(missing)}. "
            f"Set them in .env before running dd-research."
        )
