"""Hold verified-summary inputs' raw model outputs in owner-bound process memory with LRU and TTL bounds (ADR-192)."""

import logging
import time
from collections import OrderedDict

LOGGER = logging.getLogger(__name__)
MAX_ENTRIES = 64
TTL_SECONDS = 1800


class SummaryCache:
    """Keep at most 64 entries for 1,800 seconds; keys always include the authenticated owner."""

    def __init__(self, *, clock=time.monotonic):
        """Start empty with an injectable clock for tests."""
        self.clock = clock
        self.entries = OrderedDict()

    def _prune(self):
        """Drop expired entries."""
        now = self.clock()
        for key in [
            key for key, (expires, _) in self.entries.items() if expires <= now
        ]:
            del self.entries[key]

    def get(self, owner, key):
        """Return the owner's live entry and mark it recently used, or None."""
        self._prune()
        entry = self.entries.get((owner, key))
        if entry is None:
            return None
        self.entries.move_to_end((owner, key))
        return entry[1]

    def put(self, owner, key, value):
        """Store one entry for the owner, evicting the least recently used entry when full."""
        self._prune()
        self.entries[(owner, key)] = (self.clock() + TTL_SECONDS, value)
        self.entries.move_to_end((owner, key))
        while len(self.entries) > MAX_ENTRIES:
            self.entries.popitem(last=False)

    def purge(self, owner):
        """Remove every entry of one owner and return how many were removed."""
        keys = [key for key in self.entries if key[0] == owner]
        for key in keys:
            del self.entries[key]
        LOGGER.info("summary_cache_purged count=%d", len(keys))
        return len(keys)

    def close(self):
        """Clear all entries at shutdown."""
        self.entries.clear()


class BoundSummaryCache:
    """Expose get/put for one authenticated owner only."""

    def __init__(self, cache, owner):
        """Bind the shared cache to the caller's principal."""
        self.cache, self.owner = cache, owner

    def get(self, key):
        """Read the owner's entry."""
        return self.cache.get(self.owner, key)

    def put(self, key, value):
        """Write the owner's entry."""
        self.cache.put(self.owner, key, value)
