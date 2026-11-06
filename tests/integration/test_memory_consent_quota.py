"""Verify actual consent receipt inventories cannot grow beyond declared owner/global memory limits."""

import pytest
from sqlalchemy import text
from test_memory_journal_postgres import enabled_receipt
from test_memory_journal_postgres import memory_context as memory_context

from src.application.services.memory_contract import MemoryPolicyError


async def bulk_owned_receipts(context, owner, count):
    """Fill only owned synthetic receipt inventory through real constrained SQL to reach quota boundaries."""
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                "WITH stamp AS (SELECT clock_timestamp() t) INSERT INTO assistant.memory_consents(id,owner_id,kind,scope_id,settings_revision,granted_at,expires_at) SELECT gen_random_uuid(),:owner,'preference',:owner,1,stamp.t,stamp.t+interval '1 hour' FROM generate_series(1,:count),stamp"
            ),
            dict(owner=owner, count=count),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["owner", "global"])
async def test_actual_consent_owner_global_caps(memory_context, scope):
    """Reject a new receipt at either real inventory cap without admitting implicit or excess consent."""
    context = memory_context
    journal, owner = context["journal"], context["owners"][0]
    if scope == "owner":
        await enabled_receipt(context)
        await bulk_owned_receipts(context, owner, 999)
    else:
        await journal.configure(
            owner, expected_revision=0, enabled=True, extraction_enabled=False
        )
        for other in context["owners"][1:11]:
            await enabled_receipt(context, owner=other)
            await bulk_owned_receipts(context, other, 999)
    with pytest.raises(MemoryPolicyError, match="memory_consent_limit"):
        await journal.grant(owner, kind="preference", expected_revision=1, seconds=3600)
