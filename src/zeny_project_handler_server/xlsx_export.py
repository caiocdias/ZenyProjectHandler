"""Grava planilhas XLSX pequenas sem levar uma suíte de escritório ao servidor."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"
_PACKAGE_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CORE_PROPERTIES = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DUBLIN_CORE = "http://purl.org/dc/elements/1.1/"
_DUBLIN_TERMS = "http://purl.org/dc/terms/"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_EXTENDED_PROPERTIES = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_INVALID_SHEET_CHARACTERS = frozenset("[]:*?/\\")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class WorksheetData:
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[object | None, ...], ...]


def write_xlsx(path: Path, sheets: Sequence[WorksheetData]) -> Path:
    """Publique um workbook OOXML válido com cabeçalhos, filtro e painel congelado."""
    worksheets = tuple(sheets)
    if not worksheets:
        raise ValueError("A planilha deve possuir ao menos uma aba")
    names = _sheet_names(worksheets)
    for sheet in worksheets:
        if not sheet.headers:
            raise ValueError("Cada aba deve possuir ao menos uma coluna")
        if any(len(row) != len(sheet.headers) for row in sheet.rows):
            raise ValueError("Todas as linhas devem possuir a mesma quantidade de colunas")

    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _write(archive, "[Content_Types].xml", _content_types(len(worksheets)))
        _write(archive, "_rels/.rels", _root_relationships())
        _write(archive, "docProps/app.xml", _app_properties(names))
        _write(archive, "docProps/core.xml", _core_properties())
        _write(archive, "xl/workbook.xml", _workbook(names))
        _write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships(len(names)))
        _write(archive, "xl/styles.xml", _styles())
        for index, sheet in enumerate(worksheets, start=1):
            _write(archive, f"xl/worksheets/sheet{index}.xml", _worksheet(sheet))
    return target


def _sheet_names(sheets: tuple[WorksheetData, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for index, sheet in enumerate(sheets, start=1):
        cleaned = "".join("_" if char in _INVALID_SHEET_CHARACTERS else char for char in sheet.name)
        cleaned = cleaned.strip(" '")[:31] or f"Planilha {index}"
        candidate = cleaned
        suffix = 2
        while candidate.casefold() in {item.casefold() for item in names}:
            marker = f" ({suffix})"
            candidate = f"{cleaned[: 31 - len(marker)]}{marker}"
            suffix += 1
        names.append(candidate)
    return tuple(names)


def _content_types(sheet_count: int) -> bytes:
    root = ElementTree.Element("Types", xmlns=_CONTENT_TYPES)
    ElementTree.SubElement(
        root,
        "Default",
        Extension="rels",
        ContentType="application/vnd.openxmlformats-package.relationships+xml",
    )
    ElementTree.SubElement(root, "Default", Extension="xml", ContentType="application/xml")
    overrides = (
        (
            "/xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        ),
        (
            "/xl/styles.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
        ),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        (
            "/docProps/app.xml",
            "application/vnd.openxmlformats-officedocument.extended-properties+xml",
        ),
    )
    for part_name, content_type in overrides:
        ElementTree.SubElement(
            root,
            "Override",
            PartName=part_name,
            ContentType=content_type,
        )
    for index in range(1, sheet_count + 1):
        ElementTree.SubElement(
            root,
            "Override",
            PartName=f"/xl/worksheets/sheet{index}.xml",
            ContentType=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
            ),
        )
    return _xml(root)


def _root_relationships() -> bytes:
    root = ElementTree.Element("Relationships", xmlns=_RELATIONSHIPS)
    for identity, relationship_type, target in (
        ("rId1", f"{_OFFICE_RELATIONSHIPS}/officeDocument", "xl/workbook.xml"),
        (
            "rId2",
            f"{_PACKAGE_RELATIONSHIPS}/metadata/core-properties",
            "docProps/core.xml",
        ),
        ("rId3", f"{_OFFICE_RELATIONSHIPS}/extended-properties", "docProps/app.xml"),
    ):
        ElementTree.SubElement(
            root,
            "Relationship",
            Id=identity,
            Type=relationship_type,
            Target=target,
        )
    return _xml(root)


def _app_properties(names: tuple[str, ...]) -> bytes:
    ElementTree.register_namespace("vt", _VT)
    root = ElementTree.Element("Properties", xmlns=_EXTENDED_PROPERTIES)
    ElementTree.SubElement(root, "Application").text = "Zeny Project Handler"
    ElementTree.SubElement(root, "DocSecurity").text = "0"
    heading_pairs = ElementTree.SubElement(root, "HeadingPairs")
    vector = ElementTree.SubElement(heading_pairs, f"{{{_VT}}}vector", size="2", baseType="variant")
    first = ElementTree.SubElement(vector, f"{{{_VT}}}variant")
    ElementTree.SubElement(first, f"{{{_VT}}}lpstr").text = "Planilhas"
    second = ElementTree.SubElement(vector, f"{{{_VT}}}variant")
    ElementTree.SubElement(second, f"{{{_VT}}}i4").text = str(len(names))
    titles = ElementTree.SubElement(root, "TitlesOfParts")
    title_vector = ElementTree.SubElement(
        titles,
        f"{{{_VT}}}vector",
        size=str(len(names)),
        baseType="lpstr",
    )
    for name in names:
        ElementTree.SubElement(title_vector, f"{{{_VT}}}lpstr").text = name
    ElementTree.SubElement(root, "AppVersion").text = "1.0"
    return _xml(root)


def _core_properties() -> bytes:
    ElementTree.register_namespace("cp", _CORE_PROPERTIES)
    ElementTree.register_namespace("dc", _DUBLIN_CORE)
    ElementTree.register_namespace("dcterms", _DUBLIN_TERMS)
    ElementTree.register_namespace("xsi", _XSI)
    root = ElementTree.Element(f"{{{_CORE_PROPERTIES}}}coreProperties")
    ElementTree.SubElement(root, f"{{{_DUBLIN_CORE}}}creator").text = "Zeny Project Handler"
    ElementTree.SubElement(
        root, f"{{{_CORE_PROPERTIES}}}lastModifiedBy"
    ).text = "Zeny Project Handler"
    created = ElementTree.SubElement(
        root,
        f"{{{_DUBLIN_TERMS}}}created",
        {f"{{{_XSI}}}type": "dcterms:W3CDTF"},
    )
    created.text = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return _xml(root)


def _workbook(names: tuple[str, ...]) -> bytes:
    ElementTree.register_namespace("r", _OFFICE_RELATIONSHIPS)
    root = ElementTree.Element("workbook", xmlns=_SPREADSHEET)
    sheets = ElementTree.SubElement(root, "sheets")
    for index, name in enumerate(names, start=1):
        ElementTree.SubElement(
            sheets,
            "sheet",
            name=name,
            sheetId=str(index),
            attrib={f"{{{_OFFICE_RELATIONSHIPS}}}id": f"rId{index}"},
        )
    ElementTree.SubElement(root, "calcPr", calcId="0", fullCalcOnLoad="1")
    return _xml(root)


def _workbook_relationships(sheet_count: int) -> bytes:
    root = ElementTree.Element("Relationships", xmlns=_RELATIONSHIPS)
    for index in range(1, sheet_count + 1):
        ElementTree.SubElement(
            root,
            "Relationship",
            Id=f"rId{index}",
            Type=f"{_OFFICE_RELATIONSHIPS}/worksheet",
            Target=f"worksheets/sheet{index}.xml",
        )
    ElementTree.SubElement(
        root,
        "Relationship",
        Id=f"rId{sheet_count + 1}",
        Type=f"{_OFFICE_RELATIONSHIPS}/styles",
        Target="styles.xml",
    )
    return _xml(root)


def _styles() -> bytes:
    root = ElementTree.Element("styleSheet", xmlns=_SPREADSHEET)
    fonts = ElementTree.SubElement(root, "fonts", count="2")
    normal_font = ElementTree.SubElement(fonts, "font")
    ElementTree.SubElement(normal_font, "sz", val="11")
    ElementTree.SubElement(normal_font, "name", val="Aptos")
    header_font = ElementTree.SubElement(fonts, "font")
    ElementTree.SubElement(header_font, "b")
    ElementTree.SubElement(header_font, "color", rgb="FFFFFFFF")
    ElementTree.SubElement(header_font, "sz", val="11")
    ElementTree.SubElement(header_font, "name", val="Aptos")
    fills = ElementTree.SubElement(root, "fills", count="3")
    ElementTree.SubElement(ElementTree.SubElement(fills, "fill"), "patternFill", patternType="none")
    ElementTree.SubElement(
        ElementTree.SubElement(fills, "fill"),
        "patternFill",
        patternType="gray125",
    )
    header_fill = ElementTree.SubElement(fills, "fill")
    pattern = ElementTree.SubElement(header_fill, "patternFill", patternType="solid")
    ElementTree.SubElement(pattern, "fgColor", rgb="FF24536B")
    ElementTree.SubElement(pattern, "bgColor", indexed="64")
    borders = ElementTree.SubElement(root, "borders", count="1")
    border = ElementTree.SubElement(borders, "border")
    for side in ("left", "right", "top", "bottom", "diagonal"):
        ElementTree.SubElement(border, side)
    cell_style_xfs = ElementTree.SubElement(root, "cellStyleXfs", count="1")
    ElementTree.SubElement(
        cell_style_xfs,
        "xf",
        numFmtId="0",
        fontId="0",
        fillId="0",
        borderId="0",
    )
    cell_xfs = ElementTree.SubElement(root, "cellXfs", count="2")
    ElementTree.SubElement(
        cell_xfs,
        "xf",
        numFmtId="0",
        fontId="0",
        fillId="0",
        borderId="0",
        xfId="0",
        applyAlignment="1",
    ).append(ElementTree.Element("alignment", vertical="top", wrapText="1"))
    header_xf = ElementTree.SubElement(
        cell_xfs,
        "xf",
        numFmtId="0",
        fontId="1",
        fillId="2",
        borderId="0",
        xfId="0",
        applyAlignment="1",
        applyFont="1",
        applyFill="1",
    )
    ElementTree.SubElement(header_xf, "alignment", vertical="center", wrapText="1")
    cell_styles = ElementTree.SubElement(root, "cellStyles", count="1")
    ElementTree.SubElement(cell_styles, "cellStyle", name="Normal", xfId="0", builtinId="0")
    return _xml(root)


def _worksheet(sheet: WorksheetData) -> bytes:
    root = ElementTree.Element("worksheet", xmlns=_SPREADSHEET)
    views = ElementTree.SubElement(root, "sheetViews")
    view = ElementTree.SubElement(views, "sheetView", workbookViewId="0")
    ElementTree.SubElement(
        view,
        "pane",
        ySplit="1",
        topLeftCell="A2",
        activePane="bottomLeft",
        state="frozen",
    )
    columns = ElementTree.SubElement(root, "cols")
    widths = _column_widths(sheet)
    for index, width in enumerate(widths, start=1):
        ElementTree.SubElement(
            columns,
            "col",
            min=str(index),
            max=str(index),
            width=f"{width:.2f}",
            customWidth="1",
        )
    data = ElementTree.SubElement(root, "sheetData")
    _row(data, 1, sheet.headers, style=1)
    for index, values in enumerate(sheet.rows, start=2):
        _row(data, index, values, style=0)
    last_column = _column_name(len(sheet.headers))
    last_row = max(1, len(sheet.rows) + 1)
    ElementTree.SubElement(root, "autoFilter", ref=f"A1:{last_column}{last_row}")
    ElementTree.SubElement(
        root,
        "pageMargins",
        left="0.3",
        right="0.3",
        top="0.5",
        bottom="0.5",
        header="0.2",
        footer="0.2",
    )
    return _xml(root)


def _row(
    parent: ElementTree.Element,
    number: int,
    values: Sequence[object | None],
    *,
    style: int,
) -> None:
    row = ElementTree.SubElement(parent, "row", r=str(number))
    for column, value in enumerate(values, start=1):
        cell = ElementTree.SubElement(
            row,
            "c",
            r=f"{_column_name(column)}{number}",
            s=str(style),
            t="inlineStr",
        )
        inline = ElementTree.SubElement(cell, "is")
        text = ElementTree.SubElement(inline, "t")
        rendered = "" if value is None else str(value)
        if rendered != rendered.strip():
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = rendered


def _column_widths(sheet: WorksheetData) -> tuple[float, ...]:
    rows = (sheet.headers, *sheet.rows[:200])
    return tuple(
        min(60.0, max(10.0, max(len(str(row[index] or "")) for row in rows) + 2.0))
        for index in range(len(sheet.headers))
    )


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("O índice de coluna deve ser positivo")
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml(root: ElementTree.Element) -> bytes:
    return cast(bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True))


def _write(archive: ZipFile, name: str, payload: bytes) -> None:
    info = ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)
