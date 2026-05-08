from __future__ import annotations

from dataclasses import dataclass

from mrf_rad.codes.aba import ABA_CLASSIFICATIONS, ABA_CODES
from mrf_rad.codes.radiology import RADIOLOGY_CODES, basic_radiology_classification


@dataclass(frozen=True)
class BenchmarkPolicy:
    max_rate: float | None = None
    allowed_billing_classes: frozenset[str] | None = None
    allow_percentage: bool = False

    def is_eligible(
        self,
        *,
        negotiated_type: str | None,
        negotiated_rate: float | None,
        billing_class: str | None,
    ) -> bool:
        if negotiated_rate is None:
            return False
        if not self.allow_percentage and negotiated_type == "percentage":
            return False
        if (
            self.allowed_billing_classes is not None
            and billing_class not in self.allowed_billing_classes
        ):
            return False
        if self.max_rate is not None and negotiated_rate > self.max_rate:
            return False
        return True


@dataclass(frozen=True)
class CodeProfile:
    name: str
    codes: frozenset[str]
    benchmark_policy: BenchmarkPolicy

    def contains(self, code: str) -> bool:
        return code in self.codes

    def is_benchmark_eligible(
        self,
        *,
        negotiated_type: str | None,
        negotiated_rate: float | None,
        billing_class: str | None,
    ) -> bool:
        return self.benchmark_policy.is_eligible(
            negotiated_type=negotiated_type,
            negotiated_rate=negotiated_rate,
            billing_class=billing_class,
        )


PROFILES: dict[str, CodeProfile] = {
    "aba": CodeProfile(
        "aba",
        ABA_CODES,
        benchmark_policy=BenchmarkPolicy(
            max_rate=1_000,
            allowed_billing_classes=frozenset({"professional"}),
            allow_percentage=False,
        ),
    ),
    "radiology": CodeProfile(
        "radiology",
        RADIOLOGY_CODES,
        benchmark_policy=BenchmarkPolicy(
            max_rate=100_000,
            allowed_billing_classes=None,
            allow_percentage=False,
        ),
    ),
}


def list_profiles() -> list[str]:
    return sorted(PROFILES)


def get_profile(name: str) -> CodeProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        options = ", ".join(list_profiles())
        raise ValueError(f"unknown code profile {name!r}; expected one of: {options}") from exc


def classify_code(profile_name: str, code: str) -> dict[str, str | None]:
    profile = get_profile(profile_name)
    if not profile.contains(code):
        return {}

    if profile_name == "aba":
        return ABA_CLASSIFICATIONS[code].to_dict()
    if profile_name == "radiology":
        return basic_radiology_classification(code)
    return {}
