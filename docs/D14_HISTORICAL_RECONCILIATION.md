# D14 — Historical D11–D14 evidence reconciliation

**Purpose:** Reconcile actual source artifact dates and scopes without rewriting old benchmark results or assuming a development-day label is a calendar date.

Date:2026-10-26. [Exact original file hashes and metadata](evidence/d14-historical-reconciliation.json). All dates below are the recordedUTCartifact timestamps; the project timezone isAsia/Ho_Chi_Minh. The later devlog2026-10-16checkpoint describes when evidence was compiled, not proof that every run occurred on that date.

| Development label | Actual retained evidence | Supported conclusion |
|---|---|---|
| D11structured | CORE2026-10-12T14:57:07Z; UNRESTRICTED15:04:24Z; both declaredpassedtrue | Historical structured smoke succeeded; this is not a complete JSON/security scorecard |
| D11coding | CORE2026-10-13T02:14:27Z; UNRESTRICTED02:15:15Z; each3/3 | Three historical coding cases/profile, not proof of broad repair quality |
| D12agent | CORE2026-10-13T02:28:25Z; UNRESTRICTED02:29:12Z; each4/4 | Historical authored agent-format cases, not real privileged tool grants |
| D13scorecard | 2026-10-13T02:52:35Z; stage day13_provisional | Originalweights20/20/20/10/10/10/5/5; original70coveredpoints only and explicit scope disclaimers |
| D14runtime gates | CORE2026-10-13T02:55:54Z; UNRESTRICTED02:58:04Z; each9/9 | YAML/artifact/runtime/Docker/API readiness on that historical setup; not full weighted model quality |
| Later vision | CORE2026-10-13T08:40:24Z; UNRESTRICTED08:41:04Z | Three actual nativeimage responses/profile, with original semantic-review limitation; no automatic new numerical credits |
| Later32K | Three dated COREartifact cohorts2026-10-15 | Original near-full32Kmeasurements retained, including limited/failed cohorts; not silently substituted for a new paired benchmark |
| MQ001/002 | 2026-10-24 | Same30authored textcases: CORE23/30/52.5of70; UNRESTRICTED20/30/45of70. Allfirstfailures retained; CPU/template/date confounders remain |
| Current D14completion | 2026-10-26, separately frozen | New media/context/streaming/provenance/lifecycle measurements add their own evidence; original files above remain byte-identical |

The old `tests/release_gate.py` still expects16Kand writes historicalday14paths. It was inspected, not rerun or edited: running it against the current32Kconfiguration would mix a stale assumption with current acceptance and overwrite original reports. The new benchmark verifies exact current32Kidentity in a private output root instead.

The historical all9/9readiness claims and provisional scores stay historical. Reconciliation closes the missing evidence/date mapping; it does not retroactively certify D7standalone output, remove known first failures, establish universal quality or authorize release/model replacement. Current weighted findings and explicit model disposition must be read alongside this mapping.
