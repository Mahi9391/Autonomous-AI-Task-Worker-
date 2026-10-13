import os
import uuid
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

class BrowserSession:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.traces_dir = Path(__file__).resolve().parent.parent.parent / "data" / "traces"
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        if self._playwright is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                accept_downloads=True
            )
            self._page = self._context.new_page()
            # Set default timeout to 10 seconds
            self._page.set_default_timeout(10000)

    @property
    def page(self) -> Page:
        if self._page is None:
            self.start()
        return self._page

    def screenshot(self, prefix: str = "shot") -> str:
        filename = f"{prefix}_{uuid.uuid4().hex[:6]}.png"
        filepath = self.traces_dir / filename
        self.page.screenshot(path=str(filepath), full_page=True)
        return str(filepath)

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._context = None
            self._browser = None
            self._playwright = None
            self._page = None

# Global or task-scoped session provider
_default_session: Optional[BrowserSession] = None

def get_browser_session(headless: bool = True) -> BrowserSession:
    global _default_session
    if _default_session is None or _default_session._page is None:
        _default_session = BrowserSession(headless=headless)
        _default_session.start()
    return _default_session

def close_browser_session():
    global _default_session
    if _default_session:
        _default_session.close()
        _default_session = None
