from __future__ import annotations

from dataclasses import dataclass


ABA_CODES = frozenset(str(code) for code in range(97151, 97157))


@dataclass(frozen=True)
class AbaClassification:
    service_category: str
    service_subcategory: str
    unit_basis: str
    aba_delivery_mode: str
    aba_provider_role: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "service_line": "aba",
            "service_category": self.service_category,
            "service_subcategory": self.service_subcategory,
            "unit_basis": self.unit_basis,
            "modality": None,
            "body_region": None,
            "with_contrast": None,
            "aba_delivery_mode": self.aba_delivery_mode,
            "aba_provider_role": self.aba_provider_role,
        }


ABA_CLASSIFICATIONS: dict[str, AbaClassification] = {
    "97151": AbaClassification(
        "Assessment",
        "behavior_identification",
        "15 minutes",
        "individual",
        "qualified_professional",
    ),
    "97152": AbaClassification(
        "Assessment",
        "supporting_assessment",
        "15 minutes",
        "individual",
        "technician",
    ),
    "97153": AbaClassification(
        "Direct Treatment",
        "protocol_treatment",
        "15 minutes",
        "individual",
        "technician",
    ),
    "97154": AbaClassification(
        "Direct Treatment",
        "group_protocol_treatment",
        "15 minutes",
        "group",
        "technician",
    ),
    "97155": AbaClassification(
        "Supervision/Protocol Modification",
        "protocol_modification",
        "15 minutes",
        "individual",
        "mixed_or_supervisory",
    ),
    "97156": AbaClassification(
        "Caregiver Guidance",
        "family_caregiver_guidance",
        "15 minutes",
        "family/caregiver",
        "qualified_professional",
    ),
}

