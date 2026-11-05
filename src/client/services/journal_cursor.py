"""Consume append-only snapshot journals without replaying loaded history."""
from __future__ import annotations


class JournalCursor:
    def __init__(self, initial_records=()):
        records = list(initial_records)
        self._offset = len(records)
        self._tail = dict(records[-1]) if records else None

    def consume(self, records):
        if self._offset > len(records) or (self._offset and records[self._offset-1] != self._tail):
            self._offset = len(records)
        fresh = records[self._offset:]
        self._offset = len(records)
        self._tail = dict(records[-1]) if records else None
        return fresh
