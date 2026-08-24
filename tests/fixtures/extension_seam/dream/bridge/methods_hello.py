"""Synthetic extension used only by the P0 seam contract test."""


def hello(name: str = "world") -> dict[str, str]:
    return {"message": f"hello {name}"}


HANDLERS = {"hello.greet": hello}
