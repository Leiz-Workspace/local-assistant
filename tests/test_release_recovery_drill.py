"""Verify restore namespace guards, private artifacts and vector export/restore cleanup before any actual infrastructure drill."""

import copy
import json

import httpx
import pytest

from scripts import release_recovery_drill as module


@pytest.mark.parametrize(
    "name",
    [
        "local_assistant",
        "postgres",
        "production",
        "la_restore_probe_bad",
        "la_restore_probe_" + "a" * 31,
    ],
)
def test_target_guard_cannot_select_original_collection(name):
    """Refuse original or malformed namespace names before any vector deletion request."""
    with pytest.raises(ValueError):
        module.guarded_collection(name)


def test_private_artifact_creation_is_exclusive_bounded_and_no_follow(tmp_path):
    """Retain original bytes and reject overwrite, symlink substitution and oversized artifact payloads."""
    path = tmp_path / "archive"
    module.private_write(path, b"owned fixture")
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        module.private_write(path, b"replace")
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        module.private_write(link, b"replace")
    with pytest.raises(ValueError):
        module.private_write(tmp_path / "huge", b"x" * (64 * 1024 * 1024 + 1))
    assert path.read_bytes() == b"owned fixture" and not (tmp_path / "huge").exists()


class VectorFixture:
    """Model only finite authored collection/index/point requests and preserve failure cleanup observations."""

    def __init__(self, fail=False, existing=False):
        """Select optional second-upload failure or pre-existing original collection without real infrastructure access."""
        self.state = {"original": {}} if existing else {}
        self.fail = fail
        self.uploads = 0
        self.deleted = []

    def handle(self, request):
        """Serve only the logical export/restore API shape and fail unexpected operations loudly."""
        path = request.url.path.split("/")
        if request.url.path == "/collections":
            return httpx.Response(
                200,
                json=dict(
                    result=dict(collections=[dict(name=name) for name in self.state])
                ),
            )
        name = path[2]
        assert module.guarded_collection(name) == name
        if request.method == "DELETE":
            self.deleted.append(name)
            self.state.pop(name, None)
            return httpx.Response(200, json=dict(result=True))
        body = json.loads(request.content) if request.content else None
        if len(path) == 3 and request.method == "PUT":
            self.state[name] = dict(points=[], indexes={})
        elif len(path) == 3 and request.method == "GET":
            schema = {
                field: dict(data_type="keyword", points=len(self.state[name]["points"]))
                for field in self.state[name]["indexes"]
            }
            return httpx.Response(200, json=dict(result=dict(payload_schema=schema)))
        elif path[-1] == "index":
            self.state[name]["indexes"][body["field_name"]] = "keyword"
        elif path[-1] == "points" and request.method == "PUT":
            self.uploads += 1
            if self.fail and self.uploads == 2:
                return httpx.Response(500, json=dict(error="PRIVATE-VECTOR-CANARY"))
            self.state[name]["points"] = copy.deepcopy(body["points"])
        elif path[-1] == "scroll":
            return httpx.Response(
                200,
                json=dict(
                    result=dict(
                        points=self.state[name]["points"], next_page_offset=None
                    )
                ),
            )
        else:
            raise AssertionError("Unexpected fixture request")
        return httpx.Response(200, json=dict(result=True))


@pytest.mark.parametrize("fail", [False, True])
def test_vector_canary_roundtrip_or_failure_retires_only_two_owned_targets(
    tmp_path, fail, caplog
):
    """Restore exact nonempty points/indexes or preserve failed evidence while cleaning only names minted by this drill."""
    fixture = VectorFixture(fail=fail)
    with httpx.Client(
        base_url="http://fixture", transport=httpx.MockTransport(fixture.handle)
    ) as client:
        if fail:
            with pytest.raises(RuntimeError):
                module.vector_drill(client, tmp_path)
        else:
            result = module.vector_drill(client, tmp_path)
            assert (
                result["canary_points_restored"] == 3
                and result["keyword_indexes_verified"] == 2
            )
    assert fixture.state == {} and len(set(fixture.deleted)) == 2
    assert (tmp_path / "vector-canary-backup.json").exists()
    assert "PRIVATE-VECTOR-CANARY" not in caplog.text


def test_existing_original_collection_stops_drill_without_any_mutation(tmp_path):
    """Fail closed when actual vector inventory no longer matches the reviewed empty baseline."""
    fixture = VectorFixture(existing=True)
    with httpx.Client(
        base_url="http://fixture", transport=httpx.MockTransport(fixture.handle)
    ) as client:
        with pytest.raises(RuntimeError, match="empty_vector_baseline"):
            module.vector_drill(client, tmp_path)
    assert (
        fixture.state == {"original": {}}
        and not fixture.deleted
        and fixture.uploads == 0
    )


