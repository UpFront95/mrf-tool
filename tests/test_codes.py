from __future__ import annotations

import pytest

from mrf_rad.codes import classify_code, get_profile, list_profiles


def test_aba_profile_contains_initial_core_codes_only():
    profile = get_profile("aba")

    assert profile.contains("97151")
    assert profile.contains("97156")
    assert not profile.contains("97157")


def test_aba_classification_has_service_line_fields():
    classification = classify_code("aba", "97156")

    assert classification["service_line"] == "aba"
    assert classification["service_category"] == "Caregiver Guidance"
    assert classification["aba_delivery_mode"] == "family/caregiver"
    assert classification["unit_basis"] == "15 minutes"
    assert classification["modality"] is None


def test_radiology_profile_contains_range_without_aba_codes():
    profile = get_profile("radiology")

    assert profile.contains("70551")
    assert not profile.contains("97151")


def test_unknown_profile_error_lists_options():
    with pytest.raises(ValueError, match="aba, radiology"):
        get_profile("cardiology")


def test_list_profiles_is_stable():
    assert list_profiles() == ["aba", "radiology"]


def test_aba_benchmark_policy_is_conservative():
    profile = get_profile("aba")

    assert profile.is_benchmark_eligible(
        negotiated_type="negotiated",
        negotiated_rate=42.5,
        billing_class="professional",
    )
    assert not profile.is_benchmark_eligible(
        negotiated_type="negotiated",
        negotiated_rate=42.5,
        billing_class="institutional",
    )
    assert not profile.is_benchmark_eligible(
        negotiated_type="percentage",
        negotiated_rate=None,
        billing_class="professional",
    )


def test_radiology_benchmark_policy_is_broader():
    profile = get_profile("radiology")

    assert profile.is_benchmark_eligible(
        negotiated_type="negotiated",
        negotiated_rate=5000,
        billing_class="institutional",
    )
