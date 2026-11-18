import os
import builtins
from datetime import datetime, timedelta
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


DEBUG = False

def debug_print(*args, **kwargs):
    if DEBUG:
        builtins.print(*args, **kwargs)

def print_info(*args, **kwargs):
    builtins.print(*args, **kwargs)

# Override the default print function for this module to suppress logs when DEBUG is False
print = debug_print

MONTH_NAMES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

def read_secret(name: str, prompt_text: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value
    if default is not None:
        prompt = f"{prompt_text} [{default}]: "
        answer = input(prompt).strip()
        return answer or default
    return input(f"{prompt_text}: ").strip()


def set_dx_textbox(page, selector: str, value: str, widget_name: str = "dxTextBox"):
    return page.evaluate(
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


def set_dx_selectbox(page, selector: str, value: str):
    return page.evaluate(
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


def select_dx_dropdown_option_by_label(popup, field_label: str, option_text: str) -> bool:
    """Open a DX select box by field label and choose an option by visible text."""
    print(f'Selecting DX dropdown option for label "{field_label}" -> "{option_text}"')
    popup.wait_for_timeout(300)
    try:
        field = popup.locator(f'div.dx-field:has(span:has-text("{field_label}"))')
        if field.count() == 0:
            print(f'No field found for label: {field_label}')
            return False

        select_box = field.locator('div.dx-selectbox, div.dx-dropdowneditor')
        if select_box.count() == 0:
            print(f'No selectbox found for field label: {field_label}')
            return False

        select_box.first.click()
        popup.wait_for_timeout(400)

        # Fallback to a JS selection on the visible overlay list.
        print(f'Fallback: trying JS selection for option text: {option_text}')
        clicked = popup.evaluate(
            '''([optionText]) => {
                const options = Array.from(document.querySelectorAll('div.dx-list-item, div[role="option"]'));
                const target = options.find(opt => opt.textContent && opt.textContent.trim().toLowerCase().includes(optionText.toLowerCase()));
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }''',
            [option_text],
        )
        if clicked:
            popup.wait_for_timeout(400)
            print(f'Selected "{option_text}" via JS fallback for "{field_label}"')
            return True

        print(f'No dropdown option found with text: {option_text}')
        return False
    except Exception as e:
        print(f'Error selecting dropdown option for {field_label}: {e}')
        return False


def select_dx_dropdown_option_by_any_option_text(popup, option_text: str) -> bool:
    """Select an option from the currently open DX dropdown overlay by text."""
    try:
        option_locator = popup.locator(
            f'div.dx-list-item:has-text("{option_text}"), div[role="option"]:has-text("{option_text}"), div.dx-item-content:has-text("{option_text}")'
        )
        if option_locator.count() > 0:
            option_locator.first.click()
            popup.wait_for_timeout(400)
            return True

        clicked = popup.evaluate(
            '''([optionText]) => {
                const options = Array.from(document.querySelectorAll('div.dx-list-item, div[role="option"], div.dx-item-content'));
                const target = options.find(opt => opt.textContent && opt.textContent.trim().toLowerCase().includes(optionText.toLowerCase()));
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }''',
            [option_text],
        )
        if clicked:
            popup.wait_for_timeout(400)
            return True

        return False
    except Exception as e:
        print(f'Error selecting option by text "{option_text}": {e}')
        return False


def set_datetime_picker_time(popup, time_value: str) -> bool:
    """Set hours and minutes in the 'Fecha y hora' datetime picker.
    
    Args:
        popup: The Playwright page object
        time_value: Time in 'HH:MM' format (e.g., '08:30')
    
    Returns:
        True if time was set successfully, False otherwise
    """
    print(f'Setting datetime picker time to {time_value}')
    try:
        parts = time_value.split(':')
        if len(parts) != 2:
            print(f'Invalid time format: {time_value}')
            return False

        hour_str = parts[0].zfill(2)
        minute_str = parts[1].zfill(2)

        popup.wait_for_timeout(300)

        # Click to open the datetime picker
        fecha_field = popup.locator('div.dx-datebox-datetime div.dx-dropdowneditor-button')
        if fecha_field.count() == 0:
            print('Could not find datetime picker button')
            return False

        fecha_field.first.click()
        popup.wait_for_timeout(500)

        # Select the hour value
        hour_success = popup.evaluate(
            '''([hourStr]) => {
                const hourItems = document.querySelectorAll('div.dx-dateviewroller-hours div.dx-dateview-item');
                const target = Array.from(hourItems).find(item => item.textContent.trim() === hourStr);
                if (!target) return false;
                target.scrollIntoView({ block: 'center' });
                target.click();
                return true;
            }''',
            [hour_str],
        )

        if not hour_success:
            print(f'Could not select hour {hour_str}')
            return False

        popup.wait_for_timeout(400)

        # Select the minute value
        minute_success = popup.evaluate(
            '''([minuteStr]) => {
                const minuteItems = document.querySelectorAll('div.dx-dateviewroller-minutes div.dx-dateview-item');
                const target = Array.from(minuteItems).find(item => item.textContent.trim() === minuteStr);
                if (!target) return false;
                target.scrollIntoView({ block: 'center' });
                target.click();
                return true;
            }''',
            [minute_str],
        )

        if not minute_success:
            print(f'Could not select minute {minute_str}')
            return False

        popup.wait_for_timeout(400)

        # Click the "Hecho" (Done) button
        done_locator = popup.locator('div.dx-popup-done:has-text("Hecho"), div.dx-popup-done[aria-label="Hecho"]')
        if done_locator.count() > 0:
            try:
                done_locator.first.wait_for(state='visible', timeout=2000)
                done_locator.first.click()
                popup.wait_for_timeout(500)
                print(f'Datetime set to {time_value}')
                return True
            except Exception:
                pass

        # Use JS fallback to click the button directly in the DOM
        done_clicked = popup.evaluate(
            '''() => {
                const candidates = Array.from(document.querySelectorAll('div.dx-popup-done'));
                const button = candidates.find(el => {
                    const text = el.textContent && el.textContent.trim();
                    return text === 'Hecho' || el.getAttribute('aria-label') === 'Hecho';
                });
                if (!button) return false;
                button.click();
                return true;
            }'''
        )
        if done_clicked:
            popup.wait_for_timeout(500)
            print(f'Datetime set to {time_value} via JS fallback')
            return True

        # Last fallback: any element with visible Hecho text
        fallback_button = popup.locator('text=Hecho')
        if fallback_button.count() > 0:
            fallback_button.first.click()
            popup.wait_for_timeout(500)
            print(f'Datetime set to {time_value} via fallback text locator')
            return True

        print('Could not find Done button in datetime picker')
        return False
    except Exception as e:
        print(f'Error setting datetime picker time: {e}')
        return False


def get_time_range(target_date: datetime | None = None) -> tuple[str, str]:
    """Determine time range based on the target date.
    
    June 16 - Sept 1: 8:00 to 15:00
    Otherwise: 8:30 to 18:00
    Fridays: Exit is always 15:00
    """
    target_date = target_date or datetime.now()
    month = target_date.month
    day = target_date.day
    
    # Check if between June 16 and August 31
    if (month == 6 and day >= 16) or (7 <= month <= 8):
        enter_time, exit_time = "08:00", "15:00"
    else:
        enter_time, exit_time = "08:30", "18:00"
        
    if target_date.weekday() == 4:
        exit_time = "15:00"
        
    return (enter_time, exit_time)


def process_period(popup, start_date: datetime, end_date: datetime) -> None:
    """Iterate days in [start_date, end_date] and submit entrada/salida for weekdays.

    Weekends (Saturday=5, Sunday=6) are skipped and not submitted.
    The function re-opens `Gestión horaria` and selects each date before
    attempting entrada and salida submissions.
    """
    if end_date < start_date:
        print('End date is before start date; nothing to process')
        return

    current = start_date
    while current.date() <= end_date.date():
        # weekday(): Monday=0 .. Sunday=6 ; skip Saturday(5) and Sunday(6)
        if current.weekday() < 5:
            enter_time, exit_time = get_time_range(current)
            print_info(f'Processing {current.date()} (weekday) - Entry: {enter_time}, Exit: {exit_time}')

            # Ensure Gestion Horaria is visible and select the calendar day
            try:
                navigate_to_gestion_horaria(popup)
            except Exception as e:
                print(f'Failed to navigate to Gestión horaria: {e}')

            if select_calendar_day(popup, current):
                # Submit entrada if missing
                click_detalles_de_fichajes(popup)
                submit_time_request(popup, 'entrada', enter_time, current)

                # Re-open and select again for salida (UI may require re-selection)
                try:
                    navigate_to_gestion_horaria(popup)
                except Exception:
                    pass

                if select_calendar_day(popup, current):
                    click_detalles_de_fichajes(popup)
                    submit_time_request(popup, 'salida', exit_time, current)
                else:
                    print(f'Could not select {current.date()} for salida')
            else:
                print(f'Skipped or could not select {current.date()} for entrada')

            # Small delay between days to let UI stabilise
            popup.wait_for_timeout(800)
        else:
            print_info(f'Skipping {current.date()} (weekend)')

        current = current + timedelta(days=1)


def login(popup, client: str, username: str, password: str, language: str = 'ESP') -> None:
    """Log into VTPortal."""
    popup.wait_for_load_state('networkidle')
    popup.wait_for_timeout(1500)
    print('Popup opened at', popup.url)

    if language:
        result = set_dx_selectbox(popup, 'div.dx-field-value.lang', language)
        print('Language set:', result)
        popup.wait_for_timeout(500)

    client_result = set_dx_textbox(popup, 'div[data-testid="login-client-field"]', client)
    print('Client field set:', client_result)
    popup.wait_for_timeout(500)

    username_result = set_dx_textbox(popup, 'div[data-testid="login-username-field"]', username)
    print('Username field set:', username_result)
    popup.wait_for_timeout(500)

    password_result = set_dx_textbox(popup, '#accessPwd', password)
    print('Password field set:', password_result)
    popup.wait_for_timeout(500)

    submit_button = popup.locator('[data-testid="login-submit-btn"]')
    submit_button.wait_for(state='visible', timeout=15000)

    try:
        popup.wait_for_function(
            '''() => {
                const btn = document.querySelector('[data-testid="login-submit-btn"]');
                return btn && btn.getAttribute('aria-disabled') !== 'true';
            }''',
            timeout=15000,
        )
        print('Login button enabled')
    except PlaywrightTimeoutError:
        print('Login button did not become enabled in time, trying click anyway')

    submit_button.click()
    print('Login submitted')

    try:
        popup.wait_for_load_state('networkidle', timeout=2000)
    except PlaywrightTimeoutError:
        pass

    print('Login flow complete. Current popup URL:', popup.url)
    popup.wait_for_timeout(2000)


def navigate_to_gestion_horaria(popup) -> None:
    """Navigate to 'Gestión horaria' section."""
    print('Navigating to Gestión horaria...')
    popup.wait_for_timeout(1000)

    # Open the lateral menu first, then look for Gestión horaria.
    print('Opening lateral menu before searching for Gestión horaria')
    menu_opened = False
    menu_selectors = [
        'button[aria-label*="menu" i]',
        'button[aria-label*="menú" i]',
        'div[class*="hamburger"]',
        'div[class*="burger"]',
        'div[role="button"]:has-text("☰")',
        'div[role="button"]:has-text("Menu")',
        'div[role="button"]:has-text("Menú")',
        'button:has-text("☰")',
        'button:has-text("Menu")',
        'button:has-text("Menú")',
    ]
    for selector in menu_selectors:
        try:
            locator = popup.locator(selector)
            if locator.count() > 0 and locator.first.is_visible():
                popup.click(selector, timeout=5000)
                print(f'Clicked menu opener: {selector}')
                menu_opened = True
                break
        except Exception as e:
            print(f'Failed to click menu opener {selector}: {e}')

    if not menu_opened:
        print('Menu opener not found. Attempting to click Back button twice to return to main screen...')
        back_selector = 'div.dx-button-back, div[aria-label="Back"]'
        for i in range(2):
            try:
                back_locator = popup.locator(back_selector)
                if back_locator.count() > 0 and back_locator.first.is_visible():
                    back_locator.first.click()
                    print(f'Clicked Back button (attempt {i + 1})')
                    popup.wait_for_timeout(800)
            except Exception as e:
                print(f'Failed to click Back button: {e}')

        # Retry finding and clicking the menu opener now that we are on the main screen
        for selector in menu_selectors:
            try:
                locator = popup.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    popup.click(selector, timeout=2000)
                    print(f'Clicked menu opener after going back: {selector}')
                    menu_opened = True
                    break
            except Exception:
                pass

    if not menu_opened:
        try:
            popup.mouse.click(30, 30)
            print('Clicked top-left coordinate to open sidebar menu')
            menu_opened = True
        except Exception as e:
            print('Failed to click top-left coordinate:', e)

    if menu_opened:
        popup.wait_for_timeout(1200)
    else:
        print('Sidebar menu opener was not found; proceeding to search for Gestión horaria anyway')

    # Try clicking the menu item from the navigation sidebar.
    # Use the specific dx-item-content div that wraps the hamburgerMenuItem span
    gestion_selectors = [
        'div.dx-treeview-item:has(span.hamburgerMenuItem:has-text("gestión horaria")) div.dx-item-content',
        'div.dx-treeview-item:has(span.hamburgerMenuItem:has-text("gestion horaria")) div.dx-item-content',
        'div.dx-item:has(span.hamburgerMenuItem:has-text("gestión horaria"))',
        'div.dx-item:has(span.hamburgerMenuItem:has-text("gestion horaria"))',
        'div.dx-treeview-item-content:has(span.hamburgerMenuItem:has-text("gestión horaria"))',
        'div.dx-treeview-item-content:has(span.hamburgerMenuItem:has-text("gestion horaria"))',
        'div.dx-treeview-item:has-text("gestión horaria")',
        'div.dx-treeview-item:has-text("gestion horaria")',
    ]
    clicked = False
    for selector in gestion_selectors:
        try:
            locator = popup.locator(selector)
            if locator.count() > 0:
                print(f'Found element with selector: {selector}')
                locator.first.click()
                print(f'Clicked Gestión horaria via selector: {selector}')
                popup.wait_for_timeout(500)
                clicked = True
                break
        except Exception as e:
            print(f'Failed to click selector {selector}: {e}')

    if not clicked:
        print('Could not find Gestión horaria with direct selectors, searching visible labels...')
        links = popup.query_selector_all('a, button, div[role="button"], span')
        for link in links:
            text = link.text_content() or ''
            if 'gestión' in text.lower() or 'gestion' in text.lower():
                if 'horaria' in text.lower():
                    try:
                        link.click()
                        print(f'Found and clicked fallback link: {text}')
                        clicked = True
                        popup.wait_for_timeout(500)
                        break
                    except Exception as e:
                        print(f'Failed clicking fallback link {text}: {e}')
                        continue

    if not clicked:
        raise RuntimeError('Unable to navigate to Gestión horaria; selector not found')

    popup.wait_for_timeout(500)
    popup.wait_for_load_state('networkidle', timeout=500)
    popup.wait_for_timeout(500)
    print('Gestión horaria page loaded')


def click_detalles_de_fichajes(popup) -> bool:
    """Click the Detalle de fichajes action after selecting a day."""
    print('Looking for Detalle de fichajes...')
    popup.wait_for_timeout(800)

    selectors = [
        'div.textActionCalendar:has-text("Detalle de fichajes")',
        'div.textActionCalendar:has-text("detalle de fichajes")',
        'div.dx-item-content:has-text("Detalle de fichajes")',
        'div.dx-item-content:has-text("detalle de fichajes")',
    ]

    for selector in selectors:
        try:
            locator = popup.locator(selector)
            print(f'Checking selector {selector} count:', locator.count())
            if locator.count() > 0:
                element = locator.first
                if element.is_visible():
                    print(f'Found Detalle de fichajes inner element via selector: {selector}; clicking with force')
                    element.click(force=True)
                    popup.wait_for_timeout(1000)
                    return True
        except Exception as e:
            print(f'Failed selector {selector}: {e}')

    print('Attempting DOM-based click for Detalle de fichajes')
    try:
        clicked = popup.evaluate(
            '''() => {
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
            }'''
        )
        if clicked:
            print('Clicked Detalle de fichajes via precise DOM click')
            popup.wait_for_timeout(1000)
            return True
    except Exception as e:
        print(f'DOM-based click failed: {e}')

    print('Detalle de fichajes not found or not clickable')
    return False


def navigate_calendar_to_month(popup, target_month_year: str) -> bool:
    """Navigate the calendar to a specific month.
    
    Args:
        popup: The Playwright page object
        target_month_year: Month/year in format 'mm yyyy' or 'M yyyy' (e.g., '04 2026' or '4 2026')
    
    Returns:
        True if navigation successful, False otherwise
    """
    print(f'Navigating calendar to {target_month_year}...')
    popup.wait_for_timeout(500)
    
    # Normalize the target
    parts = target_month_year.strip().split()
    if len(parts) < 2:
        print(f'Invalid month/year format: {target_month_year}')
        return False
    
    target_month = int(parts[0])
    target_year = int(parts[1])
    
    target_month_name = MONTH_NAMES_ES.get(target_month, str(target_month))
    target_caption = f'{target_month_name} {target_year}'
    print(f'Target caption: {target_caption}')
    
    # Check current calendar month
    max_attempts = 24  # 2 years worth of months
    attempts = 0
    
    while attempts < max_attempts:
        try:
            # Get current caption
            caption_elem = popup.locator('a.dx-calendar-caption-button span.dx-button-text')
            if caption_elem.count() > 0:
                current_caption = caption_elem.first.text_content().strip().lower()
                print(f'Current calendar caption: {current_caption}')
                
                if target_caption.lower() in current_caption:
                    print(f'Reached target month: {target_caption}')
                    return True
        except Exception as e:
            print(f'Error reading calendar caption: {e}')
        
        # Determine which button to click (previous or next)
        # Parse current caption to compare
        try:
            caption_elem = popup.locator('a.dx-calendar-caption-button')
            if caption_elem.count() > 0:
                caption_text = caption_elem.first.get_attribute('aria-label') or ''
                print(f'Caption aria-label: {caption_text}')
        except Exception as e:
            print(f'Could not read caption: {e}')
        
        # Determine whether to go forward or backward by comparing current and target month/year
        try:
            month_name_to_num = {v: k for k, v in MONTH_NAMES_ES.items()}
            current_parts = current_caption.split()
            if len(current_parts) >= 2:
                current_month = month_name_to_num.get(current_parts[0], None)
                current_year = int(current_parts[1])
            else:
                current_month = None
                current_year = None

            if current_month is not None and current_year is not None:
                if current_year < target_year or (current_year == target_year and current_month < target_month):
                    direction = 'next'
                elif current_year > target_year or (current_year == target_year and current_month > target_month):
                    direction = 'prev'
                else:
                    print(f'Reached target month after comparison: {target_caption}')
                    return True
            else:
                direction = 'next'

            next_button = popup.locator('a.dx-calendar-navigator-next-month, a[aria-label*="chevronright"]')
            prev_button = popup.locator('a.dx-calendar-navigator-previous-month, a[aria-label*="chevronleft"]')

            if direction == 'next' and next_button.count() > 0:
                next_button.first.click()
                print('Clicked next month button')
                popup.wait_for_timeout(500)
            elif direction == 'prev' and prev_button.count() > 0:
                prev_button.first.click()
                print('Clicked previous month button')
                popup.wait_for_timeout(500)
            else:
                print(f'Navigation button for direction {direction} not found')
                break
        except Exception as e:
            print(f'Error clicking navigation button: {e}')
            break
        
        attempts += 1
    
    print(f'Could not navigate to {target_caption} after {attempts} attempts')
    return False


def check_entry_for_date(popup, target_date_str: str) -> bool:
    """Check if there's already any entrada or salida entry for a specific date."""
    print(f'\nChecking for existing entries on {target_date_str}...')
    popup.wait_for_timeout(500)
    
    # Parse the date
    try:
        dt = datetime.strptime(target_date_str, '%d/%m/%Y')
        day = str(dt.day)
        month = dt.month
        year = dt.year
        
        month_name = MONTH_NAMES_ES.get(month, str(month))
        month_year_str = f'{month} {year}'  # e.g., '04 2025'
        
        print(f'Navigating to month: {month_name} {year}')
        
        # Navigate calendar to the target month
        navigate_calendar_to_month(popup, month_year_str)
        popup.wait_for_timeout(800)
        
    except Exception as e:
        print(f'Error parsing date {target_date_str}: {e}')
        return False
    
    date_value = f'{year:04d}/{month:02d}/{int(day):02d}'
    selector = f'td.dx-calendar-cell[role="option"][data-value="{date_value}"], td[role="option"][data-value="{date_value}"]'
    try:
        locator = popup.locator(selector)
        if locator.count() > 0 and locator.first.is_visible():
            locator.first.click(force=True)
            print(f'Clicked calendar cell for date {date_value}')
            popup.wait_for_timeout(800)
        else:
            print(f'Could not find calendar cell for exact date {date_value}; falling back to text match')
            day_locators = popup.locator(
                f'button:has-text("{day}"), div:has-text("{day}"), span:has-text("{day}")'
            )
            found_day = False
            for i in range(day_locators.count()):
                day_elem = day_locators.nth(i)
                if day_elem.is_visible():
                    try:
                        day_elem.click()
                        print(f'Clicked fallback calendar day {day}')
                        popup.wait_for_timeout(800)
                        found_day = True
                        break
                    except Exception as e:
                        print(f'Failed clicking fallback calendar day {day}: {e}')
            if not found_day:
                print(f'Could not find and click day {day} in calendar')
                return False
    except Exception as e:
        print(f'Error locating calendar day {day}: {e}')
        return False
    
    # Access detalle de fichajes
    click_detalles_de_fichajes(popup)

    # Check for entrada or salida entries in the detail view
    popup.wait_for_timeout(800)
    try:
        result = popup.evaluate(
            '''() => {
                const entries = Array.from(document.querySelectorAll('div.dx-item.dx-list-item'));
                return entries.some(entry => {
                    const icon = entry.querySelector('.listMenuItemIcon');
                    const className = icon ? icon.className : '';
                    return /dx-icon-(?:TA|TATC)_in/.test(className) || /dx-icon-(?:TA|TATC)_out/.test(className);
                });
            }'''
        )
        if result:
            print('Found existing entrada or salida entry for the selected day')
            return True
    except Exception as e:
        print(f'Error checking for entrada/salida entries: {e}')

    print('No entrada or salida entry found for the selected day')
    return False


def select_calendar_day(popup, target_date: datetime) -> bool:
    """Select an exact date from the calendar using the data-value attribute."""
    popup.wait_for_timeout(500)
    target_month_year = f'{target_date.month} {target_date.year}'
    if not navigate_calendar_to_month(popup, target_month_year):
        print(f'Could not navigate to month {target_month_year}')
        return False

    def is_holiday(loc) -> bool:
        try:
            return loc.evaluate(
                '''(el) => {
                    const html = el.outerHTML.toLowerCase();
                    return html.includes('#ff0000') || 
                           html.includes('#ffff00') || 
                           html.includes('rgb(255, 0, 0)') || 
                           html.includes('rgb(255, 255, 0)') ||
                           html.includes('rgb(255,0,0)') ||
                           html.includes('rgb(255,255,0)');
                }'''
            )
        except Exception as e:
            print(f'Error checking for holiday color: {e}')
            return False

    date_value = f'{target_date.year:04d}/{target_date.month:02d}/{target_date.day:02d}'
    selector = (
        f'td.dx-calendar-cell[role="option"][data-value="{date_value}"],' \
        f'td[role="option"][data-value="{date_value}"]'
    )
    try:
        locator = popup.locator(selector)
        if locator.count() > 0 and locator.first.is_visible():
            if is_holiday(locator.first):
                print_info(f'Day {target_date.date()} is marked as a festivity or vacation. Skipping.')
                return False
            locator.first.click(force=True)
            popup.wait_for_timeout(800)
            print(f'Clicked calendar cell for date {date_value}')
            return True

        print(f'Exact calendar cell not found for {date_value}')
    except Exception as e:
        print(f'Error selecting calendar date {date_value}: {e}')

    # Fallback: match the visible day number inside the calendar table.
    day_text = str(target_date.day)
    try:
        fallback_locator = popup.locator(
            f'td.dx-calendar-cell:has-text("{day_text}"), td:has-text("{day_text}"), button:has-text("{day_text}"), div:has-text("{day_text}")'
        )
        for i in range(fallback_locator.count()):
            element = fallback_locator.nth(i)
            if element.is_visible():
                if is_holiday(element):
                    print_info(f'Day {target_date.date()} (fallback) is marked as a festivity or vacation. Skipping.')
                    return False
                element.click(force=True)
                popup.wait_for_timeout(800)
                print(f'Clicked fallback calendar day {day_text}')
                return True
    except Exception as e:
        print(f'Fallback calendar selection failed for day {day_text}: {e}')

    return False


def inspect_day_entries(popup) -> dict[str, bool]:
    """Inspect the selected day's request entries for entrada and salida."""
    popup.wait_for_timeout(800)
    try:
        result = popup.evaluate(
            '''() => {
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
            }''',
        )
        print('Day entry inspection:', result)
        return {'entrada': bool(result.get('entrada')), 'salida': bool(result.get('salida'))}
    except Exception as e:
        print(f'Error inspecting day entries: {e}')
        return {'entrada': False, 'salida': False}


def click_add_request_button(popup) -> bool:
    """Click the add request button if the selected day needs a new entrada request."""
    popup.wait_for_timeout(500)
    try:
        button = popup.locator('#btnActionMenuPopover, div[data-bind*="newRequest"], div.actionButton.fixedButton')
        if button.count() > 0:
            print('Found add request button locator count:', button.count())
            if button.first.is_visible():
                try:
                    button.first.click(force=True)
                    print('Clicked add request button via locator')
                except Exception as e:
                    print(f'Locator click failed, falling back to JS click: {e}')
                    popup.evaluate('document.querySelector("#btnActionMenuPopover")?.click()')
            else:
                print('Button locator found but not visible; trying JS click')
                popup.evaluate('document.querySelector("#btnActionMenuPopover")?.click()')

            popup.wait_for_timeout(1000)
            if wait_for_add_request_form(popup):
                print('Add request form opened successfully')
                return True
            print('Add request form did not appear after clicking button')
        else:
            print('Add request button locator count is zero')
    except Exception as e:
        print(f'Error clicking add request button: {e}')

    print('Add request button was not found or not visible')
    return False


def wait_for_add_request_form(popup, timeout: int = 5000) -> bool:
    """Wait for the add-request form to appear after clicking the plus button."""
    try:
        popup.wait_for_selector('div.dx-fieldset', timeout=timeout)
        return True
    except Exception:
        try:
            return popup.locator('div.dx-fieldset').count() > 0
        except Exception:
            return False


def select_date_for_request(popup, month, day) -> None:
    """Select June 15, inspect entries, and create an entrada request if needed."""
    print('Starting date selection and request check...')
    popup.wait_for_timeout(500)

    today = datetime.now()
    year = today.year if today.month > 6 or (today.month == 6 and today.day >= 15) else today.year - 1
    target_date = datetime(year, month, day)
    date_str = target_date.strftime('%d/%m/%Y')

    _ = check_entry_for_date(popup, date_str)
    popup.wait_for_timeout(800)


def submit_time_request(popup, request_type: str, time_value: str, target_date: datetime | None = None) -> None:
    """Submit a time request (enter or exit).
    
    Args:
        popup: The Playwright page object
        request_type: 'entrada' (enter) or 'salida' (exit)
        time_value: Time in 'HH:MM' format
        target_date: Optional datetime of the target day
    """
    
    request_status = inspect_day_entries(popup)
    print(f'Entry status for {time_value}: {request_status}')

    if request_status['entrada'] and request_type == 'entrada':
        print('Entrada already exists; no add request button click needed')
        return
    
    if request_status['salida'] and request_type == 'salida':
        print('Salida already exists; no add request button click needed')
        return

    print('No request found for the selected day; clicking add request button')
    
    if not click_add_request_button(popup):
        print('Unable to click add request button to create entrada request')
    else:
        print('Add request flow started')
    
    print(f'\nSubmitting {request_type} request at {time_value}')
    popup.wait_for_timeout(500)

    # Select the request type via menu or button
    request_selector_text = {
        'entrada': ['entrada', 'fichar entrada', 'registro entrada'],
        'salida': ['salida', 'fichar salida', 'registro salida'],
    }
    selected = False
    for option in request_selector_text.get(request_type, []):
        try:
            locator = popup.locator(f'text="{option}"', has_text=True)
            if locator.count() > 0:
                locator.first.click()
                print(f'Selected {request_type} via text: {option}')
                selected = True
                popup.wait_for_timeout(500)
                break
        except PlaywrightTimeoutError:
            pass

    if not selected:
        print(f'No explicit {request_type} selector found, trying DX select value instead...')
        option_name = 'Entrada' if request_type == 'entrada' else 'Salida'
        if select_dx_dropdown_option_by_label(popup, 'Sentido', option_name):
            selected = True
        else:
            print(f'Could not select {option_name} in Sentido')

    if not selected:
        print(f'Failed to select request type {request_type}. Aborting submit.')
        return

    # Set work mode: Wednesdays are Presencial, otherwise Teletrabajo
    work_mode = 'Teletrabajo'
    if target_date and target_date.weekday() == 2:  # Wednesday
        work_mode = 'Presencial'

    if select_dx_dropdown_option_by_label(popup, '¿Desde dónde trabajaste?', work_mode):
        print(f'Selected {work_mode} work mode')
    else:
        print(f'Could not select {work_mode} work mode')

    # Set the date and time
    if set_datetime_picker_time(popup, time_value):
        print(f'Datetime set to {time_value}')
    else:
        print(f'Could not set datetime to {time_value}')

    # Find and click submit button
    try:
        submit_buttons = popup.query_selector_all('button, div[role="button"], input[type="submit"]')
        for btn in submit_buttons:
            btn_text = (btn.text_content() or '').strip().lower()
            if any(keyword in btn_text for keyword in ['hecho']):
                print(f'Found submit button: {btn_text}')
                btn.click()
                print(f'Clicked Hecho button')
                popup.wait_for_timeout(1000)
                break

        guardar_selector = 'div[title="Guardar"], div[aria-label="save"], div[data-bind*="btnSave"]'
        guardar_locator = popup.locator(guardar_selector)
        if guardar_locator.count() > 0:
            guardar_locator.first.click()
            print(f'{request_type} request submitted (clicked Guardar)')
            popup.wait_for_timeout(1000)
            return
    except Exception as e:
        print(f'Error clicking submit: {e}')

    print(f'Submit button for {request_type} not found')


def main() -> None:
    client = read_secret('VTPORTAL_CLIENT', 'VT Portal client code / name')
    username = read_secret('VTPORTAL_USER', 'VT Portal username')
    password = read_secret('VTPORTAL_PASSWORD', 'VT Portal password')
    language = os.getenv('VTPORTAL_LANGUAGE', 'ESP')
    headless = os.getenv('HEADLESS', 'false').lower() not in ('0', 'false', 'no')
    month = 4
    day= 9

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto('https://vtportal.visualtime.net/', wait_until='networkidle')
        print('Opened vtportal.visualtime.net')

        with page.expect_popup() as popup_info:
            page.click('#btOpen')

        popup = popup_info.value
        
        # Login
        login(popup, client, username, password, language)
        
        print('Page title:', popup.title())
        print('Page URL:', popup.url)
        
        # Ask user for a period (YYYY-MM-DD) or leave blank to use single date
        period_input = input('Enter start date (YYYY-MM-DD) for a period, or leave blank to use single date: ').strip()
        if period_input:
            end_input = input('Enter end date (YYYY-MM-DD): ').strip()
            try:
                start_date = datetime.fromisoformat(period_input)
                end_date = datetime.fromisoformat(end_input)
            except Exception:
                # Try alternative formats DD/MM/YYYY
                try:
                    start_date = datetime.strptime(period_input, '%d/%m/%Y')
                    end_date = datetime.strptime(end_input, '%d/%m/%Y')
                except Exception as e:
                    print_info('Could not parse provided dates:', e)
                    browser.close()
                    return

            print_info(f'\nProcessing period {start_date.date()} -> {end_date.date()}')
            process_period(popup, start_date, end_date)
        else:
            # Get time range based on current date
            enter_time, exit_time = get_time_range()
            
            # Submit entrada (enter) request for single date
            try:
                target_date = datetime(datetime.now().year, month, day)
            except Exception:
                target_date = datetime.now()

            print_info(f'\nProcessing {target_date.date()} - Entry: {enter_time}, Exit: {exit_time}')

            navigate_to_gestion_horaria(popup)
            if select_calendar_day(popup, target_date):
                click_detalles_de_fichajes(popup)
                submit_time_request(popup, 'entrada', enter_time, target_date)
                
                # Go back to Gestion Horaria for exit request
                print_info('\nReturning to Gestion Horaria for exit request...')
                try:
                    navigate_to_gestion_horaria(popup)
                except Exception:
                    pass
                
                if select_calendar_day(popup, target_date):
                    click_detalles_de_fichajes(popup)
                    submit_time_request(popup, 'salida', exit_time, target_date)
                else:
                    print_info(f'Could not select {target_date.date()} for salida')
            else:
                print_info(f'Skipped or could not select {target_date.date()} for entrada')
        
        print_info('\n✓ Time requests submitted successfully')
        
        input('Press Enter to close the browser...')
        browser.close()



if __name__ == '__main__':
    main()
