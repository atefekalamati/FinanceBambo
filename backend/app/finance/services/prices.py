from datetime import datetime,timezone,date
from uuid import uuid4
from ..domain.prices import PriceVersion,latest_price_trend

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
 async def trends(self,scope,as_of:date):
  histories=await self.repo.trend_history(scope,as_of);result=[]
  for resource_id,versions in histories.items():
   project=[value for value in versions if value.scope_kind=="project"]
   organization=[value for value in versions if value.scope_kind=="organization"]
   selected=project or organization
   trend=latest_price_trend(selected)
   if trend is None:
    result.append({"resource_id":resource_id,"current_price_irr":None,"previous_price_irr":None,"latest_change_percent":None,"trend_direction":"none","scope_kind":None,"trend_points":[]});continue
   current,previous,percent,direction,points=trend
   result.append({"resource_id":resource_id,"current_price_irr":current.unit_price_irr,"previous_price_irr":None if previous is None else previous.unit_price_irr,"latest_change_percent":percent,"trend_direction":direction,"scope_kind":current.scope_kind,"trend_points":[{"effective_from":value.effective_from,"unit_price_irr":value.unit_price_irr} for value in points]})
  return result
