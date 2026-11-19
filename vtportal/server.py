"""FastMCP server definition for VisualTime Portal."""

import json
from datetime import datetime
from mcp.server import MCPServer
from vtportal.browser import (
    VTPortalClient,
    get_default_work_mode,
    get_time_range,
    parse_target_date,
)
from vtportal.config import PortalConfig, logger

mcp = MCPServer(
    "vtportal",
    instructions="VisualTime Portal MCP Server - Manage work clock-ins (fichajes), check status, and automate time requests.",
)

_client_instance: VTPortalClient | None = None


def get_client() -> VTPortalClient:
    """Return the shared singleton VTPortalClient instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = VTPortalClient()
    return _client_instance


@mcp.tool()
async def check_day_status(date: str | None = None) -> str:
    """Check clock-in and clock-out status (fichajes) for a given date.
    
    Args:
        date: The date to check in YYYY-MM-DD or DD/MM/YYYY format. Leave empty or pass 'today' for the current date.
        
    Returns:
        JSON string containing whether entrada/salida are registered, existing entry details,
        weekend/holiday status, and company schedule expectations.
    """
    try:
        client = get_client()
        res = await client.check_day_status(date)
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("check_day_status error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
async def clock_in_out(
    request_type: str,
    date: str | None = None,
    time: str | None = None,
    work_mode: str | None = None,
    force: bool = False,
    jitter_minutes: int = 0,
) -> str:
    """Submit a single time request (clock-in 'entrada' or clock-out 'salida').
    
    Args:
        request_type: Either 'entrada' (clock-in) or 'salida' (clock-out).
        date: Target date in YYYY-MM-DD or DD/MM/YYYY format (defaults to today).
        time: Time in HH:MM format (e.g. '08:30', '15:00', '18:00'). If omitted, automatically uses company default rules.
        work_mode: Work mode: 'Teletrabajo' or 'Presencial'. If omitted, defaults to 'Presencial' on Wednesdays and 'Teletrabajo' on other days.
        force: If False (default), skips submission if an entry of that type already exists.
        jitter_minutes: Random minute variation to add to time (e.g. 3 introduces +/- 3 min).
        
    Returns:
        JSON string with result status and submission details.
    """
    try:
        client = get_client()
        res = await client.clock_in_out(
            request_type=request_type,
            date_val=date,
            time_value=time,
            work_mode=work_mode,
            force=force,
            jitter_minutes=jitter_minutes,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("clock_in_out error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
async def fill_day(
    date: str | None = None,
    work_mode: str | None = None,
    enter_time: str | None = None,
    exit_time: str | None = None,
    skip_if_holiday: bool = True,
    jitter_minutes: int = 0,
) -> str:
    """Automatically ensure both entrada and salida are registered for a specific day.
    
    Existing entries will not be duplicated. Weekends and holidays/vacations are skipped by default.
    
    Args:
        date: Target date in YYYY-MM-DD or DD/MM/YYYY format (defaults to today).
        work_mode: 'Teletrabajo' or 'Presencial'. If omitted, uses default (Presencial on Wed, Teletrabajo otherwise).
        enter_time: Clock-in time HH:MM (e.g. '08:30'). If omitted, uses company standard.
        exit_time: Clock-out time HH:MM (e.g. '18:00' or '15:00' on Fri). If omitted, uses company standard.
        skip_if_holiday: Whether to check calendar and skip if marked as holiday/vacation (default True).
        jitter_minutes: Random minute variation to add to standard times (e.g. 5 introduces +/- 5 min).
        
    Returns:
        JSON string with result status for both entrada and salida.
    """
    try:
        client = get_client()
        res = await client.fill_day(
            date_val=date,
            work_mode=work_mode,
            enter_time=enter_time,
            exit_time=exit_time,
            skip_if_holiday=skip_if_holiday,
            jitter_minutes=jitter_minutes,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("fill_day error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
async def process_period(
    start_date: str,
    end_date: str,
    skip_weekends: bool = True,
    skip_holidays: bool = True,
    work_mode: str | None = None,
    jitter_minutes: int = 0,
) -> str:
    """Automatically fill missing clock-in and clock-out entries for a range of dates.
    
    Iterates every day between start_date and end_date (inclusive), skips weekends and holidays,
    and submits missing entrada and salida requests according to schedule rules.
    
    Args:
        start_date: Start date in YYYY-MM-DD or DD/MM/YYYY format.
        end_date: End date in YYYY-MM-DD or DD/MM/YYYY format.
        skip_weekends: Whether to skip Saturday and Sunday (default True).
        skip_holidays: Whether to skip days marked as holiday/vacation in calendar (default True).
        work_mode: Optional override for work mode ('Teletrabajo' or 'Presencial').
        jitter_minutes: Random minute variation to add to standard times (e.g. 5 introduces +/- 5 min).
        
    Returns:
        JSON string summarizing each processed day and overall status.
    """
    try:
        client = get_client()
        res = await client.process_period(
            start_date_val=start_date,
            end_date_val=end_date,
            skip_weekends=skip_weekends,
            skip_holidays=skip_holidays,
            work_mode=work_mode,
            jitter_minutes=jitter_minutes,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("process_period error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
async def process_dates(
    dates: list[str],
    skip_weekends: bool = True,
    skip_holidays: bool = True,
    work_mode: str | None = None,
    enter_time: str | None = None,
    exit_time: str | None = None,
    jitter_minutes: int = 0,
) -> str:
    """Automatically fill missing clock-in and clock-out entries for a specific list of dates.
    
    Iterates each date in the provided list, skips weekends/holidays if requested,
    and submits missing entrada and salida requests according to schedule rules.
    
    Args:
        dates: List of target dates in YYYY-MM-DD or DD/MM/YYYY format.
        skip_weekends: Whether to skip Saturday and Sunday (default True).
        skip_holidays: Whether to skip days marked as holiday/vacation in calendar (default True).
        work_mode: Optional override for work mode ('Teletrabajo' or 'Presencial').
        enter_time: Clock-in time HH:MM (e.g. '08:30'). If omitted, uses company standard.
        exit_time: Clock-out time HH:MM (e.g. '18:00' or '15:00' on Fri). If omitted, uses company standard.
        jitter_minutes: Random minute variation to add to standard times (e.g. 5 introduces +/- 5 min).
        
    Returns:
        JSON string summarizing each processed day and overall status.
    """
    try:
        client = get_client()
        res = await client.process_dates(
            dates=dates,
            skip_weekends=skip_weekends,
            skip_holidays=skip_holidays,
            work_mode=work_mode,
            enter_time=enter_time,
            exit_time=exit_time,
            jitter_minutes=jitter_minutes,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("process_dates error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
async def find_missing_dates(
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Scan the calendar to identify all working days missing an entrada or salida.
    
    Args:
        start_date: Start date YYYY-MM-DD or DD/MM/YYYY (defaults to 1st day of current month).
        end_date: End date YYYY-MM-DD or DD/MM/YYYY (defaults to today).
        
    Returns:
        JSON string listing all days missing entrada or salida, days completed, and holidays.
    """
    try:
        client = get_client()
        res = await client.find_missing_dates(
            start_date_val=start_date,
            end_date_val=end_date,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("find_missing_dates error: %s", e)
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def get_schedule_info(date: str | None = None) -> str:
    """Get the expected schedule hours and work mode for a given date without opening a browser.
    
    Args:
        date: Date in YYYY-MM-DD or DD/MM/YYYY format (defaults to today).
        
    Returns:
        JSON string with expected enter_time, exit_time, work_mode, summer schedule flag, and day details.
    """
    try:
        dt = parse_target_date(date)
        enter_time, exit_time = get_time_range(dt)
        work_mode = get_default_work_mode(dt)
        month = dt.month
        day = dt.day
        is_summer = (month == 6 and day >= 16) or (7 <= month <= 8)

        info = {
            "date": dt.strftime("%Y-%m-%d"),
            "day_of_week": dt.strftime("%A"),
            "is_weekend": dt.weekday() >= 5,
            "is_summer_schedule": is_summer,
            "enter_time": enter_time,
            "exit_time": exit_time,
            "work_mode": work_mode,
            "rules": [
                "Summer schedule (June 16 - August 31): 08:00 - 15:00",
                "Regular schedule: 08:30 - 18:00",
                "Fridays: exit is 15:00",
                "Wednesdays: 'Presencial', other weekdays: 'Teletrabajo'",
            ],
        }
        return json.dumps(info, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


def main() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting VTPortal MCP server (transport=stdio)...")
    mcp.run("stdio")


if __name__ == "__main__":
    main()
