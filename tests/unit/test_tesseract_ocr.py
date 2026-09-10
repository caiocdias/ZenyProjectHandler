from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from zeny_project_handler.adapters.analysis import tesseract_ocr as ocr_module
from zeny_project_handler.adapters.analysis.tesseract_ocr import (
    _parse_tsv,
    _ppm_bytes,
)
from zeny_project_handler.ports.analysis import PaginaRasterOcr


def _fake_installation(
    root: Path,
    *,
    portuguese: bytes = b"trained-por",
    english: bytes = b"trained-eng",
) -> tuple[Path, Path]:
    root.mkdir()
    executable = root / "tesseract.exe"
    executable.write_bytes(b"stub")
    tessdata = root / "tessdata"
    tessdata.mkdir()
    (tessdata / "por.traineddata").write_bytes(portuguese)
    (tessdata / "eng.traineddata").write_bytes(english)
    return executable, tessdata


def _metadata_process(
    arguments: tuple[str, ...],
    *,
    tessdata: Path,
    version: str = "5.4.1.20250101",
) -> CompletedProcess[str] | None:
    if "--version" in arguments:
        return CompletedProcess(
            args=arguments,
            returncode=0,
            stdout=f"tesseract {version}\n leptonica-1.85.0\n",
        )
    if "--list-langs" in arguments:
        return CompletedProcess(
            args=arguments,
            returncode=0,
            stdout=f'List of available languages in "{tessdata}" (2):\neng\npor\n',
        )
    return None


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


def test_tsv_parser_does_not_treat_literal_quotes_as_csv_quoting() -> None:
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            '5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\t"Seu',
            "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t80\tdia",
            '5\t1\t2\t1\t1\t1\t10\t40\t30\t10\t90\tASTA"',
        )
    )

    result = _parse_tsv(tsv, width=100, height=100)

    assert [item.texto for item in result] == ['"Seu dia', 'ASTA"']


@pytest.mark.parametrize("output", ("", "POSTE 11-300\n", "level\ttext\n5\tPOSTE\n"))
def test_tsv_parser_rejects_missing_or_incompatible_header(output: str) -> None:
    with pytest.raises(ValueError, match="cabeçalho TSV"):
        _parse_tsv(output, width=100, height=100)


def test_tsv_parser_accepts_valid_blank_page() -> None:
    output = "\t".join(ocr_module._TSV_COLUMNS) + "\n1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t\n"

    assert _parse_tsv(output, width=100, height=100) == ()


def test_tsv_parser_preserves_group_order_and_skips_malformed_rows() -> None:
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t2\t1\t1\t1\t-10\t90\t30\t20\t120\tSEGUNDA",
            "5\t1\t1\t1\t1\t1\t10\t20\t20\t10\t80\tPRIMEIRA",
            "5\t1\t1\t1\t1\t2\t35\t20\t20\t10\tinválida\tIGNORADA",
            "5\t1\t1\t1\t1\t3\t60\t20\t20\t10\t-1\tIGNORADA",
            "linha\ttruncada",
        )
    )

    result = _parse_tsv(tsv, width=100, height=100)

    assert [item.texto for item in result] == ["PRIMEIRA", "SEGUNDA"]
    assert result[0].caixa_normalizada == (0.1, 0.2, 0.3, 0.3)
    assert result[0].confianca == 0.8
    assert result[1].caixa_normalizada == (0.0, 0.9, 0.2, 1.0)
    assert result[1].confianca == 1.0


@pytest.mark.parametrize(("width", "height"), ((0, 100), (100, 0), (-1, 100)))
def test_tsv_parser_rejects_non_positive_raster_dimensions(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="positivas"):
        _parse_tsv("", width=width, height=height)


