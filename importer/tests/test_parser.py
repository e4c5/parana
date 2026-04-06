"""Unit tests for the JaCoCo XML parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from parana_importer.parser import parse_jacoco_xml


class TestParseJacocoXml:
    def test_parses_sample_fixture(self, sample_xml_path, tmp_path):
        report = parse_jacoco_xml(sample_xml_path)

        assert report.name == "MyProject"
        assert len(report.packages) == 1

        pkg = report.packages[0]
        assert pkg.name == "com/example"
        assert len(pkg.classes) == 1
        assert len(pkg.source_files) == 1

        cls = pkg.classes[0]
        assert cls.name == "com/example/Calculator"
        assert cls.source_file_name == "Calculator.java"
        assert len(cls.methods) == 3

        add_method = next(m for m in cls.methods if m.name == "add")
        assert add_method.descriptor == "(II)I"
        assert add_method.start_line == 5
        instr_counter = next(c for c in add_method.counters if c.type == "INSTRUCTION")
        assert instr_counter.missed == 0
        assert instr_counter.covered == 4

        subtract_method = next(m for m in cls.methods if m.name == "subtract")
        instr_counter = next(c for c in subtract_method.counters if c.type == "INSTRUCTION")
        assert instr_counter.missed == 4
        assert instr_counter.covered == 0

    def test_parses_source_file_lines(self, sample_xml_path):
        report = parse_jacoco_xml(sample_xml_path)
        sf = report.packages[0].source_files[0]
        assert sf.name == "Calculator.java"
        assert len(sf.lines) == 6
        line_nrs = sorted(ln.nr for ln in sf.lines)
        assert line_nrs == [5, 6, 9, 10, 13, 14]

    def test_parses_class_counters(self, sample_xml_path):
        report = parse_jacoco_xml(sample_xml_path)
        cls = report.packages[0].classes[0]
        types = {c.type for c in cls.counters}
        assert "INSTRUCTION" in types
        assert "CLASS" in types

    def test_missing_report_element_raises(self, tmp_path):
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("<notreport/>")
        with pytest.raises(ValueError, match="No <report>"):
            parse_jacoco_xml(str(bad_xml))

    def test_minimal_valid_xml(self, tmp_path):
        xml = tmp_path / "minimal.xml"
        xml.write_text(
            textwrap.dedent("""\
                <?xml version="1.0" encoding="UTF-8"?>
                <report name="empty">
                </report>
            """)
        )
        report = parse_jacoco_xml(str(xml))
        assert report.name == "empty"
        assert report.packages == []
