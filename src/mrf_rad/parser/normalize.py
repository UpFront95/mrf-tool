from __future__ import annotations

from typing import Any

from mrf_rad.codes import classify_code, get_profile


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)

def normalize_in_network_item(
    item: dict[str, Any],
    *,
    profile_name: str,
    metadata: dict[str, Any],
    source_file_url: str,
    index_payer: str | None = None,
    provider_references: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    profile = get_profile(profile_name)
    classification = classify_code(profile_name, str(item.get("billing_code", "")))
    if not classification:
        return []

    rows: list[dict[str, Any]] = []
    common = {
        "index_payer": index_payer,
        "payer_name": metadata.get("reporting_entity_name"),
        "reporting_entity_type": metadata.get("reporting_entity_type"),
        "source_file_url": source_file_url,
        "last_updated_on": metadata.get("last_updated_on"),
        "schema_version": metadata.get("version"),
        "billing_code": item.get("billing_code"),
        "billing_code_type": item.get("billing_code_type"),
        "billing_code_type_version": item.get("billing_code_type_version"),
        "name": item.get("name"),
        "description": item.get("description"),
        **classification,
        "negotiation_arrangement": item.get("negotiation_arrangement"),
    }

    for rate in item.get("negotiated_rates", []) or []:
        provider_groups = list(rate.get("provider_groups", []) or [])
        if rate.get("provider_references"):
            if provider_references is None:
                raise NotImplementedError("provider_references are not available")
            for reference_id in rate.get("provider_references", []) or []:
                key = str(reference_id)
                if key not in provider_references:
                    raise ValueError(f"missing provider reference {key}")
                provider_groups.extend(provider_references[key])

        for provider_group in provider_groups:
            tin = provider_group.get("tin") or {}
            provider_npis = [str(npi) for npi in provider_group.get("npi", []) or []]
            provider_common = {
                "provider_npi_list": provider_npis,
                "provider_tin_type": tin.get("type"),
                "provider_tin_value": tin.get("value"),
            }

            for price in rate.get("negotiated_prices", []) or []:
                modifiers = [
                    str(modifier)
                    for modifier in price.get("billing_code_modifier", []) or []
                ]
                negotiated_type = price.get("negotiated_type")
                negotiated_rate = _float_or_none(price.get("negotiated_rate"))
                percentage = negotiated_rate if negotiated_type == "percentage" else None

                rows.append(
                    {
                        **common,
                        "billing_class": price.get("billing_class"),
                        "setting": price.get("setting"),
                        "negotiated_type": negotiated_type,
                        "negotiated_rate": (
                            None if negotiated_type == "percentage" else negotiated_rate
                        ),
                        "percentage": percentage,
                        "expiration_date": price.get("expiration_date"),
                        "service_codes": [
                            str(code) for code in price.get("service_code", []) or []
                        ],
                        "billing_code_modifiers": modifiers,
                        "is_technical_component": "TC" in modifiers,
                        "is_professional_component": "26" in modifiers,
                        "is_global": "TC" not in modifiers and "26" not in modifiers,
                        "is_benchmark_eligible": profile.is_benchmark_eligible(
                            billing_class=price.get("billing_class"),
                            negotiated_type=negotiated_type,
                            negotiated_rate=(
                                None
                                if negotiated_type == "percentage"
                                else negotiated_rate
                            ),
                        ),
                        **provider_common,
                        "additional_information": price.get("additional_information"),
                    }
                )

    return rows
