import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from whoami.contracts import INEC_COLUMNS
from whoami.ingest import inec
from whoami.ingest.raw import RawFile

SOURCE = RawFile("x", "https://example.test/x", "0", datetime(2026, 10, 7, tzinfo=UTC), Path("x"))

#: Source bytes are cp850, the delimiter is `;` and the header spans three rows.
GDP_CSV = (
    ";PIBCONSTANTE ;PIBCONSTANTE ;PIBCORRIENTE;PIBCORRIENTE\r\n"
    ";A;PIB;A;PIB\r\n"
    "Trimestre;Agricultura (M);PRODUCTO INTERNO BRUTO A PRECIOS DE COMPRADOR;Agricultura (M);PIB\r\n"
    "2021-Q1;1;16174,64666;1;16151.6\r\n"
    "2022-Q1;1;18296.15197;1;18747.5\r\n"
    "2021-Q1;1;99999;1;99999\r\n"
    "2022-Q2;1;..;1;17279.2\r\n"
)


def xlsx(rows: dict[int, dict[str, str]]) -> bytes:
    """Minimal workbook with the shared-string layout INEC uses; a value starting with `=` is a number."""
    strings: list[str] = []
    sheet_rows = []
    for number, cells in rows.items():
        xml = ""
        for column, text in cells.items():
            if text.startswith("="):
                xml += f'<c r="{column}{number}"><v>{text[1:]}</v></c>'
            else:
                strings.append(text)
                xml += f'<c r="{column}{number}" t="s"><v>{len(strings) - 1}</v></c>'
        sheet_rows.append(f'<row r="{number}">{xml}</row>')
    namespace = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    shared = "".join(f"<si><t>{text}</t></si>" for text in strings)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", f"<sst {namespace}>{shared}</sst>")
        archive.writestr("xl/worksheets/sheet1.xml", f"<worksheet {namespace}><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>")
    return buffer.getvalue()


CPI_XLSX = xlsx(
    {
        8: {"A": "Mes", "B": "Indice de Precios 2024=100 (a)"},
        11: {"A": "2025", "B": "=99.878", "E": "=-0.12"},
        12: {"A": "Enero", "B": "=99.74", "C": "=0.2598", "D": "=-0.18", "E": "                       -"},
        13: {"A": "Febrero", "B": "=100.12", "C": "                       -", "D": "=5.27E-2"},
        14: {"A": "2026"},
        15: {"A": "Enero", "B": "=100.07", "C": "=0.22", "D": "=0.33"},
        16: {"A": "Septiembre"},
    }
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1234.5", 1234.5), ("1,234.5", 1234.5), ("1.234,5", 1234.5), ("12,5", 12.5), ("20,069", 20069.0), (" -4.2 ", -4.2)],
)
def test_parse_number_handles_decimal_and_thousands_separators(text, expected):
    assert inec.parse_number(text) == expected


@pytest.mark.parametrize("text", ["", "-", "..", "                       -"])
def test_parse_number_keeps_missing_as_none_never_zero(text):
    assert inec.parse_number(text) is None


def test_gdp_reads_total_column_of_each_group_from_cp850_bytes():
    text = GDP_CSV.encode("cp850").decode(inec.CSV_ENCODING)

    observations, _ = inec.parse_gdp(text, SOURCE)

    values = {(o.serie_id, o.period): o.value for o in observations}
    assert values[("pib_constante", "2021-T1")] == 16174.64666
    assert values[("pib_corriente", "2022-T1")] == 18747.5


def test_gdp_period_label_repeated_in_source_is_excluded_not_overwritten():
    observations, excluded = inec.parse_gdp(GDP_CSV, SOURCE)

    assert {(o.serie_id, o.period): o.value for o in observations}[("pib_constante", "2021-T1")] == 16174.64666
    assert [(e["periodo"], e["motivo"]) for e in excluded] == [("2021-T1", inec.DUPLICATE_PERIOD)]


def test_gdp_dots_in_source_become_null():
    observations, _ = inec.parse_gdp(GDP_CSV, SOURCE)

    assert {(o.serie_id, o.period): o.value for o in observations}[("pib_constante", "2022-T2")] is None


def test_year_on_year_is_null_without_the_previous_year_quarter():
    observations, _ = inec.parse_gdp(GDP_CSV, SOURCE)

    growth = {o.period: o.value for o in inec.year_on_year(observations)}

    assert growth["2021-T1"] is None
    assert growth["2022-T1"] == round((18296.15197 / 16174.64666 - 1) * 100, 4)
    assert growth["2022-T2"] is None


def test_cpi_reads_months_under_their_year_and_skips_annual_rows():
    observations, _ = inec.parse_cpi(CPI_XLSX, SOURCE)

    values = {(o.serie_id, o.period): o.value for o in observations}
    assert values[("ipc_indice", "2025-01")] == 99.74
    assert values[("ipc_var_interanual", "2025-02")] == 0.0527
    assert values[("ipc_indice", "2026-01")] == 100.07
    assert not any(o.period == "2025" for o in observations)


def test_cpi_dash_is_null_and_unpublished_month_is_excluded():
    observations, excluded = inec.parse_cpi(CPI_XLSX, SOURCE)

    assert {(o.serie_id, o.period): o.value for o in observations}[("ipc_var_mensual", "2025-02")] is None
    assert excluded == [{"serie_id": "ipc", "periodo": "2026-09", "motivo": inec.UNPUBLISHED}]


def test_find_link_encodes_spaces_of_the_catalog_href():
    page = b'<a href="archivos/A07055475Anexo 4.xlsx">x</a>'

    assert inec.find_link(page, r"archivos/[^\"']*Anexo 4\.xlsx") == "https://www.inec.gob.pa/archivos/A07055475Anexo%204.xlsx"


def test_find_link_fails_loudly_when_the_catalog_changes():
    with pytest.raises(LookupError):
        inec.find_link(b"<html></html>", r"Anexo 4")


def test_every_series_has_metadata_and_row_matches_contract_columns():
    observations, _ = inec.parse_cpi(CPI_XLSX, SOURCE)

    row = inec._row(observations[0])

    assert tuple(row) == INEC_COLUMNS
    assert row["fecha_extraccion"] == "2026-10-07T00:00:00Z"
    assert {o.serie_id for o in observations} <= set(inec.SERIES)
