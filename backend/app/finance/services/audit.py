class FinanceAuditService:
    def __init__(self,repository):self.repo=repository

    async def list(self,scope,page=1,page_size=50,action=None,entity_type=None,occurred_from=None,occurred_to=None,query=None):
        """Filter and page in the database, so a narrow filter cannot miss older events."""
        items,total=await self.repo.list(scope,limit=page_size,offset=(page-1)*page_size,
            action=action,entity_type=entity_type,occurred_from=occurred_from,occurred_to=occurred_to,query=query)
        return {"items":items,"page":page,"page_size":page_size,"total_items":total,
            "total_pages":0 if total==0 else ((total-1)//page_size)+1}
