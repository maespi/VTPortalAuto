"""Playwright automation client for VisualTime Portal."""

import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from vtportal.config import PortalConfig, logger

MONTH_NAMES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

MONTH_ALIASES: dict[int, list[str]] = {
    1: ["enero", "january", "ene", "jan"],
    2: ["febrero", "february", "feb"],
    3: ["marzo", "march", "mar"],
    4: ["abril", "april", "abr", "apr"],
    5: ["mayo", "may"],
    6: ["junio", "june", "jun"],
    7: ["julio", "july", "jul"],
    8: ["agosto", "august", "ago", "aug"],
    9: ["septiembre", "september", "sep", "sept"],
    10: ["octubre", "october", "oct"],
    11: ["noviembre", "november", "nov"],
    12: ["diciembre", "december", "dic", "dec"],
}

MONTH_NUMS: dict[str, int] = {}
for m_num, aliases in MONTH_ALIASES.items():
    for alias in aliases:
        MONTH_NUMS[alias] = m_num


def parse_target_date(date_val: str | datetime | None = None) -> datetime:
    """Parse a date string or return datetime.now().
    
    Supports:
        - None, '', 'today' -> datetime.now()
        - 'yesterday' -> datetime.now() - 1 day
        - 'YYYY-MM-DD'
        - 'DD/MM/YYYY'
        - 'YYYY/MM/DD'
    """
    if date_val is None:
        return datetime.now()

    if isinstance(date_val, datetime):
        return date_val

    raw = str(date_val).strip().lower()
    if not raw or raw == "today" or raw == "hoy":
        return datetime.now()
    if raw == "yesterday" or raw == "ayer":
        return datetime.now() - timedelta(days=1)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw)
    except Exception as e:
        raise ValueError(f"Could not parse date '{date_val}'. Expected YYYY-MM-DD or DD/MM/YYYY.") from e


def get_time_range(target_date: datetime | None = None) -> tuple[str, str]:
    """Determine enter/exit time range based on the target date.

    Rules:
        - Summer (June 16 to August 31): 08:00 to 15:00
        - Rest of year (from Sept 1): 08:30 to 18:00
        - Fridays: Exit is always 15:00
    """
    target_date = target_date or datetime.now()
    month = target_date.month
    day = target_date.day

    if (month == 6 and day >= 16) or (7 <= month <= 8):
        enter_time, exit_time = "08:00", "15:00"
    else:
        enter_time, exit_time = "08:30", "18:00"

    if target_date.weekday() == 4:  # Friday
        exit_time = "15:00"

    return enter_time, exit_time


def get_default_work_mode(target_date: datetime | None = None) -> str:
    """Determine default work mode based on day of week.
    
    Rules:
        - Wednesday (weekday 2): 'Presencial'
        - Other days: 'Teletrabajo'
    """
    target_date = target_date or datetime.now()
    if target_date.weekday() == 2:
        return "Presencial"
    return "Teletrabajo"


def add_time_jitter(time_str: str, max_minutes: int = 0) -> str:
    """Add a random variation of [-max_minutes, +max_minutes] to time_str (HH:MM)."""
    if not max_minutes or max_minutes <= 0:
        return time_str
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return time_str
        hours, minutes = int(parts[0]), int(parts[1])
        delta = random.randint(-max_minutes, max_minutes)
        total_minutes = hours * 60 + minutes + delta
        # Clamp to 00:00 - 23:59
        total_minutes = max(0, min(1439, total_minutes))
        new_hours = total_minutes // 60
        new_minutes = total_minutes % 60
        return f"{new_hours:02d}:{new_minutes:02d}"
    except Exception:
        return time_str


