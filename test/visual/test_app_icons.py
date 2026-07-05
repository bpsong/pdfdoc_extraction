"""Regression checks for shared application icons."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_pages_declare_the_shared_favicon() -> None:
    """Keep the branded favicon on authenticated and login pages."""

    favicon = ROOT / "web/static/favicon.svg"
    favicon_markup = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />'

    assert favicon.is_file()
    assert "<svg" in favicon.read_text(encoding="utf-8")
    assert favicon_markup in (ROOT / "web/templates/app_base.html").read_text(
        encoding="utf-8"
    )
    assert favicon_markup in (ROOT / "web/templates/login.html").read_text(
        encoding="utf-8"
    )


def test_users_navigation_link_has_a_decorative_icon() -> None:
    """Keep the Users link aligned with the other icon-led navigation items."""

    source = (ROOT / "web/templates/app_base.html").read_text(encoding="utf-8")
    users_link = source.split('href="/app/admin/users"', maxsplit=1)[1].split(
        "</a>", maxsplit=1
    )[0]

    assert '<svg class="w-4 h-4 shrink-0"' in users_link
    assert 'aria-hidden="true"' in users_link
    assert "<span>Users</span>" in users_link
