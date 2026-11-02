# D60 rate-limit recovery panel

Purpose: apply the now-observed provider rate-limit recovery interval to one separately recorded fixed-corpus panel while retaining both unsuccessful earlier cohorts.

Date: 2026-11-03 (Asia/Ho_Chi_Minh). P1 follow-up under the owner's instruction to diagnose and complete8/8valid responses. Dependencies and risks remain those in [the initial availability protocol](D60_BRAVE_AVAILABILITY_PROTOCOL.md); added effort is at most30minutes. No architecture/model/provider/default deployment change.

## New evidence and intervention

The fresh Python-English diagnostic returned5valid hits/no declared failure. The subsequent30-second paced panel stopped on its second question:1valid/1error/6not-run. The error's reason hash exactly matches the installed serializer's finite English label `too many requests`. Reconstructing the complete bounded JSON with the fixed question, empty arrays and this label matches both byte length and SHA256 of the original222-byte response and this new211-byte response. This proves the declaration, not an independently captured upstream HTTP status/header or all underlying causes.

The actual merged SearXNG setting `search.suspended_times.SearxEngineTooManyRequests` is180seconds. The older source docstring mentioning one hour is not the effective configuration. No setting is changed. Original adapter/schema/model/query/label/threshold choices remain byte-identical.

## Bounded cause-based recovery measurement

This supersedes the earlier one-panel/operator request budget for this newly diagnosed intervention only: retain all3actual requests of that completed attempt, then allow exactly one new panel of at most8requests, total at most11for this owner follow-up. No additional diagnostic, repeated panel or automatic retry is scheduled. This is a changed-condition recovery measurement, not replacing either first score or selecting a best result among hidden reruns.

Freeze code/tests/corpus/configuration and the exact old response proofs before dispatch. First dispatch is no earlier than the last recorded failure's completionUTC plus180seconds; thereafter require at least180seconds between actual starts. Keep original10-second adapter budget and max5results, with operator waiting outside that budget; total wall limit1800seconds. Retain the exact eight original questions/order/source labels and thresholds8valid/6primary/min2per language/min1per topic. Stop after any error, retaining all eight denominator rows. No model calls, shared-service restart, header/cookie/IP rotation, CAPTCHA bypass, engine fallback or database/Vault mutation.

One request every three minutes may qualify this slow fixed sample; it does not establish availability at the application's existing request cadence or fit the unchanged45-second research budget. Any production queue/global cooldown/API-provider proposal remains a separate assessed architecture/product task. Verify unchanged750-source software/config/protected evidence/runtime and report private tool tests separately from retained full5889. Preserve every old receipt. Publish the new result, roadmap/devlog and complete changed files after actual closure.
