from hyprtxt import Element, Page, add_page
from hyprtxt.core import run_app
from hyprtxt.pages import _DEFAULT_STATIC_PROVIDER


class CounterPage(Page):
    async def setup_page(self):
        self.count = 0

        await self.add_child(
            Element(
                "div",
                Element("h1", "count: ", Element("span", str(self.count), id="count")),
                Element("button", "click me", id="btn"),
            )
        )

        await self.hook("btn", "onclick", self.increment)

    async def increment(self, id: str, action: str):
        self.count += 1
        await self.set_text("count", str(self.count))


add_page("/", CounterPage)
run_app([_DEFAULT_STATIC_PROVIDER])