class VTPortalClient:
    """Manages browser sessions and automation tasks on VTPortal."""

    def __init__(self, config: PortalConfig | None = None):
        self.config = config or PortalConfig.from_env()
        self.session_file = Path(self.config.session_file)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._main_page: Page | None = None
        self._popup: Page | None = None

    async def close(self) -> None:
        """Close active popup, context, browser, and playwright instance."""
        if self._popup and not self._popup.is_closed():
            try:
                await self._popup.close()
            except Exception:
                pass
        self._popup = None

        if self._main_page and not self._main_page.is_closed():
            try:
                await self._main_page.close()
            except Exception:
                pass
        self._main_page = None

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = None

    async def __aenter__(self) -> "VTPortalClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    async def _init_browser_and_popup(self) -> None:
        """Initialize playwright, launch chromium, load session storage if exists, and open popup."""
        logger.info("Initializing Playwright browser and portal session...")
        if self._popup and not self._popup.is_closed():
            try:
                await self._popup.close()
            except Exception:
                pass
            self._popup = None

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser and not self._browser.is_connected():
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if not self._playwright:
            self._playwright = await async_playwright().start()

        if not self._browser:
            self._browser = await self._playwright.chromium.launch(headless=self.config.headless)

        storage_state = str(self.session_file) if self.session_file.is_file() else None
        if storage_state:
            logger.info("Loading cached session from %s", storage_state)
            try:
                self._context = await self._browser.new_context(
                    storage_state=storage_state,
                    locale="es-ES",
                )
            except Exception as e:
                logger.warning("Could not load storage_state (%s), creating clean context", e)
                self._context = await self._browser.new_context(locale="es-ES")
        else:
            self._context = await self._browser.new_context(locale="es-ES")

        self._main_page = await self._context.new_page()
        await self._main_page.goto("https://vtportal.visualtime.net/", wait_until="networkidle")

        bt_open = self._main_page.locator("#btOpen")
        if await bt_open.count() > 0 and await bt_open.first.is_visible():
            async with self._main_page.expect_popup() as popup_info:
                await bt_open.first.click()
            self._popup = await popup_info.value
        else:
            self._popup = self._main_page

        await self._popup.wait_for_load_state("networkidle")
        await self._popup.wait_for_timeout(1000)

    async def _ensure_active_session(self) -> Page:
        """Ensure Playwright, Browser, Context, and Popup are open, connected, and authenticated."""
        needs_init = False
        if not self._playwright or not self._browser or not self._context:
            needs_init = True
        elif not self._browser.is_connected():
            needs_init = True
        elif not self._popup or self._popup.is_closed():
            needs_init = True

        if needs_init:
            await self._init_browser_and_popup()

        assert self._popup is not None
        await self._ensure_logged_in(self._popup)
        return self._popup

    async def _check_and_handle_forced_logout(self, popup: Page) -> bool:
        """Check if session expired or forced out by another system, and re-login if needed."""
        try:
            # Check for session expired dialog or alert
            dismissed_dialog = await popup.evaluate(
                """() => {
                    const dialogs = Array.from(document.querySelectorAll('.dx-dialog, .dx-overlay-content'));
                    for (const d of dialogs) {
                        const txt = (d.textContent || '').toLowerCase();
                        if (txt.includes('sesi') || txt.includes('expir') || txt.includes('caduc') || txt.includes('dispositivo')) {
                            const btn = d.querySelector('.dx-button, [role="button"], button');
                            if (btn) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }"""
            )
            if dismissed_dialog:
                logger.warning("Session expired dialog detected and dismissed")
                await popup.wait_for_timeout(1000)

            # Check if login form inputs are visible
            pwd_field = popup.locator("#accessPwd, [data-testid='login-client-field']")
            if await pwd_field.count() > 0 and await pwd_field.first.is_visible():
                logger.warning("Forced logout or unauthenticated state detected! Re-authenticating...")
                await self._login(popup)
                return True
        except Exception as e:
            logger.debug("Error while checking for forced logout: %s", e)

        return False

    async def _ensure_logged_in(self, popup: Page) -> None:
        """Ensure that the popup is authenticated, logging in if needed."""
        await popup.wait_for_load_state("networkidle")
        await popup.wait_for_timeout(800)

        # First handle any forced logout / session expired alert
        if await self._check_and_handle_forced_logout(popup):
            return

        is_logged_in = await popup.evaluate(
            """() => {
                const hasMenu = !!document.querySelector('.dx-menu-hamburger-button, .dx-icon-menu, #btnActionMenuPopover');
                const hasApp = typeof window.VTPortal !== 'undefined' && window.VTPortal.app;
                const hasLoginField = !!document.querySelector('#accessPwd, [data-testid="login-client-field"]');
                return (hasMenu || hasApp) && !hasLoginField;
            }"""
        )

        if is_logged_in:
            logger.debug("Session is active and already logged in (using cached session)")
            return

        logger.info("Session not active or login form present. Performing login...")
        await self._login(popup)

    async def _set_dx_textbox(self, page: Page, selector: str, value: str, widget_name: str = "dxTextBox") -> dict[str, Any]:
        """Directly set DevExpress text widget value and trigger events."""
        return await page.evaluate(
            """([selector, widgetName, value]) => {
                const el = document.querySelector(selector);
                if (!el) return {success: false, error: 'selector not found'};
                if (typeof window.jQuery === 'undefined') {
                    return {success: false, error: 'jQuery unavailable'};
                }
                try {
                    const $el = jQuery(el);
                    if (typeof $el[widgetName] !== 'function') {
                        return {success: false, error: `widget ${widgetName} missing`};
                    }
                    const instance = $el[widgetName]('instance');
                    if (instance) {
                        if (instance.option('disabled') !== false) {
                            instance.option('disabled', false);
                        }
                        if (instance.option('readOnly') !== false) {
                            instance.option('readOnly', false);
                        }
                        instance.option('value', value);
                    }
                    const input = el.querySelector('input');
                    if (input) {
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    return {success: true};
                } catch (error) {
                    return {success: false, error: String(error)};
                }
            }""",
            [selector, widget_name, value],
        )

    async def _set_dx_selectbox(self, page: Page, selector: str, value: str) -> dict[str, Any]:
        """Directly set DevExpress selectbox widget value."""
        return await page.evaluate(
            """([selector, value]) => {
                const el = document.querySelector(selector);
                if (!el) return {success: false, error: 'selector not found'};
                if (typeof window.jQuery === 'undefined') {
                    return {success: false, error: 'jQuery unavailable'};
                }
                try {
                    const $el = jQuery(el);
                    if (typeof $el.dxSelectBox !== 'function') {
                        return {success: false, error: 'dxSelectBox missing'};
                    }
                    const instance = $el.dxSelectBox('instance');
                    if (!instance) {
                        return {success: false, error: 'selectbox instance missing'};
                    }
                    instance.option('value', value);
                    const input = el.querySelector('input[type=hidden]');
                    if (input) {
                        input.value = value;
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    return {success: true};
                } catch (error) {
                    return {success: false, error: String(error)};
                }
            }""",
            [selector, value],
        )

    async def _select_dx_dropdown_option_by_label(self, popup: Page, field_label: str, option_text: str) -> bool:
        """Open a DX select box by field label and choose an option by visible text."""
        logger.debug("Selecting dropdown option for '%s' -> '%s'", field_label, option_text)
        await popup.wait_for_timeout(300)
        try:
            field = popup.locator(f'div.dx-field:has(span:has-text("{field_label}"))')
            if await field.count() == 0:
                logger.warning("No field found for label: %s", field_label)
                return False

            select_box = field.locator("div.dx-selectbox, div.dx-dropdowneditor")
            if await select_box.count() == 0:
                logger.warning("No selectbox found for field label: %s", field_label)
                return False

            await select_box.first.click()
            await popup.wait_for_timeout(400)

            # Fallback to JS selection on the visible overlay list
            clicked = await popup.evaluate(
                """([optionText]) => {
                    const options = Array.from(document.querySelectorAll('div.dx-list-item, div[role="option"], div.dx-item-content'));
                    const target = options.find(opt => opt.textContent && opt.textContent.trim().toLowerCase().includes(optionText.toLowerCase()));
                    if (target) {
                        target.click();
                        return true;
                    }
                    return false;
                }""",
                [option_text],
            )
            if clicked:
                await popup.wait_for_timeout(400)
                return True

            logger.warning("No dropdown option found with text: %s", option_text)
            return False
        except Exception as e:
            logger.error("Error selecting dropdown option for %s: %s", field_label, e)
            return False

    async def _set_datetime_picker_time(self, popup: Page, time_value: str) -> bool:
        """Set hours and minutes in the 'Fecha y hora' datetime picker."""
        logger.debug("Setting datetime picker time to %s", time_value)
        try:
            parts = time_value.split(":")
            if len(parts) != 2:
                logger.error("Invalid time format: %s", time_value)
                return False

            hour_int = int(parts[0])
            minute_int = int(parts[1])
            hour_str = parts[0].zfill(2)
            minute_str = parts[1].zfill(2)

            await popup.wait_for_timeout(300)

            # 1. First attempt: direct DevExtreme dxDateBox widget instance update
            direct_success = await popup.evaluate(
                """([hours, minutes]) => {
                    try {
                        const $box = $('.dx-datebox-datetime');
                        if ($box.length) {
                            const inst = $box.dxDateBox('instance');
                            if (inst) {
                                let dt = inst.option('value');
                                dt = dt ? new Date(dt) : new Date();
                                dt.setHours(hours, minutes, 0, 0);
                                inst.option('value', dt);
                                if (typeof inst.close === 'function') {
                                    inst.close();
                                }
                                return true;
                            }
                        }
                        return false;
                    } catch (e) {
                        return false;
                    }
                }""",
                [hour_int, minute_int],
            )
            if direct_success:
                await popup.wait_for_timeout(400)
                await popup.evaluate("""() => {
                    try {
                        const $box = $('.dx-datebox-datetime');
                        if ($box.length && $box.dxDateBox('instance')) {
                            $box.dxDateBox('instance').close();
                        }
                    } catch (e) {}
                    $('.dx-overlay-wrapper.dx-datebox-wrapper').hide();
                }""")
                return True

            # 2. Fallback: open datetime picker and select via UI rollers
            fecha_field = popup.locator("div.dx-datebox-datetime div.dx-dropdowneditor-button")
            if await fecha_field.count() == 0:
                logger.error("Could not find datetime picker button")
                return False

            await fecha_field.first.click()
            await popup.wait_for_timeout(500)

            # Select hour
            hour_success = await popup.evaluate(
                """([hourStr]) => {
                    const hourItems = document.querySelectorAll('div.dx-dateviewroller-hours div.dx-dateview-item');
                    const target = Array.from(hourItems).find(item => item.textContent.trim() === hourStr);
                    if (!target) return false;
                    target.scrollIntoView({ block: 'center' });
                    target.click();
                    return true;
                }""",
                [hour_str],
            )
            if not hour_success:
                logger.error("Could not select hour %s", hour_str)
                return False

            await popup.wait_for_timeout(400)

            # Select minute
            minute_success = await popup.evaluate(
                """([minuteStr]) => {
                    const minuteItems = document.querySelectorAll('div.dx-dateviewroller-minutes div.dx-dateview-item');
                    const target = Array.from(minuteItems).find(item => item.textContent.trim() === minuteStr);
                    if (!target) return false;
                    target.scrollIntoView({ block: 'center' });
                    target.click();
                    return true;
                }""",
                [minute_str],
            )
            if not minute_success:
                logger.error("Could not select minute %s", minute_str)
                return False

            await popup.wait_for_timeout(400)

            # Click Done ("Hecho")
            done_locator = popup.locator('div.dx-popup-done:has-text("Hecho"), div.dx-popup-done[aria-label="Hecho"]')
            if await done_locator.count() > 0:
                try:
                    await done_locator.first.wait_for(state="visible", timeout=2000)
                    await done_locator.first.click()
                    await popup.wait_for_timeout(500)
                    return True
                except Exception:
                    pass

            done_clicked = await popup.evaluate(
                """() => {
                    const candidates = Array.from(document.querySelectorAll('div.dx-popup-done'));
                    const button = candidates.find(el => {
                        const text = el.textContent && el.textContent.trim();
                        return text === 'Hecho' || el.getAttribute('aria-label') === 'Hecho';
                    });
                    if (!button) return false;
                    button.click();
                    return true;
                }"""
            )
            if done_clicked:
                await popup.wait_for_timeout(500)
                return True

            fallback_button = popup.locator("text=Hecho")
            if await fallback_button.count() > 0:
                await fallback_button.first.click()
                await popup.wait_for_timeout(500)
                return True

            logger.error("Could not find Done button in datetime picker")
            return False
        except Exception as e:
            logger.error("Error setting datetime picker time: %s", e)
            return False

    async def _login(self, popup: Page) -> None:
        """Perform login on the VTPortal popup page."""
        logger.info("Starting portal login (client: %s)...", self.config.client)
        await popup.wait_for_load_state("networkidle")
        await popup.wait_for_timeout(1500)

        if self.config.language:
            await self._set_dx_selectbox(popup, "div.dx-field-value.lang", self.config.language)
            await popup.wait_for_timeout(400)

        await self._set_dx_textbox(popup, 'div[data-testid="login-client-field"]', self.config.client)
        await popup.wait_for_timeout(400)

        await self._set_dx_textbox(popup, 'div[data-testid="login-username-field"]', self.config.username)
        await popup.wait_for_timeout(400)

        await self._set_dx_textbox(popup, "#accessPwd", self.config.password)
        await popup.wait_for_timeout(400)

        submit_button = popup.locator('[data-testid="login-submit-btn"]')
        await submit_button.wait_for(state="visible", timeout=15000)

        try:
            await popup.wait_for_function(
                """() => {
                    const btn = document.querySelector('[data-testid="login-submit-btn"]');
                    return btn && btn.getAttribute('aria-disabled') !== 'true';
                }""",
                timeout=15000,
            )
        except PlaywrightTimeoutError:
            logger.warning("Submit button not enabled in time, attempting click anyway")

        await submit_button.click()
        logger.info("Login form submitted, awaiting navigation...")

        try:
            await popup.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass

        await popup.wait_for_timeout(2000)
        logger.info("Login completed successfully")

        if self.session_file:
            try:
                await popup.context.storage_state(path=str(self.session_file))
                logger.info("Saved updated session storage to %s", self.session_file)
            except Exception as e:
                logger.warning("Failed to save storage_state: %s", e)

    async def _navigate_to_gestion_horaria(self, popup: Page, target_date: datetime | None = None) -> None:
        """Navigate to 'Gestión horaria' (scheduler view) for the target date."""
        dt = target_date or datetime.now()
        date_str = dt.strftime("%Y-%m-%d")
        logger.debug("Navigating to scheduler for %s...", date_str)

        # Handle forced logout before navigation
        if await self._check_and_handle_forced_logout(popup):
            await popup.wait_for_timeout(1000)

        # If on a sub-view (like Detalle de fichajes), click Back button safely to return to scheduler view
        try:
            await popup.evaluate(
                """() => {
                    const btn = document.querySelector('div.dx-button-back, div[aria-label="Back"]');
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                    }
                }"""
            )
            await popup.wait_for_timeout(600)
        except Exception:
            pass

        try:
            navigated = await popup.evaluate(
                """([dateStr]) => {
                    if (window.VTPortal && window.VTPortal.app && typeof window.VTPortal.app.navigate === 'function') {
                        window.VTPortal.app.navigate('scheduler/1/' + dateStr);
                        return true;
                    }
                    return false;
                }""",
                [date_str],
            )
            if navigated:
                await popup.wait_for_timeout(1500)
                try:
                    await popup.wait_for_selector(".dx-loadpanel, .dx-overlay-shader", state="hidden", timeout=5000)
                except Exception:
                    pass

                # Check if navigation triggered a forced logout redirect
                if await self._check_and_handle_forced_logout(popup):
                    await popup.wait_for_timeout(1000)
                    await popup.evaluate(
                        """([dateStr]) => {
                            if (window.VTPortal && window.VTPortal.app && typeof window.VTPortal.app.navigate === 'function') {
                                window.VTPortal.app.navigate('scheduler/1/' + dateStr);
                            }
                        }""",
                        [date_str],
                    )
                    await popup.wait_for_timeout(1500)
                return
        except Exception as e:
            logger.warning("Direct SPA navigate to scheduler failed: %s", e)

        # Fallback to clicking hamburger menu
        try:
            await popup.click(".dx-menu-hamburger-button, .dx-icon-menu", timeout=3000)
            await popup.wait_for_timeout(800)
            await popup.evaluate(
                """() => {
                    const span = Array.from(document.querySelectorAll('.hamburgerMenuItem')).find(s => {
                        const txt = (s.textContent || '').toLowerCase();
                        return txt.includes('gestión') || txt.includes('gestion');
                    });
                    if (span) {
                        const parent = span.closest('.dx-menu-item, div') || span;
                        parent.click();
                    }
                }"""
            )
            await popup.wait_for_timeout(1500)
            if await self._check_and_handle_forced_logout(popup):
                await popup.wait_for_timeout(1000)
        except Exception as e:
            logger.warning("Hamburger navigation fallback failed: %s", e)

    async def _navigate_calendar_to_month(self, popup: Page, target_month: int, target_year: int) -> bool:
        """Navigate calendar navigator until target month and year are reached."""
        target_year_str = str(target_year)
        aliases = MONTH_ALIASES.get(target_month, [])
        logger.debug("Navigating calendar to month %s year %s", target_month, target_year)

        # 1. Try fast direct navigation via DevExtreme dxCalendar API
        try:
            switched = await popup.evaluate(
                """([year, month]) => {
                    const $cal = $('.dx-calendar');
                    if ($cal.length) {
                        const inst = $cal.dxCalendar('instance');
                        if (inst) {
                            inst.option('value', new Date(year, month - 1, 1));
                            return true;
                        }
                    }
                    return false;
                }""",
                [target_year, target_month],
            )
            if switched:
                await popup.wait_for_timeout(800)
                caption_elem = popup.locator("a.dx-calendar-caption-button span.dx-button-text, a.dx-calendar-caption-button")
                if await caption_elem.count() > 0:
                    current_caption = (await caption_elem.first.text_content() or "").strip().lower()
                    if target_year_str in current_caption and any(a in current_caption for a in aliases):
                        return True
        except Exception:
            pass

        # 2. Step-by-step navigation fallback via arrow buttons
        for _ in range(24):
            current_caption = ""
            try:
                caption_elem = popup.locator("a.dx-calendar-caption-button span.dx-button-text, a.dx-calendar-caption-button")
                if await caption_elem.count() > 0:
                    current_caption = (await caption_elem.first.text_content() or "").strip().lower()
                    if target_year_str in current_caption and any(a in current_caption for a in aliases):
                        return True
            except Exception:
                pass

            # Determine direction
            direction = "next"
            if current_caption:
                parts = current_caption.split()
                if len(parts) >= 2:
                    cur_month = MONTH_NUMS.get(parts[0])
                    try:
                        cur_year = int(parts[1])
                        if cur_month is not None:
                            if cur_year > target_year or (cur_year == target_year and cur_month > target_month):
                                direction = "prev"
                            elif cur_year < target_year or (cur_year == target_year and cur_month < target_month):
                                direction = "next"
                            else:
                                return True
                    except ValueError:
                        pass

            next_btn = popup.locator("a.dx-calendar-navigator-next-view, a.dx-calendar-navigator-next-month, a[aria-label*='chevronright']")
            prev_btn = popup.locator("a.dx-calendar-navigator-previous-view, a.dx-calendar-navigator-previous-month, a[aria-label*='chevronleft']")

            if direction == "next" and await next_btn.count() > 0:
                await next_btn.first.click(force=True)
            elif direction == "prev" and await prev_btn.count() > 0:
                await prev_btn.first.click(force=True)
            else:
                break

            await popup.wait_for_timeout(500)

        logger.warning("Could not reach calendar month: %s %s", target_month, target_year)
        return False

    async def _select_calendar_day(self, popup: Page, target_date: datetime) -> tuple[bool, str]:
        """Select a date in the calendar.
        
        Returns:
            (success: bool, status_code: str)
            status_code can be 'selected', 'holiday', or 'not_found'.
        """
        # Check forced logout before calendar operations
        if await self._check_and_handle_forced_logout(popup):
            await self._navigate_to_gestion_horaria(popup, target_date)

        await popup.wait_for_timeout(500)
        navigated = await self._navigate_calendar_to_month(popup, target_date.month, target_date.year)
        if not navigated:
            return False, "navigation_failed"

        async def check_is_holiday(loc) -> bool:
            try:
                return await loc.evaluate(
                    r"""(el) => {
                        // 1. If cell explicitly has a work presence shift indicator, it is a normal working day
                        if (el.querySelector('.dx-icon-Cal_TC_Presence, [class*="Presence"], [class*="presence"]')) {
                            return false;
                        }

                        // 2. Check tooltip, title, and aria-label for explicit holiday/vacation/leave terms
                        const title = (el.getAttribute('title') || '').toLowerCase();
                        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                        const leaveTerms = ['festiv', 'vacac', 'holiday', 'fiesta laboral', 'convenio', 'permiso', 'ausencia', 'baja', 'leave'];
                        for (const term of leaveTerms) {
                            if (title.includes(term) || ariaLabel.includes(term)) {
                                return true;
                            }
                        }

                        // 3. Check for explicit holiday/absence icons or class names
                        const holidaySelector = [
                            '.dx-icon-Cal_TC_Holiday',
                            '.dx-icon-Cal_TC_Absence',
                            '[class*="holiday" i]',
                            '[class*="festiv" i]',
                            '[class*="vacacion" i]',
                            '[class*="permiso" i]',
                            '[class*="ausencia" i]',
                            '[class*="baja" i]'
                        ].join(',');
                        if (el.querySelector(holidaySelector)) {
                            return true;
                        }

                        // 4. Check for special leave / absence styling or border in the daily template
                        const innerDiv = el.querySelector('.innerCalCellTemplate > div, .CalendarCellDailyLayout div');
                        if (innerDiv) {
                            const style = innerDiv.getAttribute('style') || '';
                            if (style.includes('#a400cc') || style.includes('rgb(164, 0, 204)')) {
                                return true;
                            }
                        }

                        // 5. On a weekday, if there is no presence icon, it represents an absence, special leave, or holiday
                        const isWeekendCell = el.classList.contains('dx-calendar-cell-weekend') ||
                                              ariaLabel.includes('sábado') ||
                                              ariaLabel.includes('domingo') ||
                                              ariaLabel.includes('sabado');
                        if (!isWeekendCell) {
                            return true;
                        }

                        return false;
                    }"""
                )
            except Exception:
                return False

        date_value = f"{target_date.year:04d}/{target_date.month:02d}/{target_date.day:02d}"
        selector = (
            f'td.dx-calendar-cell[role="option"][data-value="{date_value}"],'
            f'td[role="option"][data-value="{date_value}"]'
        )

        locator = popup.locator(selector)
        if await locator.count() > 0 and await locator.first.is_visible():
            if await check_is_holiday(locator.first):
                logger.info("Date %s is marked as holiday / vacation in calendar.", date_value)
                return False, "holiday"

            await locator.first.evaluate("e => { e.scrollIntoView({ block: 'center' }); e.click(); }")
            await popup.wait_for_timeout(800)
            return True, "selected"

        # Fallback by text
        day_text = str(target_date.day)
        fallback_locator = popup.locator(
            f'td.dx-calendar-cell:has-text("{day_text}"), td:has-text("{day_text}"), button:has-text("{day_text}")'
        )
        count = await fallback_locator.count()
        for i in range(count):
            item = fallback_locator.nth(i)
            if await item.is_visible():
                if await check_is_holiday(item):
                    return False, "holiday"
                await item.evaluate("e => { e.scrollIntoView({ block: 'center' }); e.click(); }")
                await popup.wait_for_timeout(800)
                return True, "selected"

        return False

    async def _click_detalles_de_fichajes(self, popup: Page) -> bool:
        """Click 'Detalle de fichajes'."""
        await popup.wait_for_timeout(600)
        selectors = [
            'div.textActionCalendar:has-text("Detalle de fichajes")',
            'div.textActionCalendar:has-text("detalle de fichajes")',
            'div.dx-item-content:has-text("Detalle de fichajes")',
            'div.dx-item-content:has-text("detalle de fichajes")',
        ]

        for s in selectors:
            loc = popup.locator(s)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(force=True)
                await popup.wait_for_timeout(800)
                return True

        clicked = await popup.evaluate(
            """() => {
                const label = document.querySelector('div.textActionCalendar');
                if (label && label.textContent && label.textContent.trim().toLowerCase().includes('detalle de fichajes')) {
                    const clickable = label.closest('div.dx-item-content') || label;
                    clickable.scrollIntoView({ block: 'center', inline: 'nearest' });
                    clickable.click();
                    return true;
                }
                const options = Array.from(document.querySelectorAll('div.dx-item.dx-list-item[role="option"]'));
                for (const option of options) {
                    const inner = option.querySelector('.textActionCalendar');
                    if (inner && inner.textContent && inner.textContent.trim().toLowerCase().includes('detalle de fichajes')) {
                        const clickable = option.querySelector('.dx-item-content') || option;
                        clickable.scrollIntoView({ block: 'center', inline: 'nearest' });
                        clickable.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if clicked:
            await popup.wait_for_timeout(800)
            return True

        return False

    async def _inspect_day_entries(self, popup: Page) -> dict[str, Any]:
        """Inspect existing clock-in and clock-out entries for the day."""
        await popup.wait_for_timeout(800)
        try:
            return await popup.evaluate(
                """() => {
                    const entries = Array.from(document.querySelectorAll('div.dx-item.dx-list-item'));
                    const response = { entrada: false, salida: false, items: [] };
                    for (const entry of entries) {
                        const icon = entry.querySelector('.listMenuItemIcon');
                        const text = entry.querySelector('.listMenuItemContent > div')?.textContent?.trim() || '';
                        const className = icon ? icon.className : '';
                        const hasIn = /dx-icon-(?:TA|TATC)_in/.test(className);
                        const hasOut = /dx-icon-(?:TA|TATC)_out/.test(className);
                        if (hasIn) response.entrada = true;
                        if (hasOut) response.salida = true;
                        response.items.push({ text, icon: className });
                    }
                    return response;
                }"""
            )
        except Exception as e:
            logger.error("Error inspecting day entries: %s", e)
            return {"entrada": False, "salida": False, "items": []}

    async def _click_add_request_button(self, popup: Page) -> bool:
        """Click the add-request button (+ icon)."""
        await popup.wait_for_timeout(500)
        button = popup.locator('#btnActionMenuPopover, div[data-bind*="newRequest"], div.actionButton.fixedButton')
        if await button.count() > 0:
            if await button.first.is_visible():
                try:
                    await button.first.click(force=True)
                except Exception:
                    await popup.evaluate('document.querySelector("#btnActionMenuPopover")?.click()')
            else:
                await popup.evaluate('document.querySelector("#btnActionMenuPopover")?.click()')

            await popup.wait_for_timeout(1000)
            try:
                await popup.wait_for_selector("div.dx-fieldset", timeout=5000)
                return True
            except Exception:
                return await popup.locator("div.dx-fieldset").count() > 0

        return False

    async def _submit_time_request_internal(
        self,
        popup: Page,
        request_type: str,
        time_value: str,
        target_date: datetime,
        work_mode: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Submit an entrada or salida time request."""
        status = await self._inspect_day_entries(popup)
        if not force:
            if request_type == "entrada" and status.get("entrada"):
                return {"success": True, "already_existed": True, "message": "Entrada already exists for this day"}
            if request_type == "salida" and status.get("salida"):
                return {"success": True, "already_existed": True, "message": "Salida already exists for this day"}

        opened = await self._click_add_request_button(popup)
        if not opened:
            return {"success": False, "error": "Could not open new request form (+ button)"}

        await popup.wait_for_timeout(500)

        # Select request type (Sentido: Entrada / Salida)
        request_selector_text = {
            "entrada": ["entrada", "fichar entrada", "registro entrada"],
            "salida": ["salida", "fichar salida", "registro salida"],
        }
        selected = False
        for opt in request_selector_text.get(request_type, []):
            loc = popup.locator(f'text="{opt}"')
            if await loc.count() > 0:
                await loc.first.click()
                selected = True
                await popup.wait_for_timeout(500)
                break

        if not selected:
            opt_name = "Entrada" if request_type == "entrada" else "Salida"
            selected = await self._select_dx_dropdown_option_by_label(popup, "Sentido", opt_name)

        if not selected:
            return {"success": False, "error": f"Failed to select request type '{request_type}'"}

        # Select work mode
        actual_work_mode = work_mode or get_default_work_mode(target_date)
        await self._select_dx_dropdown_option_by_label(popup, "¿Desde dónde trabajaste?", actual_work_mode)

        # Set time
        time_set = await self._set_datetime_picker_time(popup, time_value)
        if not time_set:
            return {"success": False, "error": f"Failed to set datetime picker to '{time_value}'"}

        # Click save
        await popup.evaluate("""() => {
            $('.dx-overlay-wrapper.dx-datebox-wrapper').hide();
        }""")
        await popup.wait_for_timeout(300)
        guardar_selector = 'div[title="Guardar"], div[aria-label="save"], div[data-bind*="btnSave"]'
        guardar_locator = popup.locator(guardar_selector)
        if await guardar_locator.count() > 0:
            await guardar_locator.first.click(force=True)
            try:
                await popup.wait_for_selector("div.dx-fieldset", state="hidden", timeout=10000)
            except Exception:
                pass
            await popup.wait_for_timeout(1000)
            return {
                "success": True,
                "already_existed": False,
                "request_type": request_type,
                "time": time_value,
                "work_mode": actual_work_mode,
                "date": target_date.strftime("%Y-%m-%d"),
            }

        return {"success": False, "error": "Guardar button not found"}

    # ---------------- Public API Methods ----------------

    async def check_day_status(self, date_val: str | datetime | None = None) -> dict[str, Any]:
        """Check clock-in/out records, work status, and holiday status for a given date."""
        target_date = parse_target_date(date_val)
        date_str = target_date.strftime("%Y-%m-%d")
        day_of_week = target_date.strftime("%A")
        is_weekend = target_date.weekday() >= 5
        expected_enter, expected_exit = get_time_range(target_date)
        default_work_mode = get_default_work_mode(target_date)

        result: dict[str, Any] = {
            "date": date_str,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "is_holiday_or_vacation": False,
            "has_entrada": False,
            "has_salida": False,
            "entries": [],
            "expected_schedule": {
                "enter_time": expected_enter,
                "exit_time": expected_exit,
                "default_work_mode": default_work_mode,
            },
        }

        if is_weekend:
            result["status"] = "weekend"
            result["message"] = f"{date_str} is a weekend ({day_of_week})."
            return result

        try:
            popup = await self._ensure_active_session()
            await self._navigate_to_gestion_horaria(popup, target_date)

            selected, status_code = await self._select_calendar_day(popup, target_date)
            if status_code == "holiday":
                result["is_holiday_or_vacation"] = True
                result["status"] = "holiday"
                result["message"] = f"{date_str} is marked as a holiday or vacation."
                return result
            if not selected:
                result["status"] = "not_found"
                result["message"] = f"Could not find or select {date_str} in calendar."
                return result

            clicked_details = await self._click_detalles_de_fichajes(popup)
            if not clicked_details:
                result["status"] = "error"
                result["message"] = "Could not open Detalle de fichajes."
                return result

            entries_info = await self._inspect_day_entries(popup)
            result["has_entrada"] = entries_info.get("entrada", False)
            result["has_salida"] = entries_info.get("salida", False)
            result["entries"] = entries_info.get("items", [])
            result["status"] = "ok"
            result["message"] = (
                f"Status for {date_str}: entrada={'yes' if result['has_entrada'] else 'no'}, "
                f"salida={'yes' if result['has_salida'] else 'no'}."
            )
            return result
        except Exception as e:
            logger.error("check_day_status failed: %s", e)
            await self.close()
            raise

    async def clock_in_out(
        self,
        request_type: str,
        date_val: str | datetime | None = None,
        time_value: str | None = None,
        work_mode: str | None = None,
        force: bool = False,
        jitter_minutes: int = 0,
    ) -> dict[str, Any]:
        """Submit a single entrada or salida time request."""
        target_date = parse_target_date(date_val)
        req_type = request_type.strip().lower()
        if req_type not in ("entrada", "salida"):
            raise ValueError(f"Invalid request_type '{request_type}'. Must be 'entrada' or 'salida'.")

        default_enter, default_exit = get_time_range(target_date)
        actual_time = time_value or (default_enter if req_type == "entrada" else default_exit)
        if jitter_minutes > 0 and not time_value:
            actual_time = add_time_jitter(actual_time, jitter_minutes)

        actual_work_mode = work_mode or get_default_work_mode(target_date)

        try:
            popup = await self._ensure_active_session()
            await self._navigate_to_gestion_horaria(popup, target_date)

            selected, status_code = await self._select_calendar_day(popup, target_date)
            if status_code == "holiday" and not force:
                return {
                    "success": False,
                    "status": "holiday",
                    "message": f"{target_date.date()} is marked as a holiday or vacation. Skipped.",
                }
            if not selected:
                return {
                    "success": False,
                    "status": "not_found",
                    "message": f"Could not find or select {target_date.date()} in calendar.",
                }

            await self._click_detalles_de_fichajes(popup)
            res = await self._submit_time_request_internal(
                popup,
                req_type,
                actual_time,
                target_date,
                work_mode=actual_work_mode,
                force=force,
            )
            return res
        except Exception as e:
            logger.error("clock_in_out failed: %s", e)
            await self.close()
            raise

    async def fill_day(
        self,
        date_val: str | datetime | None = None,
        work_mode: str | None = None,
        enter_time: str | None = None,
        exit_time: str | None = None,
        skip_if_holiday: bool = True,
        jitter_minutes: int = 0,
    ) -> dict[str, Any]:
        """Fill both entrada and salida for a given day (skipping existing entries)."""
        target_date = parse_target_date(date_val)
        date_str = target_date.strftime("%Y-%m-%d")

        if target_date.weekday() >= 5:
            return {
                "date": date_str,
                "status": "skipped_weekend",
                "message": f"{date_str} is a weekend day. Skipped.",
            }

        default_enter, default_exit = get_time_range(target_date)
        actual_enter = enter_time or default_enter
        actual_exit = exit_time or default_exit
        if jitter_minutes > 0:
            if not enter_time:
                actual_enter = add_time_jitter(actual_enter, jitter_minutes)
            if not exit_time:
                actual_exit = add_time_jitter(actual_exit, jitter_minutes)

        actual_work_mode = work_mode or get_default_work_mode(target_date)

        try:
            popup = await self._ensure_active_session()
            await self._navigate_to_gestion_horaria(popup, target_date)

            selected, status_code = await self._select_calendar_day(popup, target_date)
            if status_code == "holiday" and skip_if_holiday:
                return {
                    "date": date_str,
                    "status": "skipped_holiday",
                    "message": f"{date_str} is marked as holiday / vacation. Skipped.",
                }
            if not selected:
                return {
                    "date": date_str,
                    "status": "error",
                    "message": f"Could not select {date_str} in calendar.",
                }

            await self._click_detalles_de_fichajes(popup)
            res_in = await self._submit_time_request_internal(
                popup,
                "entrada",
                actual_enter,
                target_date,
                work_mode=actual_work_mode,
            )

            # Re-navigate to Gestion Horaria for salida
            await self._navigate_to_gestion_horaria(popup, target_date)
            selected_exit, _ = await self._select_calendar_day(popup, target_date)
            if not selected_exit:
                return {
                    "date": date_str,
                    "entrada": res_in,
                    "salida": {"success": False, "error": "Could not re-select day for salida"},
                }

            await self._click_detalles_de_fichajes(popup)
            res_out = await self._submit_time_request_internal(
                popup,
                "salida",
                actual_exit,
                target_date,
                work_mode=actual_work_mode,
            )

            return {
                "date": date_str,
                "entrada": res_in,
                "salida": res_out,
                "status": "completed",
            }
        except Exception as e:
            logger.error("fill_day failed: %s", e)
            await self.close()
            raise

    async def process_dates(
        self,
        dates: list[str | datetime],
        skip_weekends: bool = True,
        skip_holidays: bool = True,
        work_mode: str | None = None,
        work_mode_map: dict[str, str] | None = None,
        enter_time: str | None = None,
        exit_time: str | None = None,
        jitter_minutes: int = 0,
    ) -> dict[str, Any]:
        """Iterate a specific list of dates and auto-fill missing clock-in/out entries."""
        results = []
        try:
            popup = await self._ensure_active_session()

            for d_val in dates:
                cur = parse_target_date(d_val)
                cur_str = cur.strftime("%Y-%m-%d")

                if skip_weekends and cur.weekday() >= 5:
                    results.append({
                        "date": cur_str,
                        "status": "skipped_weekend",
                        "message": "Weekend day skipped",
                    })
                    continue

                default_in, default_out = get_time_range(cur)
                day_enter = enter_time or default_in
                day_exit = exit_time or default_out

                if jitter_minutes > 0:
                    if not enter_time:
                        day_enter = add_time_jitter(day_enter, jitter_minutes)
                    if not exit_time:
                        day_exit = add_time_jitter(day_exit, jitter_minutes)

                if work_mode_map and cur_str in work_mode_map:
                    day_mode = work_mode_map[cur_str]
                else:
                    day_mode = work_mode or get_default_work_mode(cur)

                try:
                    await self._navigate_to_gestion_horaria(popup, cur)
                    selected, status_code = await self._select_calendar_day(popup, cur)
                    if status_code == "holiday" and skip_holidays:
                        results.append({
                            "date": cur_str,
                            "status": "skipped_holiday",
                            "message": "Holiday/vacation day skipped",
                        })
                        continue

                    if not selected:
                        results.append({
                            "date": cur_str,
                            "status": "error",
                            "message": "Could not select calendar day",
                        })
                        continue

                    # Entrada
                    await self._click_detalles_de_fichajes(popup)
                    res_in = await self._submit_time_request_internal(
                        popup, "entrada", day_enter, cur, work_mode=day_mode
                    )

                    # Salida
                    await self._navigate_to_gestion_horaria(popup, cur)
                    selected_exit, _ = await self._select_calendar_day(popup, cur)
                    if selected_exit:
                        await self._click_detalles_de_fichajes(popup)
                        res_out = await self._submit_time_request_internal(
                            popup, "salida", day_exit, cur, work_mode=day_mode
                        )
                    else:
                        res_out = {"success": False, "error": "Could not re-select day for salida"}

                    results.append({
                        "date": cur_str,
                        "entrada": res_in,
                        "salida": res_out,
                        "status": "completed",
                    })

                    await popup.wait_for_timeout(600)
                except Exception as e:
                    logger.error("Error processing day %s: %s", cur_str, e)
                    if await self._check_and_handle_forced_logout(popup):
                        results.append({
                            "date": cur_str,
                            "status": "recovered_relogin",
                            "error": f"Forced logout encountered and recovered: {e}",
                        })
                    else:
                        results.append({
                            "date": cur_str,
                            "status": "error",
                            "error": str(e),
                        })

            return {
                "total_days": len(results),
                "days": results,
            }
        except Exception as e:
            logger.error("process_dates failed: %s", e)
            await self.close()
            raise

    async def process_period(
        self,
        start_date_val: str | datetime,
        end_date_val: str | datetime,
        skip_weekends: bool = True,
        skip_holidays: bool = True,
        work_mode: str | None = None,
        work_mode_map: dict[str, str] | None = None,
        enter_time: str | None = None,
        exit_time: str | None = None,
        jitter_minutes: int = 0,
    ) -> dict[str, Any]:
        """Iterate all days in [start_date, end_date] and auto-fill entries."""
        start_dt = parse_target_date(start_date_val)
        end_dt = parse_target_date(end_date_val)

        if end_dt < start_dt:
            raise ValueError(f"End date ({end_dt.date()}) is before start date ({start_dt.date()}).")

        date_list = []
        cur = start_dt
        while cur.date() <= end_dt.date():
            date_list.append(cur)
            cur += timedelta(days=1)

        res = await self.process_dates(
            dates=date_list,
            skip_weekends=skip_weekends,
            skip_holidays=skip_holidays,
            work_mode=work_mode,
            work_mode_map=work_mode_map,
            enter_time=enter_time,
            exit_time=exit_time,
            jitter_minutes=jitter_minutes,
        )
        res["start_date"] = start_dt.strftime("%Y-%m-%d")
        res["end_date"] = end_dt.strftime("%Y-%m-%d")
        return res

    async def find_missing_dates(
        self,
        start_date_val: str | datetime | None = None,
        end_date_val: str | datetime | None = None,
    ) -> dict[str, Any]:
        """Scan calendar to find weekdays with missing entrada or salida entries."""
        now = datetime.now()
        start_dt = parse_target_date(start_date_val) if start_date_val else datetime(now.year, now.month, 1)
        end_dt = parse_target_date(end_date_val) if end_date_val else now

        if end_dt < start_dt:
            raise ValueError(f"End date ({end_dt.date()}) is before start date ({start_dt.date()}).")

        missing_days = []
        completed_days = []
        holidays = []
        weekends = []

        try:
            popup = await self._ensure_active_session()
            cur = start_dt
            while cur.date() <= end_dt.date():
                cur_str = cur.strftime("%Y-%m-%d")
                day_name = cur.strftime("%A")

                if cur.weekday() >= 5:
                    weekends.append(cur_str)
                    cur += timedelta(days=1)
                    continue

                try:
                    await self._navigate_to_gestion_horaria(popup, cur)
                    selected, status_code = await self._select_calendar_day(popup, cur)
                    if status_code == "holiday":
                        holidays.append({"date": cur_str, "day": day_name})
                        cur += timedelta(days=1)
                        continue

                    if not selected:
                        missing_days.append({
                            "date": cur_str,
                            "day": day_name,
                            "status": "could_not_select",
                            "missing": ["entrada", "salida"],
                        })
                        cur += timedelta(days=1)
                        continue

                    await self._click_detalles_de_fichajes(popup)
                    entries_info = await self._inspect_day_entries(popup)
                    has_in = entries_info.get("entrada", False)
                    has_out = entries_info.get("salida", False)

                    missing_types = []
                    if not has_in:
                        missing_types.append("entrada")
                    if not has_out:
                        missing_types.append("salida")

                    expected_enter, expected_exit = get_time_range(cur)
                    default_mode = get_default_work_mode(cur)

                    day_record = {
                        "date": cur_str,
                        "day": day_name,
                        "has_entrada": has_in,
                        "has_salida": has_out,
                        "missing": missing_types,
                        "expected_schedule": {
                            "enter_time": expected_enter,
                            "exit_time": expected_exit,
                            "work_mode": default_mode,
                        },
                    }

                    if missing_types:
                        missing_days.append(day_record)
                    else:
                        completed_days.append(day_record)

                    await popup.wait_for_timeout(500)
                except Exception as e:
                    logger.error("Error inspecting day %s: %s", cur_str, e)
                    if await self._check_and_handle_forced_logout(popup):
                        logger.info("Recovered from forced logout, retrying day %s", cur_str)
                        continue
                    missing_days.append({
                        "date": cur_str,
                        "day": day_name,
                        "error": str(e),
                        "missing": ["unknown"],
                    })

                cur += timedelta(days=1)

            return {
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
                "missing_days_count": len(missing_days),
                "missing_days": missing_days,
                "completed_days_count": len(completed_days),
                "completed_days": completed_days,
                "holidays": holidays,
            }
        except Exception as e:
            logger.error("find_missing_dates failed: %s", e)
            await self.close()
            raise
