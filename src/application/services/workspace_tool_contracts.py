"""Share strict workspace argument models and finite tool schemas between HTTP and server dispatch."""

import logging
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class DirectoryInput(BaseModel):
    """Accept only an optional relative directory without caller roots or ownership overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    directory: str | None = Field(default=None, max_length=4096)


class SearchInput(DirectoryInput):
    """Accept a bounded exact literal search without regex execution or caller budgets."""

    query: str = Field(min_length=1, max_length=256)


class ReadInput(BaseModel):
    """Accept one relative path and a bounded one-indexed source-line range."""

    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=4096)
    start_line: int = Field(default=1, ge=1, le=2147483647)
    end_line: int = Field(default=200, ge=1, le=2147483647)


class EmptyInput(BaseModel):
    """Accept discovery without any model-selected scope or extra argument."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ToolEnvelope(BaseModel):
    """Accept exactly a registered tool name and its object arguments."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict


TOOL_REGISTRY = MappingProxyType(
    {
        "workspace.discover": ("discover", EmptyInput),
        "workspace.inventory": ("inventory", DirectoryInput),
        "workspace.read": ("read", ReadInput),
        "workspace.search": ("search", SearchInput),
        "workspace.symbols": ("symbols", DirectoryInput),
    }
)


def workspace_tool_schemas():
    """Return fresh schema objects from the exact finite runtime argument models."""
    schemas = [
        dict(name=name, parameters=model.model_json_schema())
        for name, (_, model) in TOOL_REGISTRY.items()
    ]
    logger.info("workspace_tool_schemas_published count=%d", len(schemas))
    return schemas
