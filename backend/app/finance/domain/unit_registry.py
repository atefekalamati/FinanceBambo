"""Finance unit registry used to derive dimensions from base units."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitDefinition:
    code: str
    label_fa: str
    dimension: str
    dimension_label_fa: str
    decimal_precision: int
    active: bool = True


UNIT_REGISTRY: dict[str, UnitDefinition] = {
    "kg": UnitDefinition("kg", "کیلوگرم", "mass", "جرم", 4),
    "ton": UnitDefinition("ton", "تن", "mass", "جرم", 4),
    "m": UnitDefinition("m", "متر", "length", "طول", 4),
    "m2": UnitDefinition("m2", "مترمربع", "area", "مساحت", 4),
    "m3": UnitDefinition("m3", "مترمکعب", "volume", "حجم", 4),
    "each": UnitDefinition("each", "عدد", "count", "تعداد", 4),
    "hour": UnitDefinition("hour", "ساعت", "time", "زمان", 4),
    "day": UnitDefinition("day", "روز", "equipment_time", "زمان تجهیز", 4),
}


def units_are_compatible(source_unit: str, target_unit: str, dimension: str) -> bool:
    source = UNIT_REGISTRY.get(source_unit)
    target = UNIT_REGISTRY.get(target_unit)
    if source is None or target is None or not source.active or not target.active:
        return False
    if source.dimension == target.dimension == dimension:
        return True
    return (source_unit, target_unit, dimension) in {
        ("day", "hour", "equipment_time"),
        ("hour", "day", "equipment_time"),
    }

