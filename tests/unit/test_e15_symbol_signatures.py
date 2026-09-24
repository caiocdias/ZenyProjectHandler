"""E15: assinatura de capacidade cobre as entradas operacionais do servidor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from zeny_project_handler.adapters.analysis.raster_symbols import carregar_templates_raster
from zeny_project_handler.application.symbol_reconciliation import CalibrationPolicy
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner


def _settings(
    data: Path,
    *,
    symbol_profile: str = "balanced",
    symbol_calibration_version: str = "e12-uncalibrated-1",
    symbol_raster_dpi: int = 144,
    symbol_tile_pixels: int = 768,
    symbol_tile_max_bytes: int = 64_000_000,
    symbol_model_path: Path | None = None,
) -> ServerSettings:
    return ServerSettings(
        password="senha segura de assinatura E15",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        symbol_composition=True,
        symbol_profile=symbol_profile,
        symbol_calibration_version=symbol_calibration_version,
        symbol_raster_dpi=symbol_raster_dpi,
        symbol_tile_pixels=symbol_tile_pixels,
        symbol_tile_max_bytes=symbol_tile_max_bytes,
        symbol_model_path=symbol_model_path,
    )


def test_signature_changes_with_model_profile_calibration_and_rendering(tmp_path: Path) -> None:
    baseline = _settings(tmp_path)
    original = SymbolCompositionRunner(baseline).signature
    assert original == SymbolCompositionRunner(baseline).signature

    variants = (
        _settings(tmp_path, symbol_profile="vector-only"),
        _settings(tmp_path, symbol_calibration_version="e15-calibration-test-2"),
        _settings(tmp_path, symbol_raster_dpi=150),
        _settings(tmp_path, symbol_tile_pixels=512),
        _settings(tmp_path, symbol_tile_max_bytes=8_000_000),
    )
    assert all(SymbolCompositionRunner(option).signature != original for option in variants)
    assert len({SymbolCompositionRunner(option).signature for option in variants}) == len(variants)

    model = tmp_path / "model.bin"
    model.write_bytes(b"model-v1")
    with_model = _settings(tmp_path, symbol_model_path=model)
    first_model_signature = SymbolCompositionRunner(with_model).signature
    assert first_model_signature != original
    model.write_bytes(b"model-v2")
    assert SymbolCompositionRunner(with_model).signature != first_model_signature

    templates = carregar_templates_raster()
    changed_template = replace(templates[0], id=f"{templates[0].id}-changed")
    assert (
        SymbolCompositionRunner(baseline, templates=(changed_template, *templates[1:])).signature
        != original
    )
    assert (
        SymbolCompositionRunner(
            baseline, calibration=CalibrationPolicy(minimum_samples=31)
        ).signature
        != original
    )


def test_opt_in_is_explicit_and_invalid_profile_rejected(tmp_path: Path) -> None:
    environment = {
        "ZENY_SERVER_PASSWORD": "senha segura de ambiente E15",
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": "fixture-market-connection",
        "ZENY_SERVER_DATA_DIR": str(tmp_path),
    }
    assert not ServerSettings.from_environment(environment).symbol_composition
    enabled = ServerSettings.from_environment(
        {**environment, "ZENY_SERVER_SYMBOL_COMPOSITION": "true"}
    )
    assert enabled.symbol_composition
    with pytest.raises(ValueError, match="SYMBOL_PROFILE"):
        _settings(tmp_path, symbol_profile="unknown")
