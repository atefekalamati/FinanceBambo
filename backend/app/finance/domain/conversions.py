from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID
@dataclass(frozen=True)
class UnitConversion:
 id:UUID;organization_id:UUID;project_id:str;scope_kind:str;version:int;source_unit:str;target_unit:str;dimension:str;factor:Decimal;effective_from:date;reason:str;created_by:UUID;created_at:datetime
