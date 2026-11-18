"""Unit tests for VTPortal MCP server helpers, config, and tools."""

import os
import pytest
from datetime import datetime
from vtportal.browser import (
    parse_target_date,
    get_time_range,
    get_default_work_mode,
)
from vtportal.config import PortalConfig
from vtportal.server import mcp, get_schedule_info


def test_parse_target_date():
    assert parse_target_date("2026-05-12") == datetime(2026, 5, 12)
    assert parse_target_date("12/05/2026") == datetime(2026, 5, 12)
    assert parse_target_date("2026/05/12") == datetime(2026, 5, 12)

    today = parse_target_date("today")
    assert today.date() == datetime.now().date()

    with pytest.raises(ValueError):
        parse_target_date("invalid-date-format")


def test_get_time_range():
    # Summer: July 10 (Wednesday)
    dt_summer = datetime(2026, 7, 10)
    enter, exit_ = get_time_range(dt_summer)
    assert enter == "08:00"
    assert exit_ == "15:00"

    # September 1 (Tuesday) -> Regular schedule starts
    dt_sep1 = datetime(2026, 9, 1)
    enter_sep1, exit_sep1 = get_time_range(dt_sep1)
    assert enter_sep1 == "08:30"
    assert exit_sep1 == "18:00"

    # Winter / Regular: Nov 17 (Tuesday)
    dt_winter_tue = datetime(2026, 11, 17)
    enter, exit_ = get_time_range(dt_winter_tue)
    assert enter == "08:30"
    assert exit_ == "18:00"

    # Regular Friday: Nov 20 (Friday)
    dt_winter_fri = datetime(2026, 11, 20)
    enter, exit_ = get_time_range(dt_winter_fri)
    assert enter == "08:30"
    assert exit_ == "15:00"


def test_get_default_work_mode():
    # Wednesday -> Presencial
    wed = datetime(2026, 11, 18)
    assert wed.weekday() == 2
    assert get_default_work_mode(wed) == "Presencial"

    # Tuesday -> Teletrabajo
    tue = datetime(2026, 11, 17)
    assert tue.weekday() == 1
    assert get_default_work_mode(tue) == "Teletrabajo"


def test_portal_config_validation(monkeypatch):
    monkeypatch.delenv("VTPORTAL_CLIENT", raising=False)
    monkeypatch.delenv("VTPORTAL_USER", raising=False)
    monkeypatch.delenv("VTPORTAL_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="Missing required VTPortal credentials"):
        PortalConfig.from_env()

    monkeypatch.setenv("VTPORTAL_CLIENT", "myclient")
    monkeypatch.setenv("VTPORTAL_USER", "myuser")
    monkeypatch.setenv("VTPORTAL_PASSWORD", "mypass")
    monkeypatch.setenv("HEADLESS", "false")

    cfg = PortalConfig.from_env()
    assert cfg.client == "myclient"
    assert cfg.username == "myuser"
    assert cfg.password == "mypass"
    assert cfg.headless is False


def test_mcp_server_tools_registered():
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    tool_names = [tool.name for tool in tools]
    assert "check_day_status" in tool_names
    assert "clock_in_out" in tool_names
    assert "fill_day" in tool_names
    assert "process_period" in tool_names
    assert "find_missing_dates" in tool_names
    assert "get_schedule_info" in tool_names


def test_get_schedule_info_tool():
    res_str = get_schedule_info("2026-11-18")  # Wednesday
    assert "Presencial" in res_str
    assert "08:30" in res_str
    assert "18:00" in res_str
