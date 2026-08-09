from datetime import datetime,timezone
from uuid import uuid4
from ..domain.conversions import UnitConversion
from ..domain.resources import FinanceRecordNotFound
class UnitConversionService:
 def __init__(self,repo,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.ids=id_factory;self.clock=clock
 def actor(self,s):
  if s.actor_user_id is None:raise PermissionError("authenticated actor is required")
  return s.actor_user_id
 async def list(self,s):return await self.repo.list(s)
 async def create(self,s,c):
  rows=await self.repo.list(s);version=max((x.version for x in rows if (x.scope_kind,x.source_unit,x.target_unit,x.dimension)==(c.scope_kind,c.source_unit,c.target_unit,c.dimension)),default=0)+1
  v=UnitConversion(self.ids(),s.organization_id,s.project_id,c.scope_kind,version,c.source_unit.strip(),c.target_unit.strip(),c.dimension.strip(),c.factor,c.effective_from,c.reason.strip(),self.actor(s),self.clock())
  return await self.repo.append(s,v,self.ids())
 async def revise(self,s,cid,c):
  old=await self.repo.get(s,cid)
  if old is None:raise FinanceRecordNotFound("unit conversion not found")
  v=UnitConversion(self.ids(),s.organization_id,s.project_id,old.scope_kind,old.version+1,old.source_unit,old.target_unit,old.dimension,c.factor,c.effective_from,c.reason,self.actor(s),self.clock())
  return await self.repo.append(s,v,self.ids(),old)
