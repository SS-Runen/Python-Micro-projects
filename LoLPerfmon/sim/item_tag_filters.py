"""Optional filtering of the item catalog by Data Dragon ``tags`` (e.g. exclude ``Support``)."""

from __future__ import annotations

from .models import ItemDef


def filter_items_by_tags(
    items: dict[str, ItemDef],
    *,
    exclude_tags: set[str] | frozenset[str] | None = None,
    require_tags: set[str] | frozenset[str] | None = None,
) -> dict[str, ItemDef]:
    """
    Return a subset of ``items``.

    - If ``exclude_tags`` is non-empty, drop items whose ``tags`` intersect ``exclude_tags``.
    - If ``require_tags`` is non-empty, keep only items whose ``tags`` intersect ``require_tags``.
    """
    ex = frozenset(exclude_tags or ())
    rq = frozenset(require_tags or ())
    out: dict[str, ItemDef] = {}
    for iid, it in items.items():
        tags = frozenset(it.tags)
        if ex and tags & ex:
            continue
        if rq and not (tags & rq):
            continue
        out[iid] = it
    return out
