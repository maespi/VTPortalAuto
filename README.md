# VisualTime Portal (VTPortal) MCP Server & Automation

An automation engine and **Model Context Protocol (MCP)** server for **VisualTime Portal** (by Robotics / Cegid). It enables AI assistants (such as **Gemini CLI**, **Claude Desktop**, **Cursor**, or **Antigravity**) to inspect work clock-ins (*fichajes*), scan monthly calendars for missing days, and automatically submit time requests adhering to company schedule rules.

---

## 📑 Table of Contents

- [Overview & Architecture](#-overview--architecture)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
- [Configuration (.env)](#-configuration-env)
- [Company Schedule & Calendar Rules](#-company-schedule--calendar-rules)
- [MCP Client Setup](#-mcp-client-setup)
  - [Gemini CLI](#gemini-cli)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
- [MCP Tools Reference](#-mcp-tools-reference)
- [Example AI Prompts](#-example-ai-prompts)
- [Standalone & CLI Usage](#-standalone--cli-usage)
- [Testing](#-testing)
- [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🔭 Overview & Architecture

VisualTime Portal is a web application widely used in Spain and Europe for employee time tracking. This project wraps the portal's UI interactions into a clean, programmatic interface using **Playwright** (running headless Chromium) and exposes standard **Model Context Protocol (MCP)** tools over `stdio`.

```
┌─────────────────────────────────┐
│ AI Assistant (e.g. Gemini CLI)  │
└────────────────┬────────────────┘
                 │ stdio (JSON-RPC / MCP Protocol)
┌────────────────▼────────────────┐
│      vtportal MCP Server        │
│   (vtportal.server / MCPServer) │
└────────────────┬────────────────┘
                 │ Python async
┌────────────────▼────────────────┐
│      VTPortalClient Engine      │
│     (vtportal.browser)          │
└────────────────┬────────────────┘
                 │ Playwright
┌────────────────▼────────────────┐
│      Chromium Headless          │
│   https://vtportal.visualtime...│
└─────────────────────────────────┘
```

---

## 📂 Project Structure

```text
VTPortalAuto/
├── .env.example            # Sample configuration file
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python package dependencies
├── README.md               # Documentation and setup guide
├── auto.py                 # Standalone interactive CLI script
├── tests/
│   └── test_vtportal.py    # Unit tests for schedule and parsing logic
└── vtportal/               # Core Python package
    ├── __init__.py         # Package exports
    ├── __main__.py         # Entry point for 'python -m vtportal'
    ├── config.py           # Configuration management and logging
    ├── browser.py          # Playwright automation engine and DOM interactions
    └── server.py           # FastMCP server exposing tools
```

---

## 📋 Prerequisites

- **Python**: Version `3.11+` (tested on Python 3.13)
- **VisualTime Portal Credentials**:
  - Client Code (`VTPORTAL_CLIENT`, e.g. `worl7397`)
  - Username (`VTPORTAL_USER`)
  - Password (`VTPORTAL_PASSWORD`)
- **Git** (for cloning the repository)

---

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/VTPortalAuto.git
cd VTPortalAuto
```

### 2. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright Chromium

Download the headless browser binary required by Playwright:

```bash
playwright install chromium
```

---

## ⚙️ Configuration (.env)

Copy `.env.example` to create your local `.env` file:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

Open `.env` and fill in your credentials and preferences:

```env
# VisualTime Portal Credentials
VTPORTAL_CLIENT=your_company_client_code
VTPORTAL_USER=your_username
VTPORTAL_PASSWORD=your_password
VTPORTAL_LANGUAGE=ESP

# Automation Settings
HEADLESS=true
VTPORTAL_TIMEOUT_MS=30000
```

### Configuration Options

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `VTPORTAL_CLIENT` | **Yes** | — | Company / client identifier used on the login screen. |
| `VTPORTAL_USER` | **Yes** | — | VisualTime username or employee ID. |
| `VTPORTAL_PASSWORD` | **Yes** | — | Password for the portal account. |
| `VTPORTAL_LANGUAGE` | No | `ESP` | UI language (`ESP` for Spanish). |
| `HEADLESS` | No | `true` | Set to `false` to display the Chromium window for debugging. |
| `VTPORTAL_TIMEOUT_MS` | No | `30000` | Browser action timeout in milliseconds. |

---

## 📅 Company Schedule & Calendar Rules

The engine automatically applies the following schedule and holiday rules:

### 1. Working Hours
- **Summer Schedule (June 16 – August 31):**
  - All Weekdays: `08:00` (Entrada) – `15:00` (Salida)
- **Regular Schedule (September 1 – June 15):**
  - Monday – Thursday: `08:30` (Entrada) – `18:00` (Salida)
  - Friday: `08:30` (Entrada) – `15:00` (Salida)

### 2. Work Modes (`¿Desde dónde trabajaste?`)
- **Default Rule:**
  - Wednesdays: `Presencial`
  - Other Weekdays: `Teletrabajo`
- **Custom / Hybrid Override:**
  - When batch filling via `process_period(..., work_mode_map=...)`, any weekday (e.g. Tuesday or Thursday) can be customized to `Presencial`.

### 3. Holidays, Vacations & Weekends
The engine inspects calendar cell background colors and DOM indicators:
- **Public Holidays:** Red cells (`#ff0000`) without presence icons are recognized as public holidays (e.g. *Diada*, *La Mercè*, *Fiesta Nacional*) and automatically skipped.
- **Vacations / Absences:** Bright yellow cells (`#ffff00`) without presence icons are recognized as approved vacation days and skipped.
- **Scheduled Shifts:** Lavender/purple (`#cc99ff`), light blue (`#99ccff`), and cells bearing the `dx-icon-Cal_TC_Presence` icon are correctly identified as active work shifts.
- **Weekends:** Saturdays and Sundays (grey cells `#c0c0c0`) are skipped automatically.

---

## 🤖 MCP Client Setup

### Gemini CLI

Add the server to your user configuration at `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "vtportal": {
      "command": "C:\\Users\\your.username\\Repos\\VTPortalAuto\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "vtportal"
      ],
      "cwd": "C:\\Users\\your.username\\Repos\\VTPortalAuto"
    }
  }
}
```

*(On macOS/Linux, adjust the python path to `<path-to-repo>/.venv/bin/python`)*.

> **Tip:** If you modify Python code while Gemini CLI is running, execute `/mcp reload` in the CLI prompt to reload the MCP server process.

### Claude Desktop

Add the server configuration to your `claude_desktop_config.json`:

* **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
* **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vtportal": {
      "command": "C:\\Users\\your.username\\Repos\\VTPortalAuto\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "vtportal"
      ],
      "cwd": "C:\\Users\\your.username\\Repos\\VTPortalAuto"
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your workspace or global settings:

```json
{
  "mcpServers": {
    "vtportal": {
      "command": "C:\\Users\\your.username\\Repos\\VTPortalAuto\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "vtportal"
      ],
      "cwd": "C:\\Users\\your.username\\Repos\\VTPortalAuto"
    }
  }
}
```

---

## 🛠️ MCP Tools Reference

The server registers 6 tools accessible by AI models:

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `check_day_status` | `date` (optional) | Returns clock-in status, entry details, holiday status, and expected schedule for a single day. |
| `find_missing_dates` | `start_date`, `end_date` | Scans calendar range, returning missing days, completed days, and identified holidays/vacations. |
| `clock_in_out` | `request_type`, `date`, `time`, `work_mode`, `force` | Submits a single `entrada` or `salida`. Uses company defaults if time/mode are omitted. |
| `fill_day` | `date`, `work_mode`, `enter_time`, `exit_time`, `skip_if_holiday` | Automatically ensures both `entrada` and `salida` are registered for a day. |
| `process_period` | `start_date`, `end_date`, `skip_weekends`, `skip_holidays`, `work_mode` | Submits all missing entries across a date range in a single browser session. |
| `get_schedule_info` | `date` (optional) | Fast offline lookup of expected hours, summer schedule status, and work mode without launching a browser. |

### Tool Details & Examples

#### 1. `check_day_status(date)`
```json
// Example Output
{
  "date": "2026-09-02",
  "day_of_week": "Wednesday",
  "is_weekend": false,
  "is_holiday_or_vacation": false,
  "has_entrada": true,
  "has_salida": true,
  "entries": [
    { "text": "2 de septiembre de 2026 8:30", "icon": "listMenuItemIcon dx-icon-TA_in" },
    { "text": "2 de septiembre de 2026 18:00", "icon": "listMenuItemIcon dx-icon-TA_out" }
  ],
  "expected_schedule": {
    "enter_time": "08:30",
    "exit_time": "18:00",
    "default_work_mode": "Presencial"
  },
  "status": "ok"
}
```

#### 2. `find_missing_dates(start_date, end_date)`
```json
// Example Output
{
  "start_date": "2026-09-01",
  "end_date": "2026-09-30",
  "missing_days_count": 0,
  "missing_days": [],
  "completed_days_count": 20,
  "holidays": [
    { "date": "2026-09-11", "day": "Friday" },
    { "date": "2026-09-24", "day": "Thursday" }
  ]
}
```

---

## 💬 Example AI Prompts

Once configured with an MCP client, you can control the portal with natural language:

- **Check status today:**
  > *"Check if I have clocked in today using the vtportal tool."*
- **Find missing days:**
  > *"Check if I have any missing time entries this month."*
- **Fill specific day:**
  > *"Clock in and out for yesterday as Teletrabajo."*
- **Fill entire period:**
  > *"Fill all missing days of September following the standard schedule. Set Wednesdays and Tuesdays as Presencial."*
- **Inspect offline rules:**
  > *"What are the expected working hours for next Friday?"*

---

## 💻 Standalone & CLI Usage

You can also run the automation without an AI assistant:

### Run MCP Server Directly
```powershell
.\.venv\Scripts\python.exe -m vtportal
```

### Run Interactive CLI Automation
```powershell
.\.venv\Scripts\python.exe auto.py
```

---

## 🧪 Testing

Run the automated test suite using `pytest`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

Tests verify:
- Date string parsing (`YYYY-MM-DD`, `DD/MM/YYYY`, `today`).
- Summer schedule boundaries (June 16 – August 31).
- Regular schedule rules (September 1 start, Friday 15:00 exit).
- Work mode assignments (Wednesday Presencial vs other weekdays Teletrabajo).
- Environment variable validation and error handling.
- FastMCP tool registration.

---

## ❓ Troubleshooting & FAQs

### 1. `TimeoutError` or `Element intercepted pointer events`
- **Cause:** Datepicker popups or overlays remaining in the DOM.
- **Resolution:** The engine uses direct DevExtreme `dxDateBox` widget instance updates and force clicks to prevent overlay collisions. Ensure you are on the latest version of `vtportal/browser.py`.

### 2. Login Fails (`Invalid credentials` or `Login form not submitted`)
- Check `.env` values for `VTPORTAL_CLIENT`, `VTPORTAL_USER`, and `VTPORTAL_PASSWORD`.
- Test with `HEADLESS=false` in `.env` to visually watch the login process and inspect any company MFA prompts.

### 3. Changes in code are not reflected in Gemini CLI
- MCP stdio processes are launched once when the CLI starts and stay active.
- Run `/mcp reload` inside Gemini CLI to reload the server process without restarting the session.

### 4. Playwright Browser Executable Not Found
- Re-run:
  ```powershell
  .\.venv\Scripts\python.exe -m playwright install chromium
  ```

---

## 📄 License

Internal use / Proprietary to your organization. Ensure sensitive credentials are kept strictly inside `.env` (which is excluded by `.gitignore`).
