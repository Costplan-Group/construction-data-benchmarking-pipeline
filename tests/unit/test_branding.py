"""Unit tests for BrandProfile (report branding)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.reporting.branding import (
    BrandProfile,
    _coerce_legacy_footer,
    _merged_defaults,
    clear_brand_profile_cache,
    get_brand_profile,
)


def test_accent_colour_normalization():
    assert BrandProfile(accent_colour="ff00aa").accent_colour == "#ff00aa"
    assert BrandProfile(accent_colour="#abc").accent_colour == "#abc"
    assert BrandProfile(accent_colour="").accent_colour == "#32c3e2"


def test_pdf_footer_left_lines():
    brand = BrandProfile(company_name="Acme", registration_number="CN 1")
    assert brand.pdf_footer_left_lines() == ["Acme", "CN 1"]
    assert BrandProfile(company_name="  ", registration_number="").pdf_footer_left_lines() == []


def test_resolved_logo_path_missing_and_existing(tmp_path: Path):
    missing = BrandProfile(logo_path=str(tmp_path / "nope.png"))
    assert missing.resolved_logo_path() is None

    logo = tmp_path / "logo.png"
    logo.write_bytes(b"x")
    found = BrandProfile(logo_path=str(logo))
    assert found.resolved_logo_path() == logo


def test_coerce_legacy_footer_pipe_and_list():
    pipe = _coerce_legacy_footer({"legal_footer_lines": "Acme | CN 99"})
    assert pipe["company_name"] == "Acme"
    assert pipe["registration_number"] == "CN 99"

    listed = _coerce_legacy_footer({"legal_footer_lines": ["Beta", "CN 2"]})
    assert listed["company_name"] == "Beta"
    assert listed["registration_number"] == "CN 2"


def test_merged_defaults_ignores_blank_overrides():
    merged = _merged_defaults({"company_name": "  ", "website": "acme.test"})
    assert merged["company_name"] == "Your Company Name"
    assert merged["website"] == "acme.test"


def test_get_brand_profile_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    clear_brand_profile_cache()
    monkeypatch.setattr(
        "backend.app.reporting.branding.BRANDING_YAML",
        tmp_path / "missing-branding.yaml",
    )
    monkeypatch.setenv("BRAND_COMPANY_NAME", "Env Co")
    monkeypatch.setenv("BRAND_WEBSITE", "env.example")
    monkeypatch.setenv("BRAND_ACCENT_COLOUR", "112233")
    clear_brand_profile_cache()
    try:
        profile = get_brand_profile()
        assert profile.company_name == "Env Co"
        assert profile.website == "env.example"
        assert profile.accent_colour == "#112233"
    finally:
        clear_brand_profile_cache()
