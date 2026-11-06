"""Exclude tests that need private local resources when running on GitHub-hosted runners."""

import logging
from pathlib import Path

import pytest

LOGGER = logging.getLogger(__name__)
LIST = Path(__file__).with_name("hosted-runner-exclusions.txt")


def load_entries(path):
    """Parse `<path or node id>  # <reason>` lines, rejecting entries without a stated reason."""
    entries = {}
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


class HostedExclusions:
    """Ignore whole files at collection and deselect individual node ids, reporting unmatched entries."""

    def __init__(self, config):
        """Split entries into file-level and node-level targets relative to the root directory."""
        self.root = config.rootpath
        entries = load_entries(LIST)
        self.files = {k for k in entries if "::" not in k}
        self.nodes = {k for k in entries if "::" in k}
        self.used = set()
        self.deselected = 0

    def pytest_ignore_collect(self, collection_path, config):
        """Skip importing excluded files, since some contact local services at import time."""
        try:
            relative = collection_path.relative_to(self.root).as_posix()
        except ValueError:
            return None
        if relative in self.files:
            self.used.add(relative)
            return True
        return None

    def pytest_collection_modifyitems(self, config, items):
        """Deselect excluded node ids, including every parametrization of an excluded test."""
        kept, dropped = [], []
        for item in items:
            base = item.nodeid.split("[", 1)[0]
            match = item.nodeid if item.nodeid in self.nodes else base
            if match in self.nodes:
                self.used.add(match)
                dropped.append(item)
            else:
                kept.append(item)
        if dropped:
            config.hook.pytest_deselected(items=dropped)
            items[:] = kept
        self.deselected = len(dropped)

    def unmatched(self):
        """Entries whose file exists in this checkout but matched nothing (absent files are expected on older revisions)."""
        return sorted(
            entry
            for entry in (self.files | self.nodes) - self.used
            if (self.root / entry.split("::", 1)[0]).exists()
        )

    def pytest_terminal_summary(self, terminalreporter):
        """Report exactly how much was excluded instead of implying full coverage."""
        terminalreporter.write_line(
            f"hosted-runner exclusions: {len(self.used & self.files)} files ignored, "
            f"{self.deselected} tests deselected (see .github/ci/{LIST.name})"
        )
        stale = self.unmatched()
        if stale:
            terminalreporter.write_line(
                f"hosted-runner exclusions: {len(stale)} entries matched nothing: "
                + ", ".join(stale),
                yellow=True,
            )


def pytest_configure(config):
    """Register the exclusion plugin for this run."""
    config.pluginmanager.register(HostedExclusions(config), "hosted-exclusions")
    LOGGER.info("hosted_runner_exclusions_enabled")
