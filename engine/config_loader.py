"""
engine/config_loader.py

Small shared helper so every engine module reads location and other
settings from config/settings.yaml instead of hardcoding them.
"""

import os
import yaml


def load_settings() -> dict:
    """
    Load config/settings.yaml (relative to this file's location, so
    it works no matter which folder you run a script from).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "..", "config", "settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_location():
    """Convenience helper: returns (latitude, longitude) from settings.yaml."""
    settings = load_settings()
    loc = settings["location"]
    return loc["latitude"], loc["longitude"]


def load_page_layout() -> dict:
    """
    Load config/page_layout.yaml (relative to this file's location).
    Returns a dict like {"page_home": [...], "page_panchang_left": [...], ...},
    each a list of {"key", "heading", "detail_lines"} dicts, in display order.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    layout_path = os.path.join(script_dir, "..", "config", "page_layout.yaml")
    with open(layout_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
