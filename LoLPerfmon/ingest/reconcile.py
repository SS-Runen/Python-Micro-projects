from __future__ import annotations

from typing import Any

from LoLPerfmon.sim.models import DiscrepancyRecord


def compute_discrepancies(
    canonical: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    *,
    source_name: str,
) -> list[DiscrepancyRecord]:
    out: list[DiscrepancyRecord] = []
    all_ids = set(canonical) | set(candidate)
    for eid in sorted(all_ids):
        if eid not in canonical:
            out.append(
                DiscrepancyRecord(
                    entity_type="item",
                    entity_id=eid,
                    field_path="",
                    canonical_value=None,
                    candidate_value=candidate.get(eid),
                    source_name=source_name,
                    delta_kind="missing",
                    severity="medium",
                    resolution_status="open",
                )
            )
            continue
        if eid not in candidate:
            out.append(
                DiscrepancyRecord(
                    entity_type="item",
                    entity_id=eid,
                    field_path="",
                    canonical_value=canonical[eid],
                    candidate_value=None,
                    source_name=source_name,
                    delta_kind="missing",
                    severity="low",
                    resolution_status="open",
                )
            )
            continue
        a, b = canonical[eid], candidate[eid]
        for field in ("name", "cost"):
            va, vb = a.get(field), b.get(field)
            if va != vb:
                kind: Any = "numeric_drift" if field == "cost" else "identity_mismatch"
                sev = "high" if field == "cost" and va is not None and vb is not None and abs(float(va) - float(vb)) > 50 else "medium"
                out.append(
                    DiscrepancyRecord(
                        entity_type="item",
                        entity_id=eid,
                        field_path=field,
                        canonical_value=va,
                        candidate_value=vb,
                        source_name=source_name,
                        delta_kind=kind,
                        severity=sev,
                        resolution_status="open",
                    )
                )
    return out
