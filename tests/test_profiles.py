import pytest
from src.profiles.loader import load_profile, load_all_profiles

def test_load_software_profile():
    profile = load_profile("software_data")
    assert profile.tenant_id == "hamza-solutions"
    assert len(profile.catalog) >= 2
    assert "Python" in profile.catalog[0].technical_keywords
    assert "toner" in profile.negative_constraints.keywords

def test_load_cctv_profile():
    profile = load_profile("cctv_security")
    assert profile.tenant_id == "cctv-security-morocco"
    assert len(profile.catalog) >= 3
    assert "HIKVISION" in profile.catalog[0].synonyms_fr
    assert "gardiennage" in profile.negative_constraints.keywords

def test_load_all_profiles():
    all_profiles = load_all_profiles()
    assert len(all_profiles) >= 2

