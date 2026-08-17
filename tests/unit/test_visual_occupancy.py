from __future__ import annotations

from uuid import uuid4

from zeny_project_handler.application.visual_occupancy import detectar_ocupacao_visual_rgb


def test_visual_map_accepts_only_regions_without_nonwhite_pixels() -> None:
    width = 40
    height = 32
    pixels = bytearray([255] * width * height * 3)
    for y in range(4, 12):
        for x in range(3, 37):
            offset = (y * width + x) * 3
            pixels[offset : offset + 3] = bytes((40, 40, 40))

    visual_map = detectar_ocupacao_visual_rgb(
        uuid4(),
        largura_pixels=width,
        altura_pixels=height,
        stride=width * 3,
        dados_rgb=memoryview(pixels),
    )

    assert not visual_map.regiao_totalmente_branca(0.0, 0.0, 1.0, 0.5)
    assert visual_map.regiao_totalmente_branca(0.1, 0.55, 0.9, 0.95)


def test_visual_map_treats_a_single_dark_pixel_as_occupied_cell() -> None:
    width = 16
    height = 16
    pixels = bytearray([255] * width * height * 3)
    offset = (7 * width + 7) * 3
    pixels[offset : offset + 3] = bytes((247, 255, 255))

    visual_map = detectar_ocupacao_visual_rgb(
        uuid4(),
        largura_pixels=width,
        altura_pixels=height,
        stride=width * 3,
        dados_rgb=memoryview(pixels),
    )

    assert not visual_map.regiao_totalmente_branca(0.25, 0.25, 0.75, 0.75)
    assert visual_map.regiao_totalmente_branca(0.75, 0.75, 1.0, 1.0)
