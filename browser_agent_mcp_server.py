#!/usr/bin/env python3
"""Browser Agent MCP Server - Execute browser tasks using OpenAI's CUA model."""

import os
import base64
import asyncio
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
import httpx

# Load .env from same directory as this script
load_dotenv(Path(__file__).parent / ".env")
from playwright.async_api import async_playwright, Browser, Page
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("browser-agent")

# Key mapping for CUA
CUA_KEY_TO_PLAYWRIGHT_KEY = {
    "enter": "Enter", "tab": "Tab", "space": " ", "backspace": "Backspace",
    "delete": "Delete", "esc": "Escape", "arrowup": "ArrowUp", "arrowdown": "ArrowDown",
    "arrowleft": "ArrowLeft", "arrowright": "ArrowRight", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown", "shift": "Shift", "ctrl": "Control",
    "alt": "Alt", "cmd": "Meta", "win": "Meta", "super": "Meta", "option": "Alt",
}


async def create_response(**kwargs):
    """Call OpenAI's Responses API."""
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers=headers, json=kwargs)
        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.status_code} {response.text}")
        return response.json()


class AsyncPlaywrightBrowser:
    """Async Playwright browser wrapper for CUA."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self.width = 1024
        self.height = 768

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        launch_args = [
            f"--window-size={self.width},{self.height}",
            "--disable-extensions",
        ]
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
        )
        context = await self._browser.new_context()
        context.on("page", self._handle_new_page)
        self._page = await context.new_page()
        await self._page.set_viewport_size({"width": self.width, "height": self.height})
        self._page.on("close", self._handle_page_close)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    def _handle_new_page(self, page: Page):
        self._page = page
        page.on("close", self._handle_page_close)

    def _handle_page_close(self, page: Page):
        if self._page == page and self._browser.contexts[0].pages:
            self._page = self._browser.contexts[0].pages[-1]

    def get_dimensions(self):
        return (self.width, self.height)

    def get_current_url(self) -> str:
        return self._page.url

    async def screenshot(self) -> str:
        png_bytes = await self._page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("utf-8")

    async def click(self, x: int, y: int, button: str = "left"):
        if button == "back":
            await self._page.go_back()
        elif button == "forward":
            await self._page.go_forward()
        elif button == "wheel":
            await self._page.mouse.wheel(x, y)
        else:
            await self._page.mouse.click(x, y, button=button if button in ["left", "right"] else "left")

    async def double_click(self, x: int, y: int):
        await self._page.mouse.dblclick(x, y)

    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        await self._page.mouse.move(x, y)
        await self._page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")

    async def type(self, text: str):
        await self._page.keyboard.type(text)

    async def wait(self, ms: int = 1000):
        await asyncio.sleep(ms / 1000)

    async def move(self, x: int, y: int):
        await self._page.mouse.move(x, y)

    async def keypress(self, keys: List[str]):
        mapped = [CUA_KEY_TO_PLAYWRIGHT_KEY.get(k.lower(), k) for k in keys]
        for key in mapped:
            await self._page.keyboard.down(key)
        for key in reversed(mapped):
            await self._page.keyboard.up(key)

    async def drag(self, path: List[Dict[str, int]]):
        if not path:
            return
        await self._page.mouse.move(path[0]["x"], path[0]["y"])
        await self._page.mouse.down()
        for point in path[1:]:
            await self._page.mouse.move(point["x"], point["y"])
        await self._page.mouse.up()

    async def goto(self, url: str):
        await self._page.goto(url)


async def run_browser_task(task: str, start_url: str = "https://google.com", headless: bool = False, max_steps: int = 50) -> str:
    """Run a browser task using OpenAI's CUA model."""
    log = []

    async with AsyncPlaywrightBrowser(headless=headless) as browser:
        await browser.goto(start_url)
        log.append(f"Navigated to {start_url}")

        dimensions = browser.get_dimensions()
        tools = [{
            "type": "computer-preview",
            "display_width": dimensions[0],
            "display_height": dimensions[1],
            "environment": "browser",
        }]

        items = [{"role": "user", "content": task}]
        step = 0

        while step < max_steps:
            step += 1
            response = await create_response(
                model="computer-use-preview",
                input=items,
                tools=tools,
                truncation="auto",
            )

            if "output" not in response:
                log.append(f"Error: No output from model - {response}")
                break

            items += response["output"]

            for item in response["output"]:
                if item["type"] == "message":
                    text = item["content"][0]["text"]
                    log.append(f"Agent: {text}")

                elif item["type"] == "computer_call":
                    action = item["action"]
                    action_type = action["type"]
                    action_args = {k: v for k, v in action.items() if k != "type"}
                    log.append(f"Action: {action_type}({action_args})")

                    # Execute the action
                    method = getattr(browser, action_type)
                    await method(**action_args)

                    # Get screenshot and add to items
                    screenshot_base64 = await browser.screenshot()
                    call_output = {
                        "type": "computer_call_output",
                        "call_id": item["call_id"],
                        "acknowledged_safety_checks": item.get("pending_safety_checks", []),
                        "output": {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_base64}",
                            "current_url": browser.get_current_url(),
                        },
                    }
                    items.append(call_output)

            # Check if we got a final assistant message
            if items[-1].get("role") == "assistant":
                break

        final_url = browser.get_current_url()
        log.append(f"Final URL: {final_url}")

    return "\n".join(log)


@mcp.tool()
async def browser_task(task: str, start_url: str = "https://google.com") -> str:
    """Execute a browser task using AI.

    The AI agent will control a browser to complete the task.
    For purchases, it will stop at payment entry for you to complete manually.

    Args:
        task: Description of what to do (e.g., "Search for X and add to cart")
        start_url: URL to start browsing from (default: google.com)
    """
    if not os.getenv("OPENAI_API_KEY"):
        return "Error: OPENAI_API_KEY environment variable not set"

    return await run_browser_task(task, start_url, headless=False)


@mcp.tool()
async def browser_task_headless(task: str, start_url: str = "https://google.com") -> str:
    """Execute a browser task using AI in headless mode (no visible browser).

    Same as browser_task but runs without showing the browser window.
    Useful for simple data gathering tasks.

    Args:
        task: Description of what to do
        start_url: URL to start browsing from (default: google.com)
    """
    if not os.getenv("OPENAI_API_KEY"):
        return "Error: OPENAI_API_KEY environment variable not set"

    return await run_browser_task(task, start_url, headless=True)


if __name__ == "__main__":
    mcp.run()
