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


#: Every unit Finance recognises. One place, and the only place: `finance_resources`
#: validates `base_unit` against it, `/unit-registry` publishes it, and the frontend builds
#: its unit dropdowns from what that endpoint returns -- so a unit added here becomes
#: selectable everywhere without a second list existing anywhere.
#:
#: The material price sheet brought seven more. They are here rather than in the price code
#: for exactly that reason: a unit the price importer knew about and the resource editor did
#: not would be two vocabularies, and a price would be comparable to a resource only by
#: accident. `domain/unit_conversion.py` holds the ratios between them.
UNIT_REGISTRY: dict[str, UnitDefinition] = {
    # mass
    "g": UnitDefinition("g", "گرم", "mass", "جرم", 4),
    "kg": UnitDefinition("kg", "کیلوگرم", "mass", "جرم", 4),
    "ton": UnitDefinition("ton", "تن", "mass", "جرم", 4),
    # length
    "mm": UnitDefinition("mm", "میلی‌متر", "length", "طول", 4),
    "cm": UnitDefinition("cm", "سانتی‌متر", "length", "طول", 4),
    "m": UnitDefinition("m", "متر", "length", "طول", 4),
    # area
    "cm2": UnitDefinition("cm2", "سانتی‌مترمربع", "area", "مساحت", 4),
    "m2": UnitDefinition("m2", "مترمربع", "area", "مساحت", 4),
    # volume
    "liter": UnitDefinition("liter", "لیتر", "volume", "حجم", 4),
    "m3": UnitDefinition("m3", "مترمکعب", "volume", "حجم", 4),
    # count. A branch and a bag are each ONE countable thing and that is all these say.
    # Neither carries a weight or a length: «شاخه» to kilogram is a fact about one product
    # and is stored against that product, never derived from the fact that it is a branch.
    "each": UnitDefinition("each", "عدد", "count", "تعداد", 4),
    "branch": UnitDefinition("branch", "شاخه", "count", "تعداد", 4),
    "bag": UnitDefinition("bag", "کیسه", "count", "تعداد", 4),
    # time
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
