from dream.tools import tool


@tool(risk="safe")
def hello_tool(name: str) -> str:
    """Return a deterministic greeting."""
    return f"hello {name}"