def test_capability_is_real_normalized_cached_and_stable_across_machine_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_executable, first_tessdata = _fake_installation(tmp_path / "first")
    second_executable, second_tessdata = _fake_installation(tmp_path / "other-location")
    tessdata_by_executable = {
        str(first_executable.resolve()): first_tessdata.resolve(),
        str(second_executable.resolve()): second_tessdata.resolve(),
    }
    calls: list[tuple[tuple[str, ...], int]] = []

    def fake_run(arguments: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        normalized = tuple(arguments)
        timeout = kwargs["timeout"]
        assert isinstance(timeout, int)
        calls.append((normalized, timeout))
        metadata = _metadata_process(
            normalized,
            tessdata=tessdata_by_executable[normalized[0]],
            version="5.4.1.20250101",
        )
        assert metadata is not None
        return metadata

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    first = ocr_module.TesseractCliOcr(first_executable, capability_timeout_seconds=7)
    second = ocr_module.TesseractCliOcr(second_executable, capability_timeout_seconds=7)

    first_result = first.consultar_capacidade()
    assert first.consultar_capacidade() is first_result
    second_result = second.consultar_capacidade()

    assert first_result.capacidade is not None
    assert second_result.capacidade is not None
    assert first_result.capacidade.versao == "5.4.1.20250101"
    assert first_result.capacidade.idiomas == ("por", "eng")
    assert first_result.capacidade.assinatura() == second_result.capacidade.assinatura()
    legacy = replace(
        first_result.capacidade,
        parametros=tuple(
            (key, value)
            for key, value in first_result.capacidade.parametros
            if key not in ("geracao_tsv", "validacao_tsv")
        ),
    )
    assert first_result.capacidade.assinatura() != legacy.assinatura()
    assert len(calls) == 4
    assert all(timeout == 7 for _, timeout in calls)


@pytest.mark.parametrize(
    "change",
    ("version", "language", "traineddata", "configuration"),
)
def test_capability_signature_changes_with_every_semantic_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    change: str,
) -> None:
    baseline_executable, baseline_tessdata = _fake_installation(tmp_path / "baseline")
    changed_executable, changed_tessdata = _fake_installation(
        tmp_path / "changed",
        portuguese=b"changed-por" if change == "traineddata" else b"trained-por",
    )
    tessdata_by_executable = {
        str(baseline_executable.resolve()): baseline_tessdata.resolve(),
        str(changed_executable.resolve()): changed_tessdata.resolve(),
    }

    def fake_run(arguments: tuple[str, ...], **_kwargs: object) -> CompletedProcess[str]:
        normalized = tuple(arguments)
        version = (
            "5.5.0"
            if change == "version" and normalized[0] == str(changed_executable.resolve())
            else "5.4.1"
        )
        metadata = _metadata_process(
            normalized,
            tessdata=tessdata_by_executable[normalized[0]],
            version=version,
        )
        assert metadata is not None
        return metadata

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    baseline = ocr_module.TesseractCliOcr(baseline_executable, language="por+eng")
    changed = ocr_module.TesseractCliOcr(
        changed_executable,
        language="eng" if change == "language" else "por+eng",
        oem=1 if change == "configuration" else 3,
    )

    baseline_capability = baseline.consultar_capacidade().capacidade
    changed_capability = changed.consultar_capacidade().capacidade

    assert baseline_capability is not None
    assert changed_capability is not None
    assert baseline_capability.assinatura() != changed_capability.assinatura()


def test_capability_timeout_is_diagnostic_and_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, _tessdata = _fake_installation(tmp_path / "timeout")
    calls = 0

    def fake_run(arguments: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        nonlocal calls
        calls += 1
        timeout = kwargs["timeout"]
        assert isinstance(timeout, int)
        raise TimeoutExpired(arguments, timeout)

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, capability_timeout_seconds=3)

    first = engine.consultar_capacidade()
    second = engine.consultar_capacidade()

    assert first is second
    assert first.capacidade is None
    assert [item.codigo for item in first.diagnosticos] == ["analise.ocr_capacidade_timeout"]
    assert calls == 1


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("process", "analise.ocr_capacidade_indisponivel"),
        ("version", "analise.ocr_capacidade_invalida"),
        ("language", "analise.ocr_capacidade_invalida"),
        ("traineddata", "analise.ocr_traineddata_indisponivel"),
    ),
)
def test_capability_failures_return_sanitized_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    executable, tessdata = _fake_installation(tmp_path / failure)

    def fake_run(arguments: tuple[str, ...], **_kwargs: object) -> CompletedProcess[str]:
        normalized = tuple(arguments)
        if failure == "process":
            raise OSError("machine-specific path must not escape")
        if "--version" in normalized:
            output = "unexpected banner" if failure == "version" else "tesseract 5.4.1"
            return CompletedProcess(args=arguments, returncode=0, stdout=output)
        languages = "eng" if failure == "language" else "eng\ndeu"
        return CompletedProcess(
            args=arguments,
            returncode=0,
            stdout=f'List of available languages in "{tessdata}" (2):\n{languages}\n',
        )

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(
        executable,
        language="por" if failure == "language" else "deu" if failure == "traineddata" else "eng",
    )

    result = engine.consultar_capacidade()

    assert result.capacidade is None
    assert [item.codigo for item in result.diagnosticos] == [expected_code]
    assert all("machine-specific" not in item.mensagem for item in result.diagnosticos)


def test_constructor_rejects_invalid_executable_and_semantic_settings(tmp_path: Path) -> None:
    executable, tessdata = _fake_installation(tmp_path / "validation")

    with pytest.raises(ValueError, match="Executável"):
        ocr_module.TesseractCliOcr(tessdata)
    with pytest.raises(ValueError, match="OEM"):
        ocr_module.TesseractCliOcr(executable, oem=4)
    with pytest.raises(ValueError, match="Timeouts"):
        ocr_module.TesseractCliOcr(executable, capability_timeout_seconds=0)


