from typing import Dict, Any, List
from .browser_session import get_browser_session

def browser_navigate(url: str) -> Dict[str, Any]:
    session = get_browser_session()
    response = session.page.goto(url, wait_until="domcontentloaded")
    status_code = response.status if response else 200
    title = session.page.title()
    screenshot_path = session.screenshot(prefix="nav")
    return {
        "url": session.page.url,
        "title": title,
        "status_code": status_code,
        "screenshot": screenshot_path
    }

def browser_click(selector: str) -> Dict[str, Any]:
    session = get_browser_session()
    session.page.click(selector)
    session.page.wait_for_timeout(500) # Wait for DOM to stabilize
    screenshot_path = session.screenshot(prefix="click")
    return {
        "clicked_selector": selector,
        "current_url": session.page.url,
        "screenshot": screenshot_path
    }

def browser_fill(selector: str, value: str) -> Dict[str, Any]:
    session = get_browser_session()
    session.page.fill(selector, value)
    return {
        "filled_selector": selector,
        "value": value
    }

def browser_select(selector: str, value: str) -> Dict[str, Any]:
    session = get_browser_session()
    session.page.select_option(selector, value)
    return {
        "selected_selector": selector,
        "value": value
    }

def browser_screenshot(name: str = "snapshot") -> str:
    session = get_browser_session()
    return session.screenshot(prefix=name)

def browser_get_page_text() -> str:
    session = get_browser_session()
    return session.page.inner_text("body")

def browser_get_page_snapshot() -> Dict[str, Any]:
    """
    Extracts an accessible, structured DOM snapshot of interactive elements on the page.
    This enables the LLM agent to inspect form fields, buttons, links, tables, and notices
    even when UI layouts or labels have been perturbed.
    """
    session = get_browser_session()
    page = session.page

    # Execute client-side inspection script
    snapshot = page.evaluate("""() => {
        const elements = [];
        const interactiveNodes = document.querySelectorAll('input, select, textarea, button, a, form, table');
        
        interactiveNodes.forEach(el => {
            const rect = el.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
            if (!isVisible && el.tagName.toLowerCase() !== 'form') return;

            const item = {
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                name: el.getAttribute('name') || null,
                type: el.getAttribute('type') || null,
                text: (el.innerText || el.textContent || '').trim().substring(0, 100),
                value: el.value || null,
                placeholder: el.getAttribute('placeholder') || null,
                href: el.getAttribute('href') || null,
                role: el.getAttribute('role') || null,
                checked: el.checked || false,
                required: el.required || false
            };
            elements.push(item);
        });

        // Extract alerts/notices
        const alerts = [];
        document.querySelectorAll('.alert, .dev-badge, [role="alert"]').forEach(el => {
            alerts.push(el.innerText.trim());
        });

        return {
            url: window.location.href,
            title: document.title,
            alerts: alerts,
            elements: elements
        };
    }""")
    return snapshot
