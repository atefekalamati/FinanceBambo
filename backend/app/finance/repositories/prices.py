from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.active_prices import active_price_resource
from ..domain.prices import PriceVersion

class PsycopgFinancePriceRepository:
 def __init__(self,connection): self.db=connection
 @staticmethod
 def map(r): return PriceVersion(r["id"],r["organization_id"],r["project_id"],r["resource_id"],r["scope_kind"],r["version"],r["unit_price_irr"],r["effective_from"],r["reason"],r["created_by"],r["created_at"])
 #: One ordering for both the whole history and any page of it. Two spellings would let
 #: a row sit on two pages or on none; the id tiebreak is what makes it total.
 ORDER=" ORDER BY pv.effective_from DESC,pv.version DESC,pv.created_at DESC,pv.id DESC"

 def _history_where(self,scope,resource_id,date_from,date_to):
  """The FROM and WHERE the whole history and a page of it must agree on.

  Scoped to the operational set, so the history a person reads is the history of the
  items they are shown. A withheld item keeps every version it ever had; this listing
  simply is not where they are read from. `current()` below is deliberately NOT scoped:
  resolving one item by id must keep working for invoices and reports for ever.

  The dates bound `effective_from` -- the day a price started applying, which is the date
  a reader means by "between these two dates". `created_at` is when somebody typed it.
  """
  sql=(" FROM price_versions pv JOIN finance_resources r"
       " ON r.organization_id=pv.organization_id AND r.project_id=pv.project_id AND r.id=pv.resource_id"
       " WHERE pv.organization_id=%s AND pv.project_id=%s AND r.deleted_at IS NULL AND "
       + active_price_resource("r")); args=[scope.organization_id,scope.project_id]
  if resource_id is not None: sql+=" AND pv.resource_id=%s";args.append(resource_id)
  if date_from is not None: sql+=" AND pv.effective_from>=%s";args.append(date_from)
  if date_to is not None: sql+=" AND pv.effective_from<=%s";args.append(date_to)
  return sql,args
 async def history(self,scope,resource_id=None):
  where,args=self._history_where(scope,resource_id,None,None)
  async with self.db.cursor(row_factory=dict_row) as c: await c.execute("SELECT pv.*"+where+self.ORDER,tuple(args)); return [self.map(x) for x in await c.fetchall()]
 async def history_page(self,scope,page,page_size,resource_id=None,date_from=None,date_to=None):
  """One page of the same history, with the total the filter matched.

  The count is taken over the identical predicate, so `totalItems` and the rows always
  describe the same set. Both run in one cursor rather than two round trips.
  """
  where,args=self._history_where(scope,resource_id,date_from,date_to)
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("SELECT count(*) AS total"+where,tuple(args)); total=(await c.fetchone())["total"]
   await c.execute("SELECT pv.*"+where+self.ORDER+" LIMIT %s OFFSET %s",tuple(args+[page_size,(page-1)*page_size]))
   return [self.map(x) for x in await c.fetchall()],total
 async def current(self,scope,resource_id,as_of):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT * FROM price_versions WHERE organization_id=%s AND project_id=%s AND resource_id=%s AND effective_from<=%s ORDER BY (scope_kind='project') DESC,effective_from DESC,version DESC,created_at DESC,id DESC LIMIT 1""",(scope.organization_id,scope.project_id,resource_id,as_of)); row=await c.fetchone()
  return None if row is None else self.map(row)
 async def trend_history(self,scope,as_of):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT r.id resource_id,pv.id,pv.organization_id,pv.project_id,pv.scope_kind,pv.version,pv.unit_price_irr,pv.effective_from,pv.reason,pv.created_by,pv.created_at FROM finance_resources r LEFT JOIN price_versions pv ON pv.organization_id=r.organization_id AND pv.project_id=r.project_id AND pv.resource_id=r.id AND pv.effective_from<=%s WHERE r.organization_id=%s AND r.project_id=%s AND r.deleted_at IS NULL AND """+active_price_resource("r")+""" ORDER BY r.id,pv.effective_from,pv.version,pv.created_at,pv.id""",(as_of,scope.organization_id,scope.project_id));rows=await c.fetchall()
  grouped={}
  for row in rows:
   grouped.setdefault(row["resource_id"],[])
   if row["id"] is not None:grouped[row["resource_id"]].append(self.map(row))
  return grouped
 async def append(self,scope,v,audit_id):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("""INSERT INTO price_versions(id,organization_id,project_id,resource_id,scope_kind,version,unit_price_irr,effective_from,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(v.id,v.organization_id,v.project_id,v.resource_id,v.scope_kind,v.version,v.unit_price_irr,v.effective_from,v.reason,v.created_by,v.created_at))
    await c.execute("""INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'price_version.created','price_versions',%s,%s,NULL,%s,%s)""",(audit_id,scope.organization_id,scope.project_id,v.created_by,v.id,v.reason,Jsonb({"version":v.version,"unitPriceIrr":str(v.unit_price_irr)}),v.created_at))
  return v
