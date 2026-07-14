"""Smoke tests for the SDD-defined source layout."""

import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

EXPECTED_MODULES = (
    "src.config.settings",
    "src.api.api_client",
    "src.parser.offer_parser",
    "src.matcher.offer_matcher",
    "src.matcher.geo_rules",
    "src.storage.sqlite_store",
    "src.mailer.smtp_mailer",
    "src.mailer.templates",
    "src.loop.poll_loop",
    "src.models.offer",
    "src.logging.logger",
)


def test_plan_source_layout_exists() -> None:
    expected_paths = (
        "config/settings.py",
        "api/api_client.py",
        "parser/offer_parser.py",
        "matcher/offer_matcher.py",
        "matcher/geo_rules.py",
        "storage/sqlite_store.py",
        "mailer/smtp_mailer.py",
        "mailer/templates.py",
        "loop/poll_loop.py",
        "models/offer.py",
        "logging/logger.py",
    )

    assert all((SRC_ROOT / path).is_file() for path in expected_paths)


def test_domain_modules_are_importable() -> None:
    imported_modules = [importlib.import_module(module_name) for module_name in EXPECTED_MODULES]

    assert all(module.__name__.startswith("src.") for module in imported_modules)
