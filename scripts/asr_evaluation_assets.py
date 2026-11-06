"""Fetch only pinned public D68 candidate/corpus artifacts into an owned private evaluation cache without selecting or replacing models."""

import argparse
import hashlib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path("data/backups/d68-asr-evaluation").resolve()
PLAN = Path("configs/asr-evaluation-candidates.json")
REPOSITORIES = {"Qwen/Qwen3-ASR-0.6B", "Systran/faster-whisper-small", "google/fleurs"}
MAX_ARTIFACT = 2 * 1024**3


class AssetError(Exception):
    """Expose finite provisioning errors without credentials, signed redirect URLs or upstream response bodies."""

    def __init__(self, code):
        """Record a controlled artifact failure without claiming an ASR benchmark result."""
        self.code = (
            code
            if code
            in {
                "artifact_spec_invalid",
                "artifact_path_invalid",
                "artifact_existing_invalid",
                "artifact_partial_exists",
                "artifact_response_invalid",
                "artifact_hash_mismatch",
                "artifact_fetch_failed",
            }
            else "artifact_fetch_failed"
        )
        super().__init__(self.code)
        logger.warning("asr_evaluation_asset_rejected code=%s", self.code)


def allowed_url(url):
    """Allow only credential-free HTTPS Hugging Face/CDN endpoints before following a public artifact redirect."""
    value = urllib.parse.urlsplit(url)
    host = value.hostname or ""
    return (
        value.scheme == "https"
        and value.username is None
        and value.password is None
        and value.port in (None, 443)
        and (
            host == "huggingface.co"
            or host == "cdn-lfs.huggingface.co"
            or host.endswith(".hf.co")
        )
    )


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    """Keep every public artifact redirect inside fixed HTTPS provider domains without forwarding user credentials."""

    def redirect_request(self, request, response, code, message, headers, url):
        """Refuse unexpected/private/plaintext locations before issuing a redirected request."""
        if not allowed_url(url):
            raise AssetError("artifact_response_invalid")
        return super().redirect_request(request, response, code, message, headers, url)


