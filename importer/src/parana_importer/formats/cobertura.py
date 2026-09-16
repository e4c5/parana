"""Streaming Cobertura XML parser.

Cobertura XML is emitted by coverage.py (``coverage xml`` / ``pytest --cov-report=xml``),
coverlet (.NET), gcovr, Istanbul/nyc, and many other tools.  Structure (simplified)::

    <coverage line-rate="…" branch-rate="…" lines-covered="…" lines-valid="…" …>
      <sources><source>/abs/project/root</source></sources>
      <packages>
        <package name="app.models" line-rate="…" branch-rate="…" complexity="0">
          <classes>
            <class name="user.py" filename="app/models/user.py" line-rate="…" branch-rate="…">
              <methods>
                <method name="save" signature="(self)" line-rate="…" branch-rate="…">
                  <lines><line number="12" hits="1"/></lines>
                </method>
              </methods>
              <lines>
                <line number="1" hits="1"/>
                <line number="7" hits="0" branch="true" condition-coverage="50% (1/2)"/>
              </lines>
            </class>
          </classes>
        </package>
      </packages>
    </coverage>

Mapping onto the canonical :class:`~parana_importer.models.Report`:

* ``<package>``        → :class:`Package` (name kept verbatim, e.g. ``app.models``).
* ``<class filename>`` → one :class:`SourceFile` per distinct ``filename`` within the
  package, plus one :class:`JavaClass` per ``<class>`` (several classes may share a file).
* ``<line>``           → :class:`Line` with ``ci=1/mi=0`` when ``hits > 0`` else
  ``ci=0/mi=1``; ``condition-coverage="p% (c/t)"`` gives ``cb=c, mb=t-c``.
* ``<method>``         → :class:`Method` (``signature`` → ``descriptor``, ``start_line`` =
  lowest line number inside the method, or 0 when the method has no lines).

Counters are derived from the line data because Cobertura only carries ratios:
``LINE``/``INSTRUCTION`` (identical — one statement per line), ``BRANCH``, ``METHOD``
and ``CLASS``.  No ``COMPLEXITY`` counter is produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from ..models import Counter, JavaClass, Line, Method, Package, Report, SourceFile

_CONDITION_RE = re.compile(r"\((\d+)/(\d+)\)")


@dataclass
class _RawLine:
    hits: int = 0
    covered_branches: int = 0
    total_branches: int = 0

    def merge(self, other: _RawLine) -> None:
        self.hits = max(self.hits, other.hits)
        self.covered_branches = max(self.covered_branches, other.covered_branches)
        self.total_branches = max(self.total_branches, other.total_branches)

    def to_line(self, nr: int) -> Line:
        covered = self.hits > 0
        return Line(
            nr=nr,
            mi=0 if covered else 1,
            ci=1 if covered else 0,
            mb=self.total_branches - self.covered_branches,
            cb=self.covered_branches,
        )


@dataclass
class _Totals:
    lines_missed: int = 0
    lines_covered: int = 0
    branches_missed: int = 0
    branches_covered: int = 0
    methods_missed: int = 0
    methods_covered: int = 0
    classes_missed: int = 0
    classes_covered: int = 0

    def add(self, other: _Totals) -> None:
        self.lines_missed += other.lines_missed
        self.lines_covered += other.lines_covered
        self.branches_missed += other.branches_missed
        self.branches_covered += other.branches_covered
        self.methods_missed += other.methods_missed
        self.methods_covered += other.methods_covered
        self.classes_missed += other.classes_missed
        self.classes_covered += other.classes_covered

    def counters(self, *, include_methods: bool, include_classes: bool) -> list[Counter]:
        out = [
            Counter("INSTRUCTION", self.lines_missed, self.lines_covered),
            Counter("BRANCH", self.branches_missed, self.branches_covered),
            Counter("LINE", self.lines_missed, self.lines_covered),
        ]
        if include_methods:
            out.append(Counter("METHOD", self.methods_missed, self.methods_covered))
        if include_classes:
            out.append(Counter("CLASS", self.classes_missed, self.classes_covered))
        return out


def _line_totals(lines: dict[int, _RawLine]) -> _Totals:
    t = _Totals()
    for raw in lines.values():
        if raw.hits > 0:
            t.lines_covered += 1
        else:
            t.lines_missed += 1
        t.branches_covered += raw.covered_branches
        t.branches_missed += raw.total_branches - raw.covered_branches
    return t


def _parse_raw_line(elem: etree._Element) -> tuple[int, _RawLine]:
    nr = int(elem.get("number", 0))
    raw = _RawLine(hits=int(float(elem.get("hits", 0))))
    cond = elem.get("condition-coverage")
    if cond:
        m = _CONDITION_RE.search(cond)
        if m:
            raw.covered_branches = int(m.group(1))
            raw.total_branches = int(m.group(2))
    return nr, raw


@dataclass
class _ClassState:
    cls: JavaClass
    filename: str
    lines: dict[int, _RawLine] = field(default_factory=dict)


@dataclass
class _MethodState:
    method: Method
    lines: dict[int, _RawLine] = field(default_factory=dict)


@dataclass
class _PackageState:
    package: Package
    files: dict[str, dict[int, _RawLine]] = field(default_factory=dict)
    file_classes: dict[str, list[_Totals]] = field(default_factory=dict)
    totals: _Totals = field(default_factory=_Totals)


def parse(path: str) -> Report:
    """Parse a Cobertura XML report file and return a :class:`Report` object.

    Raises:
        ValueError: if the file has no ``<coverage>`` root element or is malformed XML.
    """
    report: Report | None = None
    report_totals = _Totals()
    pkg: _PackageState | None = None
    cls: _ClassState | None = None
    meth: _MethodState | None = None

    for event, elem in etree.iterparse(path, events=("start", "end")):
        tag = etree.QName(elem).localname

        if event == "start":
            if tag == "coverage" and report is None:
                report = Report(name=elem.get("name") or "cobertura", format="cobertura")

            elif tag == "package":
                pkg = _PackageState(Package(name=elem.get("name", "")))

            elif tag == "class" and pkg is not None:
                filename = elem.get("filename", "")
                cls = _ClassState(
                    JavaClass(name=elem.get("name", ""), source_file_name=filename),
                    filename=filename,
                )

            elif tag == "method" and cls is not None:
                meth = _MethodState(
                    Method(
                        name=elem.get("name", ""),
                        descriptor=elem.get("signature", ""),
                        start_line=0,
                    )
                )

            elif tag == "line":
                nr, raw = _parse_raw_line(elem)
                if meth is not None:
                    meth.lines.setdefault(nr, _RawLine()).merge(raw)
                elif cls is not None:
                    cls.lines.setdefault(nr, _RawLine()).merge(raw)

        else:  # end
            if tag == "method" and meth is not None and cls is not None:
                t = _line_totals(meth.lines)
                meth.method.start_line = min(meth.lines) if meth.lines else 0
                if t.lines_covered > 0:
                    t.methods_covered = 1
                else:
                    t.methods_missed = 1
                meth.method.counters = t.counters(include_methods=True, include_classes=False)
                # Method lines are a subset of the class lines; fold them in so
                # reports that only list lines under <method> still yield file data.
                for nr, raw in meth.lines.items():
                    cls.lines.setdefault(nr, _RawLine()).merge(raw)
                cls.cls.methods.append(meth.method)
                meth = None

            elif tag == "class" and cls is not None and pkg is not None:
                t = _line_totals(cls.lines)
                for m in cls.cls.methods:
                    mc = next(c for c in m.counters if c.type == "METHOD")
                    t.methods_missed += mc.missed
                    t.methods_covered += mc.covered
                if t.lines_covered > 0:
                    t.classes_covered = 1
                elif cls.lines:
                    t.classes_missed = 1
                cls.cls.counters = t.counters(include_methods=True, include_classes=False)

                file_lines = pkg.files.setdefault(cls.filename, {})
                for nr, raw in cls.lines.items():
                    file_lines.setdefault(nr, _RawLine()).merge(raw)
                pkg.file_classes.setdefault(cls.filename, []).append(t)
                pkg.package.classes.append(cls.cls)
                cls = None

            elif tag == "package" and pkg is not None and report is not None:
                for filename, lines in pkg.files.items():
                    sf = SourceFile(name=filename)
                    sf.lines = [raw.to_line(nr) for nr, raw in sorted(lines.items())]
                    ft = _line_totals(lines)
                    for ct in pkg.file_classes.get(filename, []):
                        ft.methods_missed += ct.methods_missed
                        ft.methods_covered += ct.methods_covered
                        ft.classes_missed += ct.classes_missed
                        ft.classes_covered += ct.classes_covered
                    sf.counters = ft.counters(include_methods=True, include_classes=True)
                    pkg.totals.add(ft)
                    pkg.package.source_files.append(sf)
                pkg.package.counters = pkg.totals.counters(include_methods=True, include_classes=True)
                report_totals.add(pkg.totals)
                report.packages.append(pkg.package)
                pkg = None

            elem.clear()

    if report is None:
        raise ValueError(f"No <coverage> root element found in '{path}'")

    report.counters = report_totals.counters(include_methods=True, include_classes=True)
    return report
