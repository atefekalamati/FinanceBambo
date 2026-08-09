from datetime import datetime,timezone,date
from uuid import uuid4
from ..domain.prices import PriceVersion

class FinancePriceService:
 def __init__(self,repository,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)): self.repo=repository;self.ids=id_factory;self.clock=clock
 async def create(self,scope,resource_id,command):
  if scope.actor_user_id is None: raise PermissionError("authenticated actor is required")
  history=await self.repo.history(scope,resource_id)
  version=max((x.version for x in history),default=0)+1
  value=PriceVersion(self.ids(),scope.organization_id,scope.project_id,resource_id,command.scope_kind,version,command.unit_price_irr,command.effective_from,command.reason,scope.actor_user_id,self.clock())
  return await self.repo.append(scope,value,self.ids())
 async def history(self,scope,resource_id=None): return await self.repo.history(scope,resource_id)
 async def current(self,scope,resource_id,as_of:date): return await self.repo.current(scope,resource_id,as_of)
