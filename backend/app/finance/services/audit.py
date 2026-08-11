class FinanceAuditService:
    def __init__(self,repository):self.repo=repository

    async def list(self,scope,page=1,page_size=50):
        return await self.repo.list(scope,limit=page_size,offset=(page-1)*page_size)
