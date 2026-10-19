# Memory follow-up backlog

**Purpose:** Assess memory features beyond the current milestone before scheduling implementation or changing accepted data/model behavior.

| ID | Priority | Proposed feature | Dependencies | Effort | Risks / gate | Status |
|---|---|---|---|---|---|---|
| MEMORY-001 | P2 | Explicit file-to-memory adapter using exact native field spans | D30 message/manual memory and D31 source deletion/export/privacy; D28 native source mapping | At least1 milestone; re-estimate after design | Duplicate retained file facts, root/native-field drift, source deletion propagation; own ADR and real tests, no automatic file scan | Unscheduled; structural FileEvidence schema only |
| MEMORY-002 | P2 | Memory-to-prompt retrieval/use composition | D30/D31 and exact current consent/source fences | At least1 milestone | Instruction injection, stale scope/consent, deleted facts resurfacing; bounded model context and acceptance required | Unscheduled; no automatic prompt injection |
| MEMORY-003 | Conditional P2 | Semantic/vector memory index | Demonstrated need versus bounded structured lookup, MEMORY-002 and D31 | Re-estimate after measured need | Duplicate storage/delete propagation, embedding compatibility/resources; benchmark and owner approval before any model replacement | Unscheduled; no memory collection/model download |

These are future features, not implemented capabilities or substitutes for current acceptance criteria. Development-day numbering may extend beyond90. Original model choices, source/RAG configuration, user data and approval rules remain unchanged.
