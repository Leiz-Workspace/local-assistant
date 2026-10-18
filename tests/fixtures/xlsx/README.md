# XLSX formula-preserving round-trip golden

**Purpose:** Define the independent D20 workbook oracle and its conservative supported subset.

`styled-formulas.xlsx` originates from dev-only openpyxl 3.1.5 and has two sheets. Fixture construction makes package relationships relative to comply with the already accepted D17 verifier, inserts one shared-string part, and supplies explicit formula cached values. No credentials/macros/external relationships are present. Production code uses direct ZIP/lxml processing rather than openpyxl.

| Sheet | Cell | Native value / intent |
|---|---|---|
| Dữ liệu (ID1) | A1 | `Xin chào`; bold/red font/yellow fill |
| Dữ liệu | A2, B2 | numeric10/20; A2 has `0.00` number format |
| Dữ liệu | C2 | formula `SUM(A2:B2)`, attribute `ca=1`, cached30 |
| Dữ liệu | A3 | boolean true |
| Dữ liệu | B3 | shared string `shared text` |
| Dữ liệu | A4:B4 | merged range, anchor text `merged` |
| Summary (ID2) | A1 | cross-sheet formula `'Dữ liệu'!C2*2`, cached60 |
| Summary | B1 | `Untouched sheet` |

The first sheet has freeze paneB2 and columnA width24. Tests rewrite literals in the first sheet, reopen with openpyxl (`data_only=False` and `True`), and verify exact formula/cache/style/merge/freeze/width preservation. Every package member except the changed worksheet remains byte-identical; formula XML inside the changed sheet also remains byte-identical. Editing input A2 intentionally leaves C2's old cached30 unchanged; responses label this `preserved_not_recalculated`.

A replacement string beginning `=SUM(1,2)` stays an inline string (`data_type=s` after independent reopening), not a formula. No Excel/LibreOffice calculation engine opens untrusted files during runtime or tests. The fixture proves native structure/round-trip behavior for this subset, not arbitrary Excel visual rendering or calculation accuracy.

Resource variants store changed XML without compression so native cell/text/XML budget tests reach the intended bound. D17's conservative restrictions still apply: package-root absolute relationship targets, macros, external relationships and nested archives are unsupported. Normalizing the trusted fixture is not runtime adoption/repair of user input; such input is rejected under the existing policy.
