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
