"""Static dashboard typography regressions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = (ROOT / "web" / "src" / "index.css").read_text()
THEME_PRESETS = (ROOT / "web" / "src" / "themes" / "presets.ts").read_text()
WEB_SERVER = (ROOT / "hermes_cli" / "web_server.py").read_text()


def test_default_dashboard_theme_uses_hermes_webui_geist_stack():
    """The clean dashboard UI should inherit the modern Hermes WebUI font."""
    assert '--theme-font-sans: "Geist", "Geist Sans"' in INDEX_CSS
    assert 'const HERMES_WEBUI_SANS =\n  `"Geist", "Geist Sans"' in THEME_PRESETS
    assert 'fontSans: HERMES_WEBUI_SANS' in THEME_PRESETS
    assert "family=Geist:wght@400;500;600;700" in THEME_PRESETS
    assert '"fontSans": \'"Geist", "Geist Sans"' in WEB_SERVER


def test_nous_display_font_utilities_resolve_to_theme_font():
    """Explicit legacy display utility classes should not bypass the theme font."""
    assert "--font-sans: var(--theme-font-sans);" in INDEX_CSS
    assert "--font-rules-expanded: var(--theme-font-sans);" in INDEX_CSS
    assert "--font-mondwest: var(--theme-font-sans);" in INDEX_CSS
    assert ".font-mondwest," in INDEX_CSS
    assert ".font-expanded," in INDEX_CSS
    assert ".font-compressed," in INDEX_CSS
    assert ".font-courier {" in INDEX_CSS
    assert "font-family: var(--theme-font-sans);" in INDEX_CSS
