from .core import Element, Page


def add_page(route: str, page: type[Page]) -> None:
    from . import core

    core.pages["/" + route.removeprefix("/")] = page


__all__ = ["Element", "Page", "add_page"]