def opener():
    """Build a direct public HTTPS client with no ambient proxies, cookies, auth handlers or Hugging Face token lookup."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), PublicRedirect()
    )


def source_url(repository, revision, path, *, dataset=False):
    """Construct one known pinned source URI without accepting arbitrary repositories, revisions or traversal paths."""
    parts = path.split("/") if type(path) is str else []
    if (
        repository not in REPOSITORIES
        or type(revision) is not str
        or re.fullmatch("[0-9a-f]{40}", revision) is None
        or not parts
        or any(
            not part
            or part in {".", ".."}
            or "\\" in part
            or any(ord(c) < 32 for c in part)
            for part in parts
        )
    ):
        raise AssetError("artifact_spec_invalid")
    prefix = "datasets/" if dataset else ""
    return (
        f"https://huggingface.co/{prefix}{repository}/resolve/{revision}/"
        + urllib.parse.quote(path, safe="/")
        + "?download=true"
    )


def validate_spec(spec):
    """Require one bounded leaf artifact with a complete expected LFS SHA256 or ordinary Git blob identity."""
    name = spec.get("filename")
    size = spec.get("bytes")
    lfs = spec.get("lfs_sha256")
    blob = spec.get("git_blob_sha1")
    if (
        type(name) is not str
        or name in {"", ".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(c) < 32 for c in name)
    ):
        raise AssetError("artifact_spec_invalid")
    if type(size) is not int or not 1 <= size <= MAX_ARTIFACT:
        raise AssetError("artifact_spec_invalid")
    if lfs is not None:
        if type(lfs) is not str or re.fullmatch("[0-9a-f]{64}", lfs) is None:
            raise AssetError("artifact_spec_invalid")
    elif type(blob) is not str or re.fullmatch("[0-9a-f]{40}", blob) is None:
        raise AssetError("artifact_spec_invalid")
    return name, size


def file_hashes(path, size):
    """Hash complete local bytes using both SHA256 and ordinary Git blob framing without reading a large artifact into memory."""
    sha = hashlib.sha256()
    blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
    with path.open("rb") as source:
        while raw := source.read(1024**2):
            sha.update(raw)
            blob.update(raw)
    return sha.hexdigest(), blob.hexdigest()


def verify_file(path, spec):
    """Refuse symlink/nonregular/wrong-size or changed existing artifacts instead of adopting or overwriting them."""
    _, size = validate_spec(spec)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise AssetError("artifact_existing_invalid")
    sha, blob = file_hashes(path, size)
    if (spec.get("lfs_sha256") is not None and sha != spec["lfs_sha256"]) or (
        spec.get("lfs_sha256") is None and blob != spec["git_blob_sha1"]
    ):
        raise AssetError("artifact_hash_mismatch")
    return sha


def fetch(url, directory, spec, *, client=None):
    """Fetch one exact pinned artifact privately and publish complete verified bytes without replacing any existing path."""
    name, size = validate_spec(spec)
    if not allowed_url(url):
        raise AssetError("artifact_spec_invalid")
    directory = Path(directory)
    if any(
        parent.is_symlink() for parent in [directory, *directory.absolute().parents]
    ):
        raise AssetError("artifact_path_invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir():
        raise AssetError("artifact_path_invalid")
    destination = directory / name
    partial = directory / (name + ".partial")
    if destination.exists() or destination.is_symlink():
        sha = verify_file(destination, spec)
        logger.info("asr_artifact_existing_verified artifact=%s bytes=%d", name, size)
        return dict(filename=name, bytes=size, sha256=sha, status="EXISTING_VERIFIED")
    if partial.exists() or partial.is_symlink():
        raise AssetError("artifact_partial_exists")
    descriptor = os.open(
        partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    started = datetime.now(UTC).isoformat()
    received = 0
    logger.info("asr_artifact_fetch_started artifact=%s expected_bytes=%d", name, size)
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "local-assistant-offline-asr-evaluation/1",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
            },
        )
        with os.fdopen(descriptor, "wb") as output:
            with (client if client is not None else opener()).open(
                request, timeout=30
            ) as response:
                if response.status != 200 or not allowed_url(response.geturl()):
                    raise AssetError("artifact_response_invalid")
                while raw := response.read(min(1024**2, size - received + 1)):
                    received += len(raw)
                    if received > size:
                        raise AssetError("artifact_response_invalid")
                    output.write(raw)
                    if received // (32 * 1024**2) != (received - len(raw)) // (
                        32 * 1024**2
                    ):
                        logger.info(
                            "asr_artifact_fetch_progress artifact=%s received_bytes=%d",
                            name,
                            received,
                        )
            output.flush()
            os.fsync(output.fileno())
        if received != size:
            raise AssetError("artifact_response_invalid")
        sha = verify_file(partial, spec)
        # An exclusive link publishes verified bytes without replacing a concurrently created destination.
        os.link(partial, destination, follow_symlinks=False)
        partial.unlink()
        directory_fd = os.open(directory, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        logger.info("asr_artifact_fetch_complete artifact=%s bytes=%d", name, size)
        return dict(
            filename=name,
            bytes=size,
            sha256=sha,
            status="DOWNLOADED_VERIFIED",
            started_at_utc=started,
            finished_at_utc=datetime.now(UTC).isoformat(),
        )
    except AssetError:
        raise
    except Exception:
        raise AssetError("artifact_fetch_failed") from None


def metadata(url, *, client=None):
    """Read bounded public pinned repository metadata without executing remote code or printing signed URLs."""
    if not allowed_url(url):
        raise AssetError("artifact_spec_invalid")
    with (client if client is not None else opener()).open(
        urllib.request.Request(
            url, headers={"User-Agent": "local-assistant-offline-asr-evaluation/1"}
        ),
        timeout=20,
    ) as response:
        raw = response.read(1024**2 + 1)
    if len(raw) > 1024**2:
        raise AssetError("artifact_response_invalid")
    return json.loads(raw)


def corpus_specs(plan):
    """Resolve exact pinned original test TSV/archive metadata before downloading corpus bytes or choosing evaluation rows."""
    corpus = plan["corpus"]
    revision = corpus["revision"]
    repository = corpus["repository"]
    rows = []
    for language in corpus["languages"]:
        for folder, filename in [
            (f"data/{language}", "test.tsv"),
            (f"data/{language}/audio", "test.tar.gz"),
        ]:
            tree = metadata(
                f"https://huggingface.co/api/datasets/{repository}/tree/{revision}/{folder}?recursive=false&expand=false"
            )
            matches = [row for row in tree if row["path"] == folder + "/" + filename]
            if len(matches) != 1:
                raise AssetError("artifact_spec_invalid")
            item = matches[0]
            rows.append(
                dict(
                    language=language,
                    path=item["path"],
                    filename=filename,
                    bytes=item["size"],
                    git_blob_sha1=item["oid"],
                    lfs_sha256=item.get("lfs", {}).get("oid"),
                )
            )
    return rows


def provision(kind):
    """Provision only explicit evaluation artifacts in the owned cache while leaving all selected runtime configurations untouched."""
    plan = json.loads(PLAN.read_text())
    if (
        plan["status"] != "EVALUATION_ONLY_NOT_SELECTED"
        or plan["production_selection"] is not None
    ):
        raise AssetError("artifact_spec_invalid")
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = []
    if kind == "models":
        for candidate in plan["candidates"]:
            if candidate["id"] not in {"qwen3-asr-0.6b", "whisper-small-ct2"}:
                raise AssetError("artifact_spec_invalid")
            for spec in candidate["artifacts"]:
                value = fetch(
                    source_url(
                        candidate["repository"], candidate["revision"], spec["filename"]
                    ),
                    ROOT / "models" / candidate["id"] / candidate["revision"],
                    spec,
                )
                results.append(
                    dict(
                        candidate=candidate["id"],
                        revision=candidate["revision"],
                        artifact=value,
                    )
                )
    elif kind == "corpus":
        specs = corpus_specs(plan)
        for spec in specs:
            value = fetch(
                source_url(
                    plan["corpus"]["repository"],
                    plan["corpus"]["revision"],
                    spec["path"],
                    dataset=True,
                ),
                ROOT / "corpus" / spec["language"],
                spec,
            )
            results.append(
                dict(
                    language=spec["language"],
                    source_path=spec["path"],
                    expected_spec=spec,
                    artifact=value,
                )
            )
    else:
        raise AssetError("artifact_spec_invalid")
    target = ROOT / (kind + "-provisioned.json")
    raw = (
        json.dumps(
            dict(
                description="Verified pinned public offline ASR evaluation artifacts only; no selected/deployed model or previous artifact replacement.",
                kind=kind,
                results=results,
            ),
            indent=2,
        )
        + "\n"
    ).encode()
    with target.open("xb") as output:
        output.write(raw)
    target.chmod(0o600)
    logger.info(
        "asr_offline_artifacts_provisioned kind=%s count=%d selected_models=0",
        kind,
        len(results),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["models", "corpus"], required=True)
    provision(parser.parse_args().kind)
