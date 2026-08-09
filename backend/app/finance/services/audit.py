class FinanceAuditService:
    def __init__(self,repository):self.repo=repository

    async def list(self,scope):return await self.repo.list(scope)
