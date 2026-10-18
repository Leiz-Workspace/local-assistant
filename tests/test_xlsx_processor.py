"""Verify workbook formulas/caches/styles, literal edits and actual bounded sandbox behavior."""

import copy
import hashlib
import io
import logging
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import (
    CACHE_STATUS,
    XLSX_VERSION,
    validate_plan,
    validate_view,
)
from src.infrastructure import xlsx_processor as module
from src.infrastructure.xlsx_processor import process_xlsx

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parent / "fixtures/xlsx/styled-formulas.xlsx"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def process_bytes(data, operation="read", plan=None):
    """Supply a real regular source FD to the production isolated XLSX worker."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.seek(0)
        return process_xlsx(source, operation, plan)


def plan_for(data, edits=None):
    """Bind native literal edits to the exact immutable golden hash."""
    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "edits": edits
        or [{"sheet_id": 1, "cell": "A2", "kind": "number", "value": "99.5"}],
    }


def mutate_package(data, updates):
    """Build independent package variants with stored XML to exercise native resource limits."""
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for original in source.infolist():
            info = copy.copy(original)
            if info.filename in updates:
                info.compress_type = zipfile.ZIP_STORED
            target.writestr(
                info, updates.pop(info.filename, source.read(info.filename))
            )
        for name, value in updates.items():
            target.writestr(name, value)
    return output.getvalue()


def test_golden_native_sheets_formulas_cache_styles_shared_strings():
    """Read exact multi-sheet Unicode/literal/formula/cache/merge/style identities without calculation."""
    view = process_bytes(GOLDEN.read_bytes())
    assert view["processor"] == XLSX_VERSION
    assert view["formula_cache_status"] == CACHE_STATUS
    assert [sheet["name"] for sheet in view["sheets"]] == ["Dữ liệu", "Summary"]
    cells = {cell["cell"]: cell for cell in view["sheets"][0]["cells"]}
    assert cells["A1"]["value"] == "Xin chào" and cells["A1"]["style_index"] > 0
    assert cells["A3"]["value"] == "1" and cells["A3"]["kind"] == "b"
    assert cells["B3"]["value"] == "shared text" and cells["B3"]["kind"] == "s"
    assert (
        cells["C2"]["formula"] == "SUM(A2:B2)" and cells["C2"]["cached_value"] == "30"
    )
    assert cells["C2"]["formula_attributes"] == {"ca": "1"}
    assert not cells["C2"]["editable"] and not cells["A4"]["editable"]
    assert view["sheets"][0]["merged_ranges"] == ["A4:B4"]
    assert view["sheets"][1]["cells"][0]["cached_value"] == "60"
    logger.info("xlsx_golden_verified sheets=2 formula_cache_preserved=True")


def test_rewrite_preserves_formulas_caches_styles_and_other_parts():
    """Reopen output independently and retain exact formula/cache and untouched member bytes."""
    data = GOLDEN.read_bytes()
    edits = [
        {"sheet_id": 1, "cell": "A2", "kind": "number", "value": "99.5"},
        {"sheet_id": 1, "cell": "A1", "kind": "string", "value": "=SUM(1,2)"},
        {"sheet_id": 1, "cell": "A3", "kind": "boolean", "value": False},
        {"sheet_id": 1, "cell": "B3", "kind": "string", "value": " Đã sửa\t\n "},
    ]
    result = process_bytes(data, "rewrite", plan_for(data, edits))
    workbook = load_workbook(io.BytesIO(result), data_only=False)
    sheet = workbook["Dữ liệu"]
    assert sheet["A2"].value == 99.5 and sheet["A2"].number_format == "0.00"
    assert sheet["A1"].value == "=SUM(1,2)" and sheet["A1"].data_type == "s"
    assert sheet["A1"].font.bold and sheet["A1"].fill.fgColor.rgb == "00FFFF00"
    assert sheet["A3"].value is False and sheet["B3"].value == " Đã sửa\t\n "
    assert sheet["C2"].value == "=SUM(A2:B2)"
    assert workbook["Summary"]["A1"].value == "='Dữ liệu'!C2*2"
    assert sheet.freeze_panes == "B2" and sheet.column_dimensions["A"].width == 24
    assert str(sheet.merged_cells) == "A4:B4"
    cached = load_workbook(io.BytesIO(result), data_only=True)
    assert cached["Dữ liệu"]["C2"].value == 30 and cached["Summary"]["A1"].value == 60
    with (
        zipfile.ZipFile(io.BytesIO(data)) as before,
        zipfile.ZipFile(io.BytesIO(result)) as after,
    ):
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert before.read(name) == after.read(name), name
        old, new = [
            etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            for archive in (before, after)
        ]
        old_formula = old.find(".//" + S + 'c[@r="C2"]')
        new_formula = new.find(".//" + S + 'c[@r="C2"]')
        assert etree.tostring(old_formula) == etree.tostring(new_formula)
    assert process_bytes(result)["formula_cache_status"] == CACHE_STATUS
    assert GOLDEN.read_bytes() == data


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "coordinate",
        "row",
        "column",
        "boolean_index",
        "nan",
        "overflow",
        "underflow",
        "numeric_type",
        "boolean_type",
        "nul",
        "surrogate",
        "formula_kind",
        "extra",
    ],
)
def test_plan_rejects_invalid_literal_edits(kind):
    """Refuse coercion, formula input, invalid XML/coordinates and unrepresentable numbers."""
    plan = plan_for(GOLDEN.read_bytes())
    edit = plan["edits"][0]
    if kind == "duplicate":
        plan["edits"] *= 2
    elif kind in ("coordinate", "row", "column"):
        edit["cell"] = {"coordinate": "a1", "row": "A1048577", "column": "XFE1"}[kind]
    elif kind == "boolean_index":
        edit["sheet_id"] = True
    elif kind in ("nan", "overflow", "underflow"):
        edit["value"] = {"nan": "NaN", "overflow": "1e999", "underflow": "1e-999"}[kind]
    elif kind == "numeric_type":
        edit["value"] = 2.5
    elif kind == "boolean_type":
        edit.update(kind="boolean", value="false")
    elif kind in ("nul", "surrogate"):
        edit.update(kind="string", value="\0" if kind == "nul" else "\ud800")
    elif kind == "formula_kind":
        edit.update(kind="formula", value="SUM(A1)")
    else:
        plan["path"] = "/etc/passwd"
    with pytest.raises(StoragePolicyError, match="invalid_xlsx_edits"):
        validate_plan(plan)


@pytest.mark.parametrize(
    "kind",
    [
        "malformed",
        "external",
        "dtd",
        "macro",
        "nested",
        "xml_limit",
        "cells_limit",
        "text_limit",
        "bad_string",
        "bad_style",
        "duplicate_cell",
        "formula",
        "merged",
        "missing",
        "signed",
        "stale",
    ],
)
def test_actual_unsafe_or_unsupported_workbooks(kind):
    """Assert exact fail-closed outcomes for real hostile, oversized and unsupported packages."""
    data = GOLDEN.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        main = source.read("xl/worksheets/sheet1.xml")
        rels = source.read("xl/_rels/workbook.xml.rels")
    operation = "read"
    if kind == "malformed":
        data = b"not-xlsx"
    elif kind == "external":
        data = mutate_package(
            data,
            {
                "xl/_rels/workbook.xml.rels": rels.replace(
                    b'Target="worksheets/sheet1.xml"',
                    b'Target="https://example.invalid/a" TargetMode="External"',
                )
            },
        )
    elif kind == "dtd":
        data = mutate_package(
            data,
            {
                "xl/worksheets/sheet1.xml": b'<!DOCTYPE worksheet [<!ENTITY x "hostile">]>'
                + main
            },
        )
    elif kind == "macro":
        data = mutate_package(data, {"xl/vbaProject.bin": b"hostile"})
    elif kind == "nested":
        data = mutate_package(data, {"xl/nested.bin": b"PK\x03\x04hostile"})
    elif kind == "xml_limit":
        data = mutate_package(
            data,
            {
                "xl/worksheets/sheet1.xml": main.replace(
                    b"Xin ch", b"A" * (2 * 1024 * 1024) + b"Xin ch"
                )
            },
        )
    elif kind == "cells_limit":
        root = etree.fromstring(main)
        sheetdata = root.find(S + "sheetData")
        for row in list(sheetdata):
            sheetdata.remove(row)
        for number in range(1, 5):
            row = etree.SubElement(sheetdata, S + "row", r=str(number))
            for column in range(1, 12502):
                etree.SubElement(
                    row, S + "c", r=get_column_letter(column) + str(number)
                )
        data = mutate_package(data, {"xl/worksheets/sheet1.xml": etree.tostring(root)})
    elif kind == "text_limit":
        root = etree.fromstring(main)
        for number in range(10, 51):
            row = etree.SubElement(root.find(S + "sheetData"), S + "row", r=str(number))
            cell = etree.SubElement(row, S + "c", r="A" + str(number), t="inlineStr")
            etree.SubElement(etree.SubElement(cell, S + "is"), S + "t").text = (
                "a" * 30000
            )
        data = mutate_package(data, {"xl/worksheets/sheet1.xml": etree.tostring(root)})
    elif kind == "bad_string":
        data = mutate_package(
            data, {"xl/worksheets/sheet1.xml": main.replace(b"<v>0</v>", b"<v>999</v>")}
        )
    elif kind == "bad_style":
        data = mutate_package(
            data, {"xl/worksheets/sheet1.xml": main.replace(b's="1"', b's="999"')}
        )
    elif kind == "duplicate_cell":
        root = etree.fromstring(main)
        root.find(S + "sheetData/" + S + "row").append(
            copy.deepcopy(root.find(".//" + S + "c"))
        )
        data = mutate_package(data, {"xl/worksheets/sheet1.xml": etree.tostring(root)})
    else:
        operation = "rewrite"
    plan = plan_for(data)
    if kind == "formula":
        plan["edits"][0]["cell"] = "C2"
    elif kind == "merged":
        plan["edits"][0]["cell"] = "A4"
    elif kind == "missing":
        plan["edits"][0]["cell"] = "Z99"
    elif kind == "signed":
        data = mutate_package(data, {"_xmlsignatures/test.xml": b"<signature/>"})
        plan = plan_for(data)
    elif kind == "stale":
        plan["source_sha256"] = "0" * 64
    expected = (
        ("xlsx_limits_exceeded", 413)
        if kind.endswith("_limit")
        else ("unsupported_xlsx_edit", 422)
        if kind in ("formula", "merged", "signed")
        else ("xlsx_edit_not_found", 422)
        if kind == "missing"
        else ("xlsx_source_changed", 409)
        if kind == "stale"
        else ("invalid_xlsx_content", 415)
    )
    with pytest.raises(StoragePolicyError) as error:
        process_bytes(data, operation, plan)
    assert (error.value.code, error.value.status_code) == expected


def test_view_protocol_and_private_logs(caplog):
    """Reject forged formula editability and keep lexical document data out of audit logs."""
    with caplog.at_level(logging.INFO):
        view = process_bytes(GOLDEN.read_bytes())
    assert "xlsx_read_completed" in caplog.text and "Xin chào" not in caplog.text
    formula = next(c for c in view["sheets"][0]["cells"] if c["cell"] == "C2")
    formula["editable"] = True
    with pytest.raises(StoragePolicyError, match="xlsx_processing_unavailable"):
        validate_view(view)


@pytest.mark.parametrize(
    "mode",
    ["timeout", "os_error", "crash", "json", "large", "unknown_error", "array_error"],
)
def test_parent_failure_protocol_is_sanitized(monkeypatch, mode):
    """Reject malformed replies without leaking text and ensure metadata stays out of argv/env."""

    def worker(command, **kwargs):
        """Emulate a broken isolated worker while checking its parent-side descriptor contract."""
        assert "Đã sửa" not in " ".join(command)
        assert kwargs["env"] == {} and kwargs["pass_fds"]
        assert "--ro-bind-data" in command
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if mode == "os_error":
            raise OSError("private-detail")
        payload = {
            "json": b"broken",
            "large": b"x" * (module.MAX_OUTPUT_BYTES + 1),
            "unknown_error": b'{"error":"private-detail"}',
            "array_error": b'{"error":[]}',
        }.get(mode, b"{}")
        kwargs["stdout"].write(payload)
        return SimpleNamespace(returncode=1 if mode == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", worker)
    with pytest.raises(StoragePolicyError) as error:
        process_bytes(GOLDEN.read_bytes())
    assert error.value.code in (
        "xlsx_processing_unavailable",
        "xlsx_processing_timeout",
    )


def test_worker_kernel_limits_and_readonly_plan(monkeypatch):
    """Inspect real kernel budgets and private metadata mounts at the parser entrypoint."""
    sandbox = module.sandbox_command
    probe = '''
"""Inspect the production XLSX worker boundary without exposing host secrets."""
import os, resource
from src.infrastructure import file_content_verifier, xlsx_worker
from src.infrastructure.file_verifier import VERIFIER_MEMORY_BYTES, VERIFIER_CPU_SECONDS
original = file_content_verifier.verify_ooxml
def inspect_limits(*args):
    """Verify limits, private mounts and cleared environment before actual parsing."""
    assert resource.getrlimit(resource.RLIMIT_AS) == (VERIFIER_MEMORY_BYTES, VERIFIER_MEMORY_BYTES)
    assert resource.getrlimit(resource.RLIMIT_CPU) == (VERIFIER_CPU_SECONDS, VERIFIER_CPU_SECONDS+1)
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (25*1024*1024,25*1024*1024)
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0,0)
    assert not any('VAULT' in key or 'DATABASE' in key for key in os.environ)
    assert not os.path.exists('/app/data') and not os.path.exists('/home/korosaki-ryukai')
    try:
        descriptor = os.open('/request.json', os.O_WRONLY)
    except OSError:
        pass
    else:
        os.close(descriptor)
        raise AssertionError('editable plan mount')
    return original(*args)
file_content_verifier.verify_ooxml = inspect_limits
raise SystemExit(xlsx_worker.main())
'''

    def command(arguments):
        """Replace only the trusted worker entrypoint and retain production mount construction."""
        return sandbox(["/venv/bin/python", "-c", probe, "read"])

    monkeypatch.setattr(module, "sandbox_command", command)
    assert process_bytes(GOLDEN.read_bytes())["processor"] == XLSX_VERSION


def test_real_timeout_does_not_leave_workers(monkeypatch):
    """Reap a real stalled sandbox so source descriptors and metadata mounts cannot outlive it."""
    from uuid import uuid4

    marker = "xlsx-timeout-" + uuid4().hex
    sandbox = module.sandbox_command

    def stalled(arguments):
        """Replace parsing with a stalled process inside the same isolated namespaces."""
        return sandbox(
            ["/venv/bin/python", "-c", "import time; time.sleep(30)", marker]
        )

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "XLSX_WALL_SECONDS", 0.2)
    with pytest.raises(StoragePolicyError, match="xlsx_processing_timeout"):
        process_bytes(GOLDEN.read_bytes())
    for process in Path("/proc").iterdir():
        if process.name.isdecimal():
            try:
                assert marker.encode() not in (process / "cmdline").read_bytes()
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
