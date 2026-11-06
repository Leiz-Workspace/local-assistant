# ADR 160 — US term phonemes with the retained voice and API

**Purpose:** Compare source-backed American-English term hypotheses on exactly matched sentences/voices while preserving accepted API/date/clause paths and old evidence.

**Status:** Owner-requested bounded research: “Tiếp đi và thử với các từ khác nữa”, with explicit en-US/same-voice preference already recorded. No model, reference asset, SDK, training, product-default or ADR-155 change.

## Corpus and hypotheses

Six fixed source sentences, both existing Trúc Ly/Ngọc Huyền voices:

1. “Bạn muốn học Python hay dùng API của ứng dụng?”
2. “I write code in Python every day.”
3. “Chị sẽ dùng Docker để chạy ứng dụng.”
4. “Mã nguồn được lưu trên GitHub của dự án.”
5. “Mở browser để kiểm tra trang web của ứng dụng.”
6. “Server đang kết nối với database của ứng dụng.”

Inspect original dictionary/context phones before choosing interventions. Native inspection already finds Python `pˈaɪθən`, Docker `dˈɑːkɚ`, browser `bɹˈaʊzɚ`, server `sˈɜːvɚ`, database `dˈeɪɾəbˌeɪs`; GitHub in context is `ɡˈɪt hˈʌb`, while its native whole-word dictionary entry is `ɡˈɪthʌb`. Keep Docker/browser/database phones unchanged as controls; no claim these sound correct yet or that dictionary docker certifies a brand's preferred voice.

Only three hypotheses:

- Python → `pˈaɪθɑːn`, targeting Cambridge US `/ˈpaɪ.θɑːn/`.
- Server → `sˈɜːɹvɚ`, an explicit rhotic sequence targeting Cambridge American `/ˈsɜr·vər/`; representation is an engineering hypothesis, not a guaranteed acoustic equivalent.
- GitHub → native dictionary `ɡˈɪthʌb` instead of the split/stressed context form; source-backed whole-word experiment, not an independently certified brand pronunciation.

Both baseline and candidate first apply the **unchanged accepted API stress function**; retain original text renderer/clause adapter, voice references ON, seed/sampling/style/codec. No Vietnamese respelling, altered display text, word splitting, artificial added context, audio repair or ref-off ablation. Each generated chunk has exact baseline/candidate phones; only declared term spans may differ. Full-sentence audio can change outside the edited word, so unchanged phones do not certify unchanged pronunciation or voice identity.

## Fair bounds and reuse

Twelve matched sentence/voice pairs =24 logical audio observations. Reuse the four exact Python baselines: mixed Python/API from ADR159 and English Python from the Roman-context controls. Do not regenerate them. Docker/browser candidate phones equal baseline: generate one control per voice and share it visibly, not a second identical native request. Expected **16 new requests/16chunks**, engineering ceiling **20** requests/chunks, zero retries; baseline8new and candidate8new. Freeze all planned slots/provenance and dedup decisions before neural calls.

Use the same per-pair frame cap, **min(original baseline cap, original candidate cap,300)**. This conservative bound can reduce a new baseline's allowance, never increases either original allowance. Reused Python baselines are admissible only if their original cap equals the shared cap; otherwise refuse the study instead of claiming an equal comparison. Character length may change for the US phones, so do not claim length preservation. Require zero unknown tokens and exact roundtrip; preserve gaps/question punctuation and unchanged word spans. Actual trace must match the probe. Audit speaker/reference hashes on new requests; old baseline voice provenance is bound by retained files/results, not invented retrospective embedding measurements.

One sequential worker per role, at most12requests each; CPU0,1/two threads/AS8GiB/TTS sampledRSS2GiB/aggregate8GiB/headroom14GiB/root8GiB/panel120seconds. Keep original33research/750application/210protected, SDK/models/presets/audio intact. Freeze new source/tests, passing software, source references, authority, probe and retained baseline hashes. Stop/join on first software/resource/provenance/completeness/cleanup failure, retain failed/unattempted slots. No additional requests or repairs after hearing results.

## Acceptance, sources, risk and rollback

P1 VOICE-BILINGUAL-IDENTITY-001 and VOICE-ENGLISH-READING-001. Dependencies: exact en-US targets, retained baselines/model/voice, token/resource guards and tested bounded worker. Effort one six-sentence paired milestone. Risks: phoneme encoding does not guarantee accent; fixed words overfit; same speaker inputs can sound different; reduced frame budget can reject outputs; inter-term attention affects other words. Software PASS/EOS and waveform differences are not acoustic quality PASS. Owner listening must assess target words, API, overall sentence naturalness and perceived voice similarity.

Primary pronunciation references: [Python US](https://dictionary.cambridge.org/pronunciation/english/python), [server US/American entry](https://dictionary.cambridge.org/dictionary/english/server), [docker](https://dictionary.cambridge.org/dictionary/english/docker), [browser](https://dictionary.cambridge.org/pronunciation/english/browser), [database](https://dictionary.cambridge.org/pronunciation/english/database). GitHub hypothesis is explicitly from the pinned local G2P dictionary, not a claimed official external IPA standard.

Rollback rejects only the optional new phonemizer and retires owned workers; existing accepted paths never receive a product cutover. No model/reference/training/migration is authorized. Broader English quality, XI acoustic listening, rights/no-speech/physical4seconds/model/voice/product/D90release remain separate; D60 deferred and ADR155workflow unapproved.
