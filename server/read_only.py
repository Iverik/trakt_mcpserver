"""A FastMCP that registers only read-only tools, judged by their annotations."""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import AnyFunction, Icon, ToolAnnotations


class ReadOnlyFastMCP(FastMCP):
    """FastMCP that skips every tool whose annotations do not say read-only.

    The decision reads the annotation each tool already carries, so a new tool
    is covered without touching a list here. A tool with no annotations counts
    as not read-only.
    """

    skipped_tools: list[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.skipped_tools = []

    def add_tool(
        self,
        fn: AnyFunction,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        icons: list[Icon] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> None:
        if annotations is None or annotations.readOnlyHint is not True:
            self.skipped_tools.append(name or fn.__name__)
            return
        super().add_tool(
            fn,
            name=name,
            title=title,
            description=description,
            annotations=annotations,
            icons=icons,
            meta=meta,
            structured_output=structured_output,
        )
