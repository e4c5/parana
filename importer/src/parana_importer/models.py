"""Dataclasses that model the in-memory representation of a parsed coverage report.

The hierarchy mirrors JaCoCo XML (report → package → class/method + sourcefile →
line); other formats are normalised into this shape by :mod:`parana_importer.formats`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Counter:
    """A JaCoCo <counter> element — missed/covered values for one metric type."""

    type: str  # INSTRUCTION | BRANCH | LINE | COMPLEXITY | METHOD | CLASS
    missed: int
    covered: int


@dataclass
class Line:
    """A JaCoCo <line> element inside a <sourcefile>."""

    nr: int   # line number (1-based)
    mi: int   # missed instructions
    ci: int   # covered instructions
    mb: int   # missed branches
    cb: int   # covered branches


@dataclass
class Method:
    """A JaCoCo <method> element inside a <class>."""

    name: str
    descriptor: str   # JVM method descriptor, e.g. "(II)I"
    start_line: int
    counters: list[Counter] = field(default_factory=list)


@dataclass
class JavaClass:
    """A JaCoCo <class> element inside a <package>."""

    name: str             # JVM slash-separated, e.g. "com/example/Calculator"
    source_file_name: str  # value of the sourcefilename attribute
    methods: list[Method] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)


@dataclass
class SourceFile:
    """A JaCoCo <sourcefile> element inside a <package>."""

    name: str  # e.g. "Calculator.java"
    lines: list[Line] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)


@dataclass
class Package:
    """A JaCoCo <package> element inside a <report>."""

    name: str  # JVM slash-separated, e.g. "com/example"
    source_files: list[SourceFile] = field(default_factory=list)
    classes: list[JavaClass] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)


@dataclass
class Report:
    """A whole coverage report, normalised to the JaCoCo-shaped hierarchy.

    ``format`` names the source tool format (e.g. ``"jacoco"``, ``"cobertura"``).
    For non-JVM formats, ``INSTRUCTION`` counters carry statement/line counts and
    ``COMPLEXITY`` counters are absent.
    """

    name: str
    packages: list[Package] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    format: str = "jacoco"
