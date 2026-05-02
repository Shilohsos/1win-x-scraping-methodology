# CloakBrowser Setup Guide

## Installation
```bash
python3 -m venv ~/cloakbrowser-venv
source ~/cloakbrowser-venv/bin/activate
pip install --upgrade pip
pip install cloakbrowser
cloakbrowser install
```

## Verification
```bash
python -c "from cloakbrowser import launch; print('OK')"
```

## Usage
```python
from cloakbrowser import launch

# Basic headless
browser = launch(headless=True)

# With stealth + proxy
browser = launch(
    headless=True,
    stealth_args=True,
    humanize=True,
    proxy="http://user:pass@host:port"
)
page = browser.new_page()
page.set_default_timeout(60000)
```

## Storage
| Component | Location | Size |
|-----------|----------|------|
| Binary | `~/.cloakbrowser/chromium-*/chrome` | ~697 MB |
| Venv | `~/cloakbrowser-venv/` | ~173 MB |

## Stealth Features
- `stealth_args=True` — hides webdriver flags, spoofs WebGL
- `humanize=True` — adds realistic delays, simulates human interaction
- Passes 30/30 detection tests per CloakBrowser README
