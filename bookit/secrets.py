"""Where API keys come from.

One lookup order for every service, so the app and the CLI scripts behave the
same way:

1. an explicit argument, for tests
2. the environment
3. ``.streamlit/secrets.toml``

The file is read directly rather than through ``st.secrets`` so the CLI scripts
find it too — ``st.secrets`` needs a Streamlit runtime and resolves relative to
the current working directory, neither of which holds for `python scripts/…`.
"""

from __future__ import annotations

import os
from pathlib import Path

try:                      # 3.11+
    import tomllib
except ModuleNotFoundError:   # 3.10 and older
    import tomli as tomllib

SECRETS_PATH = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"


class MissingKey(RuntimeError):
    """No credential for a service that needs one."""


def _from_file(name: str) -> str | None:
    try:
        with open(SECRETS_PATH, "rb") as fh:
            value = tomllib.load(fh).get(name)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return str(value) if value else None


def read_secret(name: str, explicit: str | None = None) -> str | None:
    """The value, or None. Order: explicit, environment, secrets.toml."""
    if explicit:
        return explicit
    if value := os.environ.get(name):
        return value
    return _from_file(name)


def require_secret(name: str, explicit: str | None = None, *, hint: str = "") -> str:
    """The value, or a message telling the reader exactly where to put it."""
    if value := read_secret(name, explicit):
        return value
    raise MissingKey(
        f"No {name}. Add it to {SECRETS_PATH} as `{name} = \"…\"`, "
        f"or set it in the environment.{(' ' + hint) if hint else ''}"
    )
