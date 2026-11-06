"""Scope the suite for GitHub-hosted runners: exclude tests needing private local resources and quarantine known-intermittent ones."""

import logging
import os
from pathlib import Path

import pytest

LOGGER = logging.getLogger(__name__)
HERE = Path(__file__).parent
EXCLUSIONS = HERE / "hosted-runner-exclusions.txt"
QUARANTINE = HERE / "hosted-runner-quarantine.txt"
MODE_VARIABLE = "HOSTED_TEST_MODE"


def load_entries(path):
    """Parse `<path or node id>  # <reason>` lines, rejecting entries without a stated reason."""
    entries = {}
    if not path.exists():
        return entries
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        target, _, reason = line.partition("#")
        target, reason = target.strip(), reason.strip()
        if not target or not reason:
            raise pytest.UsageError(f"{path.name}:{number}: entry needs a '# reason'")
        if target in entries:
            raise pytest.UsageError(f"{path.name}:{number}: duplicate entry {target}")
        entries[target] = reason
    return entries


def split(entries):
    """Separate whole-file paths from node ids."""
    return {k for k in entries if "::" not in k}, {k for k in entries if "::" in k}


def matches(nodeid, files, nodes):
    """Return the entry matching a collected item, by node id, base node id or file."""
    base = nodeid.split("[", 1)[0]
    for candidate in (nodeid, base):
        if candidate in nodes:
            return candidate
    path = nodeid.split("::", 1)[0]
    return path if path in files else None


class HostedScope:
    """Exclusions are never run here; quarantined tests run only in the dedicated non-blocking job."""

    def __init__(self, config):
        """Load both lists and the requested mode (`main` by default, or `quarantine`)."""
        self.root = config.rootpath
        self.mode = os.environ.get(MODE_VARIABLE, "main")
        if self.mode not in {"main", "quarantine"}:
            raise pytest.UsageError(f"{MODE_VARIABLE} must be 'main' or 'quarantine'")
        self.excluded_files, self.excluded_nodes = split(load_entries(EXCLUSIONS))
        self.quarantine_files, self.quarantine_nodes = split(load_entries(QUARANTINE))
        self.used = set()
        self.counts = {"excluded": 0, "quarantined": 0, "outside quarantine": 0}

    def pytest_ignore_collect(self, collection_path, config):
        """Skip importing excluded files, since some contact local services at import time."""
        try:
            relative = collection_path.relative_to(self.root).as_posix()
        except ValueError:
            return None
        if relative in self.excluded_files:
            self.used.add(relative)
            return True
        return None

    def pytest_collection_modifyitems(self, config, items):
        """Deselect exclusions always, and quarantined tests in main mode (or everything else in quarantine mode)."""
        kept, dropped = [], []
        for item in items:
            # Files are normally ignored at collection; explicit path arguments bypass that hook.
            excluded = matches(item.nodeid, self.excluded_files, self.excluded_nodes)
            quarantined = matches(
                item.nodeid, self.quarantine_files, self.quarantine_nodes
            )
            for entry in (excluded, quarantined):
                if entry:
                    self.used.add(entry)
            if excluded:
                self.counts["excluded"] += 1
                dropped.append(item)
            elif (self.mode == "main") == bool(quarantined):
                self.counts["quarantined" if quarantined else "outside quarantine"] += 1
                dropped.append(item)
            else:
                kept.append(item)
        if dropped:
            config.hook.pytest_deselected(items=dropped)
            items[:] = kept

    def unmatched(self, args):
        """Entries inside the requested paths whose file exists but matched nothing (absent files are expected on older revisions)."""
        entries = (
            self.excluded_files
            | self.excluded_nodes
            | self.quarantine_files
            | self.quarantine_nodes
        )
        scopes = [(self.root / arg.split("::", 1)[0]).resolve() for arg in args] or [
            self.root
        ]
        stale = []
        for entry in entries - self.used:
            path = (self.root / entry.split("::", 1)[0]).resolve()
            if path.exists() and any(path.is_relative_to(scope) for scope in scopes):
                stale.append(entry)
        return sorted(stale)

    def pytest_terminal_summary(self, terminalreporter):
        """Report exactly what was left out instead of implying full coverage."""
        ignored = len(self.used & self.excluded_files)
        terminalreporter.write_line(
            f"hosted-runner scope ({self.mode}): {ignored} files ignored, "
            + ", ".join(
                f"{count} {name}" for name, count in self.counts.items() if count
            )
            + " (see .github/ci/)"
        )
        stale = self.unmatched(terminalreporter.config.args)
        if stale:
            terminalreporter.write_line(
                f"hosted-runner scope: {len(stale)} entries matched nothing: "
                + ", ".join(stale),
                yellow=True,
            )


def pytest_configure(config):
    """Register the hosted-runner scope plugin for this run."""
    config.pluginmanager.register(HostedScope(config), "hosted-scope")
    LOGGER.info("hosted_runner_scope_enabled")
