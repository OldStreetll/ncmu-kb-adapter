"""Translate Dify ``metadata_condition`` to FastGPT ``collectionIds``.

FastGPT's filtering lives at the Collection (=file) level via
``collectionIds``, not at the chunk-metadata level that Dify's
``metadata_condition`` can express. We support the filename-oriented subset
and document the rest as an unsupported filter (spec §10.5.4 note #4).

Return contract:
- ``None``  – no filter applicable; caller should run an unfiltered search.
- ``[]``    – a filter *was* applicable but matched zero collections; caller
              should short-circuit with ``{"records": []}`` and NOT call
              FastGPT ``/searchTest`` (saves a round trip, and Dify expects
              an empty set anyway).
- ``[...]`` – the list of collection ids to forward as ``collectionIds``.
"""

from typing import Optional

from .fastgpt_client import FastGPTClient
from .models import MetadataCondition, MetadataConditionItem


_FILENAME_FIELDS = {"filename", "source", "file_name"}


async def translate_metadata_to_collection_ids(
    mc: Optional[MetadataCondition],
    dataset_id: str,
    client: FastGPTClient,
) -> Optional[list[str]]:
    if mc is None or not mc.conditions:
        return None

    filename_conditions = [c for c in mc.conditions if _is_filename_cond(c)]
    if not filename_conditions:
        # Non-filename conditions are ignored (unsupported_filter); spec §10.5.4 note #4.
        return None

    resp = await client.list_collections(dataset_id)
    collections = resp.get("data", {}).get("list", [])

    logical = (mc.logical_operator or "and").lower()
    matches: Optional[set[str]] = None
    for cond in filename_conditions:
        matched = {
            col["_id"]
            for col in collections
            if _matches(col.get("name", ""), cond.comparison_operator, cond.value)
        }
        matches = matched if matches is None else _combine(matches, matched, logical)

    return sorted(matches or [])


def _is_filename_cond(cond: MetadataConditionItem) -> bool:
    return any((n or "").lower() in _FILENAME_FIELDS for n in cond.name)


def _matches(name: str, operator: str, value: Optional[str]) -> bool:
    if value is None:
        return False
    op = operator.lower().strip()
    if op == "contains":
        return value in name
    if op == "not contains":
        return value not in name
    if op in {"is", "="}:
        return name == value
    if op in {"is not", "!="}:
        return name != value
    if op == "start with":
        return name.startswith(value)
    if op == "end with":
        return name.endswith(value)
    return False


def _combine(a: set[str], b: set[str], logical: str) -> set[str]:
    return a | b if logical == "or" else a & b
