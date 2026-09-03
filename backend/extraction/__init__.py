# -*- coding: utf-8 -*-
"""Self-hosted extraction providers. LOCAL DEVELOPMENT ONLY.

Deliberately a sibling of `app/finance` rather than a module inside it. These packages
weigh several gigabytes and pull in a full deep-learning runtime; `app/finance` imports
none of them and must keep importing none of them, so a deployment that never reads an
image never carries the weight.

Nothing here touches a database, a migration, or an API contract.
"""