def test_general_ocr_pins_tessdata_language_oem_and_has_no_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, tessdata = _fake_installation(tmp_path / "general")
    captured: list[tuple[tuple[str, ...], dict[str, object]]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t10\t10\t95\tPOSTE",
        )
    )

    def fake_run(
        arguments: tuple[str, ...],
        **kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        normalized = tuple(arguments)
        if metadata := _metadata_process(normalized, tessdata=tessdata):
            return metadata
        captured.append((normalized, kwargs))
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(
        executable,
        language="eng",
        oem=2,
        tessdata_directory=tessdata,
    )
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=450,
    )

    result = engine.reconhecer(page)

    assert [item.texto for item in result] == ["POSTE"]
    arguments, run_options = captured[0]
    child_environment = run_options["env"]
    assert isinstance(child_environment, dict)
    assert child_environment["TESSDATA_PREFIX"] == str(tessdata.resolve())
    assert "--tessdata-dir" not in arguments
    assert arguments[arguments.index("-l") + 1] == "eng"
    assert arguments[arguments.index("--oem") + 1] == "2"
    assert not any(item.startswith("tessedit_char_whitelist=") for item in arguments)
    assert "tessedit_create_tsv=1" in arguments
    assert "tessedit_create_txt=0" in arguments
    assert "tsv" not in arguments


@pytest.mark.parametrize(
    "method",
    (
        "reconhecer",
        "reconhecer_identificador",
        "reconhecer_rotulo_operacional",
        "reconhecer_bloco_operacional",
    ),
)
def test_ocr_without_named_tsv_config_uses_renderer_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
) -> None:
    executable, tessdata = _fake_installation(tmp_path / "managed")
    assert not (tessdata / "configs" / "tsv").exists()
    tsv = "\t".join(ocr_module._TSV_COLUMNS) + "\n5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t86\tP7\n"

    def fake_run(
        arguments: tuple[str, ...],
        **kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        if metadata := _metadata_process(arguments, tessdata=tessdata):
            return metadata
        assert kwargs["timeout"] == 9
        assert kwargs["check"] is True
        # Reproduce the zero-exit plain-text fallback seen in E01 when config is absent.
        if "tsv" in arguments:
            return CompletedProcess(arguments, 0, b"P7\n", b"read_params_file: Can't open tsv")
        assert "tessedit_create_tsv=1" in arguments
        assert "tessedit_create_txt=0" in arguments
        return CompletedProcess(arguments, 0, tsv.encode())

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine = ocr_module.TesseractCliOcr(executable, recognition_timeout_seconds=9)
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=100,
        altura_pixels=100,
        stride=300,
        dados_rgb=b"\xff" * 30000,
        dpi=450,
    )

    result = getattr(engine, method)(page)

    assert result[0].texto == "P7"
    assert result[0].caixa_normalizada == (0.1, 0.2, 0.4, 0.3)
    assert result[0].confianca == 0.86


@pytest.mark.parametrize("failure", ("plain_text", "empty", "timeout"))
def test_recognition_failure_propagates_instead_of_returning_empty_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    executable, tessdata = _fake_installation(tmp_path / failure)

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        if metadata := _metadata_process(arguments, tessdata=tessdata):
            return metadata
        if failure == "timeout":
            raise TimeoutExpired(arguments, 9)
        return CompletedProcess(arguments, 0, b"P7\n" if failure == "plain_text" else b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine = ocr_module.TesseractCliOcr(executable, recognition_timeout_seconds=9)
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=450,
    )

    with pytest.raises(TimeoutExpired if failure == "timeout" else ValueError):
        engine.reconhecer(page)


def test_identifier_ocr_uses_single_character_mode_and_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"trained-eng")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t10\t10\t95\tP7",
        )
    )

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        normalized = tuple(arguments)
        if metadata := _metadata_process(normalized, tessdata=tessdata):
            return metadata
        captured.append(normalized)
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_identificador(page)

    assert [item.texto for item in result] == ["P7"]
    assert "--psm" in captured[0] and "10" in captured[0]
    assert "tessedit_char_whitelist=P0123456789" in captured[0]


def test_operational_label_ocr_uses_single_line_mode_and_technical_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"trained-eng")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t30\t10\t95\tCM2(1)",
        )
    )

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        normalized = tuple(arguments)
        if metadata := _metadata_process(normalized, tessdata=tessdata):
            return metadata
        captured.append(normalized)
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_rotulo_operacional(page)

    assert [item.texto for item in result] == ["CM2(1)"]
    assert "--psm" in captured[0] and "7" in captured[0]
    assert 'tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()-/".,:' in captured[0]


def test_operational_block_ocr_uses_uniform_block_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"trained-eng")
    captured: list[tuple[str, ...]] = []
    tsv = "\n".join(
        (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t1\t1\t30\t10\t95\t11-300",
        )
    )

    def fake_run(
        arguments: tuple[str, ...],
        **_kwargs: object,
    ) -> CompletedProcess[str] | CompletedProcess[bytes]:
        normalized = tuple(arguments)
        if metadata := _metadata_process(normalized, tessdata=tessdata):
            return metadata
        captured.append(normalized)
        return CompletedProcess(args=arguments, returncode=0, stdout=tsv.encode())

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_ocr.subprocess.run",
        fake_run,
    )
    engine = ocr_module.TesseractCliOcr(executable, language="eng")
    page = PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=1,
        altura_pixels=1,
        stride=3,
        dados_rgb=b"\xff\xff\xff",
        dpi=1200,
    )

    result = engine.reconhecer_bloco_operacional(page)

    assert [item.texto for item in result] == ["11-300"]
    assert "--psm" in captured[0] and "6" in captured[0]
