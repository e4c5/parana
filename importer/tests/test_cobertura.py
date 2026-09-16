"""Unit tests for the Cobertura XML parser and the format registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from parana_importer.formats import SUPPORTED_FORMATS, detect_format, parse_report
from parana_importer.formats.cobertura import parse as parse_cobertura
from parana_importer.sequences import compress_lines

FIXTURES_DIR = Path(__file__).parent / "fixtures"
COVERAGE_PY_XML = str(FIXTURES_DIR / "coverage_py_cobertura.xml")
METHODS_XML = str(FIXTURES_DIR / "cobertura_methods.xml")


def _counter(counters, type_):
    return next((c.missed, c.covered) for c in counters if c.type == type_)


class TestRegistry:
    def test_supported_formats(self):
        assert set(SUPPORTED_FORMATS) == {"jacoco", "cobertura"}

    def test_detects_jacoco(self, sample_xml_path):
        assert detect_format(sample_xml_path) == "jacoco"

    def test_detects_cobertura(self):
        assert detect_format(COVERAGE_PY_XML) == "cobertura"

    def test_unknown_root_raises(self, tmp_path):
        bad = tmp_path / "bad.xml"
        bad.write_text("<something/>")
        with pytest.raises(ValueError, match="Unrecognised"):
            detect_format(str(bad))

    def test_not_xml_raises(self, tmp_path):
        bad = tmp_path / "bad.info"
        bad.write_text("TN:\nSF:foo.c\nend_of_record\n")
        with pytest.raises(ValueError, match="not a valid XML"):
            detect_format(str(bad))

    def test_unknown_format_name_raises(self, sample_xml_path):
        with pytest.raises(ValueError, match="Unknown coverage format"):
            parse_report(sample_xml_path, "lcov")

    def test_parse_report_auto_detect_sets_format(self, sample_xml_path):
        assert parse_report(sample_xml_path).format == "jacoco"
        assert parse_report(COVERAGE_PY_XML).format == "cobertura"

    def test_explicit_format_mismatch_raises(self, sample_xml_path):
        with pytest.raises(ValueError, match="No <coverage>"):
            parse_report(sample_xml_path, "cobertura")


class TestCoveragePyReport:
    """A report produced by ``coverage xml`` (no <method> elements)."""

    def test_structure(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        assert report.format == "cobertura"
        assert [p.name for p in report.packages] == ["app", "app.models"]

        app = report.packages[0]
        assert [sf.name for sf in app.source_files] == ["app/__init__.py", "app/util.py"]
        assert [c.name for c in app.classes] == ["__init__.py", "util.py"]
        assert app.classes[1].source_file_name == "app/util.py"
        assert app.classes[1].methods == []

    def test_lines_and_branches(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        util = report.packages[0].source_files[1]
        by_nr = {ln.nr: ln for ln in util.lines}
        assert sorted(by_nr) == [1, 2, 3, 4, 5, 6, 9, 10]

        assert (by_nr[1].mi, by_nr[1].ci, by_nr[1].mb, by_nr[1].cb) == (0, 1, 0, 0)
        # hits=1, condition-coverage 50% (1/2)
        assert (by_nr[2].mi, by_nr[2].ci, by_nr[2].mb, by_nr[2].cb) == (0, 1, 1, 1)
        assert (by_nr[3].mi, by_nr[3].ci) == (1, 0)
        # 100% (2/2)
        assert (by_nr[4].mb, by_nr[4].cb) == (0, 2)

    def test_file_counters(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        util = report.packages[0].source_files[1]
        assert _counter(util.counters, "LINE") == (2, 6)
        assert _counter(util.counters, "INSTRUCTION") == (2, 6)
        assert _counter(util.counters, "BRANCH") == (1, 3)
        assert _counter(util.counters, "CLASS") == (0, 1)
        assert not any(c.type == "COMPLEXITY" for c in util.counters)

    def test_empty_class_is_not_counted_as_missed(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        init = report.packages[0].source_files[0]
        assert init.lines == []
        assert _counter(init.counters, "CLASS") == (0, 0)

    def test_report_totals_match_coverage_py_header(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        # lines-valid="19" lines-covered="14" branches-valid="6" branches-covered="4"
        assert _counter(report.counters, "LINE") == (5, 14)
        assert _counter(report.counters, "BRANCH") == (2, 4)

    def test_line_sequences(self):
        report = parse_cobertura(COVERAGE_PY_XML)
        user = report.packages[1].source_files[1]
        seqs = [(s.start_line, s.end_line, s.coverage_status) for s in compress_lines(user.lines)]
        assert seqs == [
            (1, 4, 2),
            (6, 6, 2),
            (7, 7, 1),
            (8, 8, 2),
            (9, 9, 0),
            (11, 11, 2),
            (12, 13, 0),
        ]


class TestCoberturaWithMethods:
    """A coverlet-style report with <method> elements and two classes per file."""

    def test_methods(self):
        report = parse_cobertura(METHODS_XML)
        pkg = report.packages[0]
        calc = pkg.classes[0]
        assert calc.name == "Demo.Core.Calculator"
        assert [m.name for m in calc.methods] == ["Add", "Subtract", "Multiply"]

        add, sub, mul = calc.methods
        assert add.descriptor == "(System.Int32,System.Int32)"
        assert (add.start_line, sub.start_line, mul.start_line) == (5, 9, 13)
        assert _counter(add.counters, "LINE") == (0, 2)
        assert _counter(add.counters, "METHOD") == (0, 1)
        assert _counter(sub.counters, "METHOD") == (1, 0)
        assert _counter(mul.counters, "LINE") == (1, 1)
        assert _counter(mul.counters, "BRANCH") == (1, 1)

    def test_class_counters(self):
        report = parse_cobertura(METHODS_XML)
        calc = report.packages[0].classes[0]
        assert _counter(calc.counters, "LINE") == (3, 3)
        assert _counter(calc.counters, "METHOD") == (1, 2)
        assert _counter(calc.counters, "BRANCH") == (1, 1)

    def test_two_classes_share_one_source_file(self):
        report = parse_cobertura(METHODS_XML)
        pkg = report.packages[0]
        assert len(pkg.classes) == 2
        assert len(pkg.source_files) == 1
        sf = pkg.source_files[0]
        assert sf.name == "Demo.Core/Calculator.cs"
        assert sorted(ln.nr for ln in sf.lines) == [5, 6, 9, 10, 13, 14, 20]
        assert _counter(sf.counters, "LINE") == (3, 4)
        assert _counter(sf.counters, "METHOD") == (1, 3)
        assert _counter(sf.counters, "CLASS") == (0, 2)
        assert _counter(pkg.counters, "CLASS") == (0, 2)

    def test_method_only_lines_are_folded_into_file(self, tmp_path):
        xml = tmp_path / "m.xml"
        xml.write_text(
            """<coverage><packages><package name="p"><classes>
            <class name="C" filename="c.py"><methods>
              <method name="f" signature="()"><lines><line number="3" hits="1"/></lines></method>
            </methods><lines/></class>
            </classes></package></packages></coverage>"""
        )
        report = parse_cobertura(str(xml))
        sf = report.packages[0].source_files[0]
        assert [ln.nr for ln in sf.lines] == [3]
        assert _counter(sf.counters, "LINE") == (0, 1)

    def test_missing_root_raises(self, tmp_path):
        bad = tmp_path / "bad.xml"
        bad.write_text("<report/>")
        with pytest.raises(ValueError, match="No <coverage>"):
            parse_cobertura(str(bad))
