"""Package constants, in a leaf module so services and the client can both
import them without a cycle."""

from __future__ import annotations

import urllib.parse

__all__ = [
    "VERSION",
    "DEFAULT_BASE_URL",
    "DEFAULT_PROFILE",
    "profile_or_default",
]

# VERSION is the client version, reported in the User-Agent header.
# It is the single source of truth for the package version: pyproject.toml
# reads it via [tool.setuptools.dynamic], so bump it in one place only.
VERSION = "0.3.0"

# DEFAULT_BASE_URL is the hosted JustRouting API endpoint.
DEFAULT_BASE_URL = "https://api.justrouting.tech"

# DEFAULT_PROFILE is the routing profile used when a request leaves
# Profile empty.
DEFAULT_PROFILE = "driving"


def profile_or_default(profile: str) -> str:
    """The profile to use in a request path, with URL path escaping."""
    if not profile:
        return DEFAULT_PROFILE
    return urllib.parse.quote(profile, safe="")