def test_config_object_roundtrip_restores_only_allowlisted_bytes(tmp_path, monkeypatch):
    """Verify separate private outputs and exact metadata pairing without reading arbitrary secrets or restoring over sources."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "configs").mkdir()
    for name in module.CONFIGS:
        (source / name).write_bytes(b"Non-secret authored config fixture.\n")
    original = {name: (source / name).read_bytes() for name in module.CONFIGS}
    target = tmp_path / "drill"
    target.mkdir(mode=0o700)
    monkeypatch.chdir(source)
    result = module.config_object_drill(target)
    assert len(result["config_sha256"]) == 4
    assert (target / "object-source.bin").read_bytes() == (
        target / "object-restored.bin"
    ).read_bytes()
    assert original == {name: (source / name).read_bytes() for name in module.CONFIGS}


def test_config_source_symlink_is_rejected_without_copying_target(
    tmp_path, monkeypatch
):
    """Reject a substituted allowlisted config file rather than following it into an unreviewed private source."""
    (tmp_path / "configs").mkdir()
    private = tmp_path / "private"
    private.write_bytes(b"PRIVATE-CONFIG-CANARY")
    (tmp_path / module.CONFIGS[0]).symlink_to(private)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="config_invalid"):
        module.config_object_drill(output)
    assert not list((output / "config-backup").iterdir())


def test_acceptance_checks_contain_no_assert_statements():
    """Keep every acceptance check active under python -O, where assert statements are stripped."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(module.__file__).read_text())
    assert not [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def test_failed_check_still_raises_its_code_under_optimized_python():
    """Prove the coded check raises in an optimized interpreter that would strip an assert."""
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from scripts.release_recovery_drill import require;"
            "require(False, 'recovery_original_changed')",
        ],
        cwd=Path(module.__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "RuntimeError: recovery_original_changed" in result.stderr


def test_unknown_check_code_is_refused_even_when_the_check_passes():
    """Keep the failure vocabulary closed so a typo cannot ship an unreviewed code."""
    with pytest.raises(ValueError, match="recovery_check_code_unknown"):
        module.require(True, "recovery_typo")
    module.require(True, "recovery_original_changed")


class TamperedVectorFixture(VectorFixture):
    """Serve one controlled export, restore or index fault after real fixture handling."""

    def __init__(self, fault):
        """Select the fault to inject into an otherwise valid logical export/restore."""
        super().__init__()
        self.fault = fault
        self.scrolls = 0

    def handle(self, request):
        """Alter only the selected response or stored state."""
        response = super().handle(request)
        path = request.url.path.split("/")
        if path[-1] == "scroll":
            self.scrolls += 1
            body = response.json()
            if self.fault == "export" and self.scrolls == 1:
                body["result"]["next_page_offset"] = 4
            if self.fault == "restore" and self.scrolls == 2:
                body["result"]["points"][0]["payload"]["owner_id"] = "tampered"
            return httpx.Response(200, json=body)
        if len(path) == 3 and request.method == "GET" and self.fault != "export":
            body = response.json()
            schema = body["result"]["payload_schema"]
            if self.fault == "index_type":
                schema["owner_id"]["data_type"] = "integer"
            elif self.fault == "index_missing" and path[2] == sorted(self.state)[1]:
                schema.pop("source_sha256")
            return httpx.Response(200, json=body)
        return response


@pytest.mark.parametrize(
    "fault,code",
    [
        ("export", "recovery_vector_export_incomplete"),
        ("restore", "recovery_vector_restore_mismatch"),
        ("index_type", "recovery_vector_index_mismatch"),
        ("index_missing", "recovery_vector_index_mismatch"),
    ],
)
def test_vector_check_failures_raise_codes_and_still_retire_targets(
    tmp_path, fault, code
):
    """Fail each logical vector acceptance check with its code and still delete only the two owned targets."""
    fixture = TamperedVectorFixture(fault)
    with httpx.Client(
        base_url="http://fixture", transport=httpx.MockTransport(fixture.handle)
    ) as client:
        with pytest.raises(RuntimeError, match=code):
            module.vector_drill(client, tmp_path)
    assert fixture.state == {} and len(set(fixture.deleted)) == 2


@pytest.mark.parametrize(
    "target,code",
    [
        ("config-restored", "recovery_config_restore_mismatch"),
        ("object-restored.bin", "recovery_object_restore_mismatch"),
    ],
)
def test_config_or_object_restore_mismatch_raises_its_code(
    tmp_path, monkeypatch, target, code
):
    """Refuse a restored config or object whose bytes differ from the backed-up source."""
    source = tmp_path / "source"
    (source / "configs").mkdir(parents=True)
    for name in module.CONFIGS:
        (source / name).write_bytes(b"Non-secret authored config fixture.\n")
    output = tmp_path / "drill"
    output.mkdir(mode=0o700)
    monkeypatch.chdir(source)
    original = module.private_write

    def corrupting_write(path, raw):
        """Flip the restored copy's bytes for the selected target only."""
        if target in str(path):
            raw = b"corrupted " + raw
        original(path, raw)

    monkeypatch.setattr(module, "private_write", corrupting_write)
    with pytest.raises(RuntimeError, match=code):
        module.config_object_drill(output)


class FakeOperator:
    """Model the restore helper's reads and outputs without Docker or PostgreSQL."""

    instances = []

    def __init__(self, directory):
        """Record the private postgres directory and the scripted observations."""
        directory.mkdir(mode=0o700)
        self.directory = directory
        self.container, self.admin = "postgres", "admin"
        self.rows = [{"assistant.messages": "rows"}]
        self.security = ["acl"]
        self.answers = {}
        self.verified = False
        FakeOperator.instances.append(self)

    def require_quiet(self):
        """Report quiet consumers."""

    def fingerprint(self, database):
        """Return the next scripted row fingerprint, repeating the last."""
        return self.rows.pop(0) if len(self.rows) > 1 else self.rows[0]

    def security_fingerprint(self, database):
        """Return the next scripted security fingerprint, repeating the last."""
        return self.security.pop(0) if len(self.security) > 1 else self.security[0]

    def sql(self, database, query):
        """Return the scripted revision and probe-database count."""
        if "alembic_version" in query:
            revisions = self.answers.setdefault("revision", ["0006"])
            return revisions.pop(0) if len(revisions) > 1 else revisions[0]
        return self.answers.get("probes", "0")

    def private_output(self, name, arguments):
        """Write a small private archive fixture."""
        path = self.directory / name
        path.write_bytes(b"archive fixture")
        return path

    def verify_restore(self, archive, rows, security):
        """Record that the isolated restore was verified."""
        self.verified = True

    def save_manifest(self):
        """Accept the manifest save."""


@pytest.mark.parametrize(
    "fault,code",
    [
        (None, None),
        ("backup", "recovery_source_changed_during_backup"),
        ("original", "recovery_original_changed"),
        ("security", "recovery_original_changed"),
        ("revision", "recovery_schema_revision_changed"),
        ("probe", "recovery_probe_database_retained"),
    ],
)
def test_drill_acceptance_checks_raise_codes_and_withhold_the_result(
    tmp_path, monkeypatch, fault, code
):
    """Complete only when the original stays unchanged; otherwise raise the closed code and write no result."""
    FakeOperator.instances.clear()

    def operator(directory):
        """Build the fake operator with the selected scripted fault."""
        fake = FakeOperator(directory)
        rows, changed = {"assistant.messages": "rows"}, {"assistant.messages": "new"}
        if fault == "backup":
            fake.rows = [rows, changed]
        elif fault == "original":
            fake.rows = [rows, rows, changed]
        elif fault == "security":
            fake.security = ["acl", "acl", "changed"]
        elif fault == "revision":
            fake.answers["revision"] = ["0006", "0007"]
        elif fault == "probe":
            fake.answers["probes"] = "1"
        return fake

    class Client:
        """Stand in for the vector client without opening a connection."""

        def __init__(self, **options):
            """Accept the fixed client options."""

        def __enter__(self):
            """Return the stub client."""
            return self

        def __exit__(self, *details):
            """Close nothing."""
            return False

    monkeypatch.setattr(module, "RecoveryAcceptance", operator)
    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(module, "vector_drill", lambda client, root: dict(vectors=1))
    monkeypatch.setattr(module, "config_object_drill", lambda root: dict(configs=4))
    root = tmp_path / "drill"
    if code is None:
        result = module.drill(root, "k" * 40)
        assert result["status"] == "COMPLETE"
        assert (root / "result.json").exists()
        return
    with pytest.raises(RuntimeError, match=code):
        module.drill(root, "k" * 40)
    assert not (root / "result.json").exists()
    assert FakeOperator.instances[0].verified is (fault != "backup")
