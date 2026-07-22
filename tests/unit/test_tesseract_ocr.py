from __future__ import annotations

from zeny_project_handler.adapters.analysis.tesseract_ocr import _parse_tsv, _ppm_bytes
from zeny_project_handler.ports.analysis import PaginaRasterOcr


def test_ppm_encoder_removes_stride_padding() -> None:
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=2,
        altura_pixels=2,
        stride=8,
        dados_rgb=b"abcdef__ghijkl__",
        dpi=200,
    )

    encoded = _ppm_bytes(page)

    assert encoded == b"P6\n2 2\n255\nabcdefghijkl"


def test_tsv_parser_groups_words_into_normalized_lines() -> None:
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\tPOSTE",
            "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t80\t11-300",
            "5\t1\t1\t1\t2\t1\t5\t60\t20\t10\t-1\t",
        )
    )

    result = _parse_tsv(tsv, width=100, height=100)

    assert len(result) == 1
    assert result[0].texto == "POSTE 11-300"
    assert result[0].caixa_normalizada == (0.1, 0.2, 0.8, 0.3)
    assert result[0].confianca == 0.85
