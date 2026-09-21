from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def test_all_presentation_templates_compile():
    root = Path("app/templates")
    environment = Environment(loader=FileSystemLoader(root))
    for path in root.glob("*.html"):
        environment.get_template(path.name)


def test_static_assets_are_bundled_locally():
    assets = list(Path("app/static").rglob("*.css")) + list(Path("app/static").rglob("*.js"))
    assert assets
    assert all(path.stat().st_size > 0 for path in assets)
    assert not any("https://" in path.read_text(encoding="utf-8") for path in assets)
