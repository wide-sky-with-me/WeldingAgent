"""pWPS Agent core package."""

from __future__ import annotations

import warnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning


warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version\.",
    category=LangChainPendingDeprecationWarning,
)

__all__ = ["__version__"]

__version__ = "0.1.0"
