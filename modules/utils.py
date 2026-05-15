import json
import os

DEFAULT_CONFIG = {
    "window": {"width": 1200, "height": 700, "x": 100, "y": 100},
    "default_directory": "",
    "last_opened_file": "",
    "column_widths": [],
    "column_order": [],
    "sort_column": -1,
    "sort_order": 0,
    "saved_filters": [],
}


def get_config_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config", "config.json")


def load_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(saved)
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def validate_netscape_cookie(cookie):
    errors = []
    expiry = cookie.get("expiry", "")
    if expiry:
        try:
            int(expiry)
        except ValueError:
            errors.append(f"expiry '{expiry}' must be a Unix timestamp integer")

    for field in ("flag", "secure"):
        val = cookie.get(field, "").upper()
        if val and val not in ("TRUE", "FALSE"):
            errors.append(f"{field} '{val}' must be TRUE or FALSE")

    return errors


def validate_cookies_for_format(cookies, fmt):
    errors = []
    if fmt == "netscape":
        for i, c in enumerate(cookies):
            for e in validate_netscape_cookie(c):
                errors.append(f"Row {i + 1}: {e}")
    elif fmt == "header":
        for i, c in enumerate(cookies):
            if not c.get("name", "").strip():
                errors.append(f"Row {i + 1}: name cannot be empty in header format")
    return errors
