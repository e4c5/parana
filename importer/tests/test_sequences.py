"""Unit tests for sequences.py — derive_status and compress_lines."""

from __future__ import annotations

import pytest

from parana_importer.models import Line
from parana_importer.sequences import compress_lines, derive_status

# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------


class TestDeriveStatus:
    def test_not_covered_when_ci_zero(self):
        assert derive_status(mi=5, ci=0, mb=0, cb=0) == 0

    def test_not_covered_when_all_zero(self):
        assert derive_status(mi=0, ci=0, mb=0, cb=0) == 0

    def test_covered_all_instructions_no_branches(self):
        assert derive_status(mi=0, ci=3, mb=0, cb=0) == 2

    def test_covered_all_instructions_all_branches(self):
        assert derive_status(mi=0, ci=3, mb=0, cb=2) == 2

    def test_partly_covered_missed_instructions(self):
        assert derive_status(mi=2, ci=3, mb=0, cb=0) == 1

    def test_partly_covered_missed_branches(self):
        assert derive_status(mi=0, ci=3, mb=1, cb=1) == 1

    def test_partly_covered_both_missed(self):
        assert derive_status(mi=1, ci=1, mb=1, cb=0) == 1

    def test_ci_positive_mi_zero_mb_zero_is_covered(self):
        # Even with cb > 0, as long as mb == 0 it's COVERED.
        assert derive_status(mi=0, ci=1, mb=0, cb=4) == 2


# ---------------------------------------------------------------------------
# compress_lines
# ---------------------------------------------------------------------------


def _make_line(nr: int, mi: int, ci: int, mb: int = 0, cb: int = 0) -> Line:
    return Line(nr=nr, mi=mi, ci=ci, mb=mb, cb=cb)


class TestCompressLines:
    def test_empty_input(self):
        assert compress_lines([]) == []

    def test_single_line(self):
        seqs = compress_lines([_make_line(1, mi=0, ci=1)])
        assert len(seqs) == 1
        assert seqs[0].start_line == 1
        assert seqs[0].end_line == 1
        assert seqs[0].coverage_status == 2  # COVERED

    def test_all_same_status_consecutive(self):
        lines = [_make_line(i, mi=0, ci=1) for i in range(1, 6)]
        seqs = compress_lines(lines)
        assert len(seqs) == 1
        assert seqs[0].start_line == 1
        assert seqs[0].end_line == 5
        assert seqs[0].coverage_status == 2

    def test_mixed_statuses(self):
        lines = [
            _make_line(1, mi=0, ci=2),   # COVERED
            _make_line(2, mi=0, ci=2),   # COVERED
            _make_line(3, mi=2, ci=0),   # NOT_COVERED
            _make_line(4, mi=2, ci=0),   # NOT_COVERED
            _make_line(5, mi=1, ci=1),   # PARTLY_COVERED
        ]
        seqs = compress_lines(lines)
        assert len(seqs) == 3
        assert (seqs[0].start_line, seqs[0].end_line, seqs[0].coverage_status) == (1, 2, 2)
        assert (seqs[1].start_line, seqs[1].end_line, seqs[1].coverage_status) == (3, 4, 0)
        assert (seqs[2].start_line, seqs[2].end_line, seqs[2].coverage_status) == (5, 5, 1)

    def test_non_consecutive_lines_break_sequence(self):
        # Lines 1 and 3 share the same status but are not consecutive.
        lines = [
            _make_line(1, mi=0, ci=1),
            _make_line(3, mi=0, ci=1),
        ]
        seqs = compress_lines(lines)
        assert len(seqs) == 2
        assert seqs[0].start_line == 1
        assert seqs[0].end_line == 1
        assert seqs[1].start_line == 3
        assert seqs[1].end_line == 3

    def test_unsorted_input_is_sorted(self):
        lines = [
            _make_line(3, mi=0, ci=1),
            _make_line(1, mi=0, ci=1),
            _make_line(2, mi=0, ci=1),
        ]
        seqs = compress_lines(lines)
        assert len(seqs) == 1
        assert seqs[0].start_line == 1
        assert seqs[0].end_line == 3

    def test_source_file_id_default_zero(self):
        seqs = compress_lines([_make_line(1, mi=0, ci=1)])
        assert seqs[0].source_file_id == 0

    def test_fixture_xml_lines(self):
        """Mirror the six lines from the sample fixture XML."""
        lines = [
            _make_line(5,  mi=0, ci=2, mb=0, cb=0),   # COVERED
            _make_line(6,  mi=0, ci=2, mb=0, cb=0),   # COVERED
            _make_line(9,  mi=2, ci=0, mb=0, cb=0),   # NOT_COVERED
            _make_line(10, mi=2, ci=0, mb=0, cb=0),   # NOT_COVERED
            _make_line(13, mi=1, ci=1, mb=1, cb=1),   # PARTLY_COVERED
            _make_line(14, mi=1, ci=1, mb=0, cb=0),   # PARTLY_COVERED
        ]
        seqs = compress_lines(lines)
        assert len(seqs) == 3
        assert (seqs[0].start_line, seqs[0].end_line, seqs[0].coverage_status) == (5, 6, 2)
        assert (seqs[1].start_line, seqs[1].end_line, seqs[1].coverage_status) == (9, 10, 0)
        assert (seqs[2].start_line, seqs[2].end_line, seqs[2].coverage_status) == (13, 14, 1)
