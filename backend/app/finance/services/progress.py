from datetime import datetime,timezone
from uuid import uuid4
from ..domain.progress import ProgressOverride
from ..domain.resources import FinanceRecordNotFound
class ProgressService:
 def __init__(self,repo,provider,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.provider=provider;self.ids=id_factory;self.clock=clock
 async def list_snapshots(self,s):return await self.repo.list_snapshots(s)
 async def feed(self,s,snapshot_id):
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(snapshot_id))
  meta=feed["snapshot"]
  if str(meta["organizationId"])!=str(s.organization_id) or meta["projectId"]!=s.project_id:raise FinanceRecordNotFound("progress snapshot not found")
  return feed
 async def override(self,s,line_id,c):
  if s.actor_user_id is None:raise PermissionError("authenticated actor is required")
  ref=await self.repo.get_snapshot(s,c.progress_snapshot_id)
  if ref is None:raise FinanceRecordNotFound("progress snapshot not found")
  value=ProgressOverride(self.ids(),s.organization_id,s.project_id,line_id,ref["id"],c.progress_snapshot_id,c.computed_value,c.override_value,c.reason,s.actor_user_id,self.clock())
  return await self.repo.append_override(s,value,self.ids())
