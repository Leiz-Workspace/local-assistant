# D60 resumed availability and local cooldown preparation

Purpose: report one newly requested availability cohort separately from prior failures and distinguish a private cooldown prototype from production behavior.

Date: 2026-11-03 (Asia/Ho_Chi_Minh). Status: actual fixed eight-question panel RUNNING; no8/8or broader acceptance claimed yet. [Frozen protocol](D60_BRAVE_RESUME_PROTOCOL.md), [execution freeze](evidence/d60-brave-20261103-resume-freeze.json).

## New measurement

The owner requested continuation after an extended idle interval. Keep the same selected SearXNG-Brave website engine and exact eight original questions/order/source labels. One attempt per question, maximum8calls, minimum180seconds between starts, original10-second provider timeout and1800-second total operator limit. No preliminary diagnostic, new model, endpoint change, retry or default configuration modification. Stop after the first error; preserve every failed/unattempted denominator row. Acceptance remains8valid/6primary/min2per language/min1per topic; URI presence is not independent semantic relevance or verified freshness.

All750application/config/test files match the previously verified full5889snapshot. Private operator execution/test inputs and provider configuration were frozen before requests. The earlier4/8,1/8and0/8cohorts and exact rate-limit proofs remain untouched. Results of this cohort will be published after its actual terminal closure, with source/runtime/protected-evidence verification.

## Private cooldown prototype

`data/backups/d60-brave-20261103-local-cooldown.py` is opt-in preparation, not registered in the API or used to relabel live measurements. It borrows a validated SearXNG port and returns the original result/error. Known quota/unavailability/transport failures start local exponential cooldown180→360→720→1440→2880→3600seconds, capped thereafter. Premature calls return finite local retry metadata before network activity. Once elapsed, only one explicitly requested probe can run; there is no automatic retry, sleeping request queue or background polling.

Nonqueued admission remains held until owned dependency cleanup joins, including repeated cancellation, swallowed cancellation and timeout. Shutdown closes only owned calls, not the borrowed provider/shared service. Invalid or backwards clock readings fail closed. Logs exclude query, credential, URL and backend prose. Empty valid search results remain valid; unrelated errors are not called proven rate limits.

State is per instance/in memory, not a distributed limiter or persistent provider reset guarantee. Local retry time does not mean Brave has agreed to accept a request then. Production integration, state sharing/restart behavior and compatibility with the unchanged45-second research budget remain a separate architecture/product decision. No model/provider/Docker/Vault/database/default changes are made here.

25prototype controls plus the overlapping resumed-operator/translated-diagnostic/proof controls total81PASS1.36s, no live network/model calls in these tests. The retained full5889is unchanged and these private counts are not added to it. Complete code versions and neutral evidence are delivered after terminal measurement/audit/commit.
