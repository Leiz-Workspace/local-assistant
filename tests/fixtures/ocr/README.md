# D21 page OCR and local vision goldens

**Purpose:** Define synthetic source/page/text/table oracles and honest uncertainty evaluation.

All files were generated from Pillow with DejaVuSans text, contain no credentials/user data and are deliberately small. Runtime uses the same sandboxed parser path as file APIs.

| Fixture | Oracle / gate |
|---|---|
| clean.png | English `LOCAL OCR GOLDEN\nInvoice 2048\nTotal 42 USD`; transcription CER≤0.02 and WER0 |
| scanned.pdf,page1 | Image-only version of clean.png; same text/quality gate, page mapping1/2 |
| scanned.pdf,page2 | Blank raster; empty output, no score, review required, locator2/2 |
| blank.png | Blank raster; no invented text/confidence, review required |
| unclear.png | Original text `uncertain 7381`,14px font/Gaussian blur3; evaluate uncertainty detection, not successful transcription |
| table-vie.png | Rows `Tên hàng | Số lượng`, `Bút | 3`, `Vở | 5`; explicit actual CORE vision, exact row order and6/6 cells |

The blurred fixture is a real OCR failure: current output is empty, CER/WER1.0 (100% error). Its acceptance criterion is that review is required and confidence is absent/low. Metrics retain this failure; it is never scored as perfect blank-page transcription. Clean image/scan are separate transcription gates. Scores are raw Tesseract character-weighted word scores, not calibrated probabilities.

The native-PDF comparison reuses `../pdf/native-pages.pdf` and also proves D18 native extraction yields no text for scanned.pdf. OCR boxes use normalized rendered pixels, not PDF coordinates. Images apply EXIF orientation and strip all metadata, including ICC; the regression test reproduces ICC retention before the fix. A source JPEG metadata probe is constructed only in memory.

The Vietnamese table measures one clean VLM example, not general multilingual OCR/layout quality. VLM always requires review and never reports a numeric confidence. Tesseract currently has English only; mixed/native pages may require explicit OCR/VLM mode. No model tools, formula execution, document instructions or implicit indexing are allowed.

Run `uv run python -m scripts.ocr_acceptance` to regenerate numeric/version/hash evidence. It stores no recognized/model text or image bytes in the metric JSON. Local tools observed: Tesseract5.5.0 (eng/osd), Poppler26.01.0 and configured CORE alias qwen3.5-9b-core. Existing file feature remains opt-in and local/one worker.
