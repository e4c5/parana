"""Line coverage status derivation and sequence compression.

Coverage status constants (stored as SMALLINT in the DB):
    0 = NOT_COVERED    — ci == 0
    1 = PARTLY_COVERED — ci > 0 and (mi > 0 or mb > 0)
    2 = COVERED        — ci > 0 and mi == 0 and mb == 0
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Line


@dataclass
class LineSeqRow:
    """A single row destined for the line_coverage_sequence table."""

    source_file_id: int
    start_line: int
    end_line: int
    coverage_status: int  # 0, 1, or 2


def derive_status(mi: int, ci: int, mb: int, cb: int) -> int:  # noqa: ARG001
    """Map per-line JaCoCo counters to a coverage status integer (0/1/2).

    Args:
        mi: missed instructions
        ci: covered instructions
        mb: missed branches
        cb: covered branches (used implicitly — a line with cb>0 and mb==0 is COVERED)

    Returns:
        0 (NOT_COVERED), 1 (PARTLY_COVERED), or 2 (COVERED)
    """
    if ci == 0:
        return 0  # NOT_COVERED: no instructions executed
    if mi == 0 and mb == 0:
        return 2  # COVERED: all instructions executed, all branches (if any) covered
    return 1  # PARTLY_COVERED: some instructions/branches executed, some missed


def compress_lines(lines: list[Line]) -> list[LineSeqRow]:
    """Collapse consecutive lines with the same coverage status into sequence rows.

    Lines are processed in ascending line-number order.  A sequence is extended
    whenever the next line is immediately adjacent (nr == prev_end + 1) *and*
    shares the same status.  Otherwise the current sequence is flushed and a new
    one is started.

    Args:
        lines: list of Line objects (order does not need to be sorted beforehand)

    Returns:
        list of LineSeqRow objects (source_file_id left as 0; caller must set it)
    """
    sequences: list[LineSeqRow] = []
    current: LineSeqRow | None = None

    for line in sorted(lines, key=lambda ln: ln.nr):
        status = derive_status(line.mi, line.ci, line.mb, line.cb)
        if current is None:
            current = LineSeqRow(
                source_file_id=0,
                start_line=line.nr,
                end_line=line.nr,
                coverage_status=status,
            )
        elif status == current.coverage_status and line.nr == current.end_line + 1:
            current.end_line = line.nr
        else:
            sequences.append(current)
            current = LineSeqRow(
                source_file_id=0,
                start_line=line.nr,
                end_line=line.nr,
                coverage_status=status,
            )

    if current is not None:
        sequences.append(current)

    return sequences
