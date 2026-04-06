"""Streaming JaCoCo XML parser.

Uses ``lxml.etree.iterparse`` for memory-efficient processing of large reports.
The parser builds an in-memory :class:`~parana_importer.models.Report` object
from the XML but never holds more than the current element subtree in the lxml
tree at one time (each element is cleared after it is fully processed).

JaCoCo XML structure (simplified)::

    <report name="…">
      <package name="com/example">
        <class name="com/example/Foo" sourcefilename="Foo.java">
          <method name="doSomething" desc="()V" line="10">
            <counter type="INSTRUCTION" missed="0" covered="5"/>
            …
          </method>
          <counter type="INSTRUCTION" missed="0" covered="10"/>
          …
        </class>
        <sourcefile name="Foo.java">
          <line nr="10" mi="0" ci="1" mb="0" cb="0"/>
          …
          <counter type="INSTRUCTION" missed="0" covered="10"/>
          …
        </sourcefile>
        <counter type="INSTRUCTION" missed="0" covered="20"/>
        …
      </package>
      <counter type="INSTRUCTION" missed="0" covered="20"/>
      …
    </report>
"""

from __future__ import annotations

from lxml import etree

from .models import Counter, JavaClass, Line, Method, Package, Report, SourceFile


def parse_jacoco_xml(path: str) -> Report:
    """Parse a JaCoCo XML report file and return a :class:`Report` object.

    Args:
        path: filesystem path to the JaCoCo XML file.

    Returns:
        A fully-populated :class:`Report` instance.

    Raises:
        ValueError: if the file contains no ``<report>`` root element, or if
            ``lxml`` encounters a malformed XML document.
    """
    report: Report | None = None
    current_package: Package | None = None
    current_source_file: SourceFile | None = None
    current_class: JavaClass | None = None
    current_method: Method | None = None

    context = etree.iterparse(path, events=("start", "end"))

    for event, elem in context:
        tag = elem.tag

        if event == "start":
            if tag == "report":
                report = Report(name=elem.get("name", ""))

            elif tag == "package":
                current_package = Package(name=elem.get("name", ""))

            elif tag == "class":
                current_class = JavaClass(
                    name=elem.get("name", ""),
                    source_file_name=elem.get("sourcefilename", ""),
                )

            elif tag == "method":
                current_method = Method(
                    name=elem.get("name", ""),
                    descriptor=elem.get("desc", ""),
                    start_line=int(elem.get("line", 0)),
                )

            elif tag == "sourcefile":
                current_source_file = SourceFile(name=elem.get("name", ""))

            elif tag == "line":
                if current_source_file is not None:
                    current_source_file.lines.append(
                        Line(
                            nr=int(elem.get("nr", 0)),
                            mi=int(elem.get("mi", 0)),
                            ci=int(elem.get("ci", 0)),
                            mb=int(elem.get("mb", 0)),
                            cb=int(elem.get("cb", 0)),
                        )
                    )

            elif tag == "counter":
                counter = Counter(
                    type=elem.get("type", ""),
                    missed=int(elem.get("missed", 0)),
                    covered=int(elem.get("covered", 0)),
                )
                # Assign counter to the innermost open container.
                if current_method is not None:
                    current_method.counters.append(counter)
                elif current_class is not None:
                    current_class.counters.append(counter)
                elif current_source_file is not None:
                    current_source_file.counters.append(counter)
                elif current_package is not None:
                    current_package.counters.append(counter)
                elif report is not None:
                    report.counters.append(counter)

        else:  # event == "end"
            if tag == "method":
                if current_class is not None and current_method is not None:
                    current_class.methods.append(current_method)
                current_method = None

            elif tag == "class":
                if current_package is not None and current_class is not None:
                    current_package.classes.append(current_class)
                current_class = None

            elif tag == "sourcefile":
                if current_package is not None and current_source_file is not None:
                    current_package.source_files.append(current_source_file)
                current_source_file = None

            elif tag == "package":
                if report is not None and current_package is not None:
                    report.packages.append(current_package)
                current_package = None

            # Free the lxml element from memory after it is fully processed.
            elem.clear()

    if report is None:
        raise ValueError(f"No <report> root element found in '{path}'")

    return report
