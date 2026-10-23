# D70 Voxtral synthetic diagnostics and next bounded investigation

**Purpose:** Record further native SDK checks after ADR-109 and distinguish completed synthetic evidence from the proposed original-weight backend comparison.

**Date:** 2026-10-23. **Status:** Synthetic investigation and ADR-110 code/tests/packet complete; new original-weight execution closed and unapproved. **D70 NATURALNESS OPEN; D71 NOT STARTED.** The retained first campaign remains **4/12 FAIL**. [Prepared evidence](evidence/d70-voxtral-attention-protocol-prepared.json), [ADR-110](ADR/110-proposed-voxtral-paired-attention-diagnostic.md).

## Completed checks

| Question | Actual synthetic observation | Limit |
|---|---|---|
| Does the pread path lose nonpersistent buffers? |7,116parameter/60tensor fixture: FP32 RoPE buffer and original_inv_freq match the standard loader; full logits exactly equal | Does not establish all original-weight numerical behavior |
| Is audio skipped during cached generation? | Both eager and SDPA: one audio-encoder call with cache, four without cache for four output tokens; cached/uncached tokens equal within each backend | Authored random fixture, not actual auditory accuracy |
| Does encoder SDPA become causal or grossly diverge? | One random1280width/20head/head64 block at1500positions preserves future influence; maximum absolute eager/SDPA difference0.000244140625 within preregistered tolerance | Not the original32layer encoder or a performance benchmark |
| Does the mel frontend differ from independent arithmetic? | Mistral filter bank and explicit STFT/clamp/global-normalization math match native features exactly on authored silence, tones, noise and step | No actual speech or independent listening judgement |

No demonstrated causal fix was found. No accepted source, model, SDK or runtime was modified. The first buffer/cache/attention checks passed4tests14.56s; expanded frontend/two-backend checks passed5tests18.16s. These logs are retained separately.

The new paired runtime was also exercised through actual native processor/forward/generation on a **random2,114,232parameter** fixture with the real131072vocabulary,375audio placeholders and401input tokens, using only authored0.2second silence. Both eager and SDPA paths produced complete bounded raw observations and full first-logit records; the parent independently reconstructed vectors and metrics. Random outputs were not valid presence labels and did not reach native EOS within16tokens; these failures remain unmodified. This test checks execution/retention/metric reconciliation, **not qualification or useful audio judgement**.

Final **470 TTS-related tests PASS64.37s, 0FAIL/0SKIP; Ruff PASS**.38new tests comprise5synthetic checks and33paired-protocol controls, including actual sealed-namespace permission denial, blind request/source/provenance binding, packet symlink rejection, complete/partial first-phase retention, no-retry enforcement, native EOS/raw/schema/feature checks and full-vector corruption/duplicate/metric/bound rejection. Historical463/469test runs remain separate before the final hardening. One existing deliberate duplicate-archive-fixture warning. No full661-source regression or new original-model audio benchmark is claimed.

Fresh integrity audit verifies **661source files/all656prior source bytes unchanged**,917protected files,176original inputs,52immutable prior D70 evidence files,23,475original TTS SDK entries,23,382old reviewer SDK entries/16artifacts and19,561Voxtral SDK entries/all9artifacts. Original services/data/security/config/collections and CORE PID37256/start63900/command/context32768 remain unchanged.24pending human-listening fields remain null/unlistened; no new original-weight worker or common24audio review. All execution guards remain False.

## Concrete next experiment, pending approval

The hypothesis left open by these fixtures is original-weight sensitivity to native eager versus SDPA. ADR-110 proposes **one worker** comparing both backends on the same four historical presence signals, same prompt/decoder/features, with8explicit diagnostic forwards and8first responses, plus one independent no-weights feature replay. Full first-logit vectors are retained and recomputed outside the worker. The packet is prepared locally:4opaque float32 copies plus request/provenance,6files. It is deliberately **not fresh held-out qualification**.

Keep12GiBaddressspace/14GiBsampledhostguard/CPU2/offline/originalCOREloaded/20GiBroot; worker900swall/retained1200sCPU, replay120swall; no new weights/packages/GPU/retry/context reduction. Eager memory fit is unmeasured and may fail inside the unchanged cap. No automatic backend/model choice, qualification rerun,24audio review or D70 closure is included. Existing model/architecture/data migration remains none; rollback closes the research guard and preserves first evidence.

The previous explicit approval covered one ADR-109 campaign and has been consumed. The new worker therefore awaits a separate explicit approval for this exact counterfactual; synthetic preparation and tests do not grant original-weight execution. A successful diagnostic would only inform a later decision about independent qualification.
