"""Local project-management dashboard ("control center") for the AI Photo Album project.

Dev tooling only — not part of the photo-album product. Python stdlib only.
Run with ``start_project_manager.bat`` or ``python -m project_management.server``.
"""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
