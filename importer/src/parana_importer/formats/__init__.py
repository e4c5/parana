"""Coverage report format registry.

Every supported format exposes a ``parse(path) -> Report`` function that
normalises the tool-specific report into the canonical
:class:`~parana_importer.models.Report` model.  :func:`parse_report` picks the
parser either from an explicit format name or by sniffing the file.
"""

from __future__ import annotations

from collections.abc import Callable

from lxml import etree

from ..models import Report
from . import cobertura, jacoco

JACOCO = "jacoco"
COBERTURA = "cobertura"

PARSERS: dict[str, Callable[[str], Report]] = {
    JACOCO: jacoco.parse,
    COBERTURA: cobertura.parse,
}

SUPPORTED_FORMATS: tuple[str, ...] = tuple(PARSERS)

_ROOT_TAG_TO_FORMAT = {
    "report": JACOCO,
    "coverage": COBERTURA,
}


def detect_format(path: str) -> str:
    """Return the format name for the report at *path* by inspecting its root element.

    Raises:
        ValueError: if the root element is not recognised or the file is not XML.
    """
    try:
        for _event, elem in etree.iterparse(path, events=("start",)):
            root_tag = etree.QName(elem).localname
            break
        else:
            raise ValueError(f"'{path}' contains no XML elements")
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"'{path}' is not a valid XML coverage report: {exc}") from exc

    fmt = _ROOT_TAG_TO_FORMAT.get(root_tag)
    if fmt is None:
        raise ValueError(
            f"Unrecognised coverage report root element <{root_tag}> in '{path}'; "
            f"supported formats: {', '.join(SUPPORTED_FORMATS)}"
        )
    return fmt


def parse_report(path: str, fmt: str | None = None) -> Report:
    """Parse the coverage report at *path*.

    Args:
        path: filesystem path to the report file.
        fmt:  explicit format name (one of :data:`SUPPORTED_FORMATS`).  When
              ``None`` the format is auto-detected.
    """
    if fmt is None:
        fmt = detect_format(path)
    try:
        parser = PARSERS[fmt]
    except KeyError:
        raise ValueError(
            f"Unknown coverage format '{fmt}'; supported formats: {', '.join(SUPPORTED_FORMATS)}"
        ) from None
    report = parser(path)
    report.format = fmt
    return report
