from __future__ import annotations


RADIOLOGY_CODES = frozenset(str(code) for code in range(70000, 80000))


def basic_radiology_classification(code: str) -> dict[str, str | None]:
    if code not in RADIOLOGY_CODES:
        return {}
    return {
        "service_line": "radiology",
        "service_category": None,
        "service_subcategory": None,
        "unit_basis": None,
        "modality": None,
        "body_region": None,
        "with_contrast": None,
        "aba_delivery_mode": None,
        "aba_provider_role": None,
    }

