"""Locate data independently of the working directory."""

from pathlib import Path
import os
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]


def user_data_dir():
    """Persistent Windows user data outside the executable and temporary folders."""
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "RetroBeaten"


def get_data_dir():
    """Source runs use the development collection; the EXE uses user data."""
    return user_data_dir() if getattr(sys, "frozen", False) else PROJECT_DIR
