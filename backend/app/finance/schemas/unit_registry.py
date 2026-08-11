"""Unit registry API DTOs."""

from .base import ApiModel


class UnitDefinitionResponse(ApiModel):
    code: str
    label_fa: str
    dimension: str
    dimension_label_fa: str
    decimal_precision: int
    active: bool


class UnitRegistryResponse(ApiModel):
    items: list[UnitDefinitionResponse]

