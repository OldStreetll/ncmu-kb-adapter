"""Pydantic request models for Dify External KB API.

Spec references:
- §10.5.1 Dify request schema (knowledge_id / query / retrieval_setting / metadata_condition)
- §10.5.4 implementation note #1: metadata_condition must be Optional to accept
  Dify's explicit `null` without raising ValidationError.
"""

from typing import Optional

from pydantic import BaseModel, Field


class MetadataConditionItem(BaseModel):
    name: list[str]
    comparison_operator: str
    value: Optional[str] = None


class MetadataCondition(BaseModel):
    logical_operator: Optional[str] = "and"
    conditions: list[MetadataConditionItem] = Field(default_factory=list)


class RetrievalSetting(BaseModel):
    top_k: int = 5
    score_threshold: float = 0.0


class DifyRetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: RetrievalSetting
    metadata_condition: Optional[MetadataCondition] = None
