# DOCX structured round-trip golden

**Purpose:** Describe the trusted D19 paragraph/table/style fixture and independent opening oracle.

`styled-table.docx` was generated with dev-only python-docx 1.2.0. Production code uses lxml and direct ZIP member preservation. The fixture contains no external relationships, macros, user data or credentials.

| Main-body paragraph ID | Native content | Formatting/structure |
|---|---|---|
| 1 | `Báo cáo D19` | Heading1 |
| 2 | `Alpha + Beta\tXin chào\nViệt Nam` | EvidenceBody based on Normal;3 runs: bold, italic, underline |
| 3 | `Tên` | Table1,row1,cell1 |
| 4 | `Giá trị` | Table1,row1,cell2 |
| 5 | `một` | Table1,row2,cell1 |
| 6 | `42` | Table1,row2,cell2 |
| 7 | `merged` | Table1,row3,cell1,gridSpan2 |

Table style is TableGrid. Header/footer contain `Header preserved`/`Footer preserved`; inspection deliberately excludes them, while rewrite retains their ZIP member bytes and relationships exactly. Tests compare every non-document.xml member, reopen with python-docx, inspect run properties/styles/table values and round-trip the rewritten package through the real sandbox reader.

A trusted rewritten variant is opened by installed `/usr/bin/libreoffice --headless` using an exclusive temporary profile and a credential-free environment, converted to PDF, then checked for edited text and table values. LibreOffice is a local development acceptance tool, never a production untrusted-document parser. This proves actual opening for this golden, not arbitrary Word visual fidelity or pagination. No generated acceptance outputs are committed.

Hostile/resource variants are constructed separately: external relationships, DTD, macro/nested ZIP members, oversized XML, paragraph/run/document text limits, fields/signatures, invalid indices and stale source hashes. Modified XML members use ZIP_STORED so native text-budget cases do not accidentally pass by hitting the earlier compression-ratio gate.
