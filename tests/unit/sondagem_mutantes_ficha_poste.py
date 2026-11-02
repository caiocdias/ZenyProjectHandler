"""Sondagem de mutantes em memória do CLI de benchmark por poste (ferramenta manual).

Não é um teste coletado pelo pytest (o nome não começa com ``test_``). Uso, da raiz::

    python tests/unit/sondagem_mutantes_ficha_poste.py        # todos os mutantes
    python tests/unit/sondagem_mutantes_ficha_poste.py 7      # só o mutante 7

Cada mutante troca um trecho do fonte de ``scripts/benchmark_ficha_poste.py`` em memória (o
arquivo em disco nunca muda), roda os testes do CLI e deve ser morto (suíte falha). Mutante vivo
indica lacuna de teste.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

RAIZ = Path.cwd()
ALVO = RAIZ / "scripts" / "benchmark_ficha_poste.py"

_BBOX = "return [min(xs), min(ys), max(xs), max(ys)]"
_PONTA = "if vao.poste_origem_id in postes and vao.poste_destino_id in postes"
_AREA = "bbox[0] == bbox[2] or bbox[1] == bbox[3]"
_CLASSE = 'if _erro_classe("simbolo", classe) is not None:'
_DE_PARA = '"de": str(vao.poste_origem_id),\n            "para": str(vao.poste_destino_id),'
_COORD = '"leste": float(coordenada.leste),\n            "norte": float(coordenada.norte),'
_TEMP = (
    'with TemporaryDirectory(prefix="ficha-poste-", dir=saida) as temporario:\n'
    "        variante = run_variant(pdf, Path(temporario), ocr=ocr)"
)
_NATIVO = "    if native_only:\n        return None"

MUTANTES: list[tuple[str, str, str]] = [
    ("pagina constante", "paginas[elemento.geometria.pagina_id],", "1,"),
    ("bbox ymax errado", _BBOX, "return [min(xs), min(ys), max(xs), min(ys)]"),
    ("bbox xmin errado", _BBOX, "return [max(xs), min(ys), max(xs), max(ys)]"),
    ("bbox usa extremos da lista", _BBOX, "return [xs[0], ys[0], xs[-1], ys[-1]]"),
    ("estruturas sem ordenar", '"estruturas": sorted(estruturas),', '"estruturas": estruturas,'),
    (
        "estrutura nula entra",
        "isinstance(elemento, EstruturaMt | EstruturaBt) and elemento.codigo_observado",
        "isinstance(elemento, EstruturaMt | EstruturaBt)",
    ),
    (
        "estrutura so MT",
        "isinstance(elemento, EstruturaMt | EstruturaBt) and",
        "isinstance(elemento, EstruturaMt) and",
    ),
    (
        "poste de simbolo grava classe",
        '"poste": None if de_simbolo else elemento.codigo_observado,',
        '"poste": elemento.codigo_observado,',
    ),
    (
        "origem por valor nao nulo",
        'de_simbolo = "origem_simbolo_ocorrencia_id" in origem',
        'de_simbolo = origem.get("origem_simbolo_ocorrencia_id") is not None',
    ),
    (
        "extras do simbolo vazios",
        '{"origem": "simbolo", "classe_simbolo": elemento.codigo_observado} if de_simbolo else {}',
        "{}",
    ),
    ("vao or em vez de and", _PONTA, _PONTA.replace(" and ", " or ")),
    ("vao sem filtro", "        " + _PONTA + "\n", ""),
    ("classe vazia vira sem simbolo", "if classe is None:", "if not classe:"),
    ("area and em vez de or", _AREA, _AREA.replace(" or ", " and ")),
    ("area so largura", _AREA, "bbox[0] == bbox[2]"),
    ("area so altura", _AREA, "bbox[1] == bbox[3]"),
    ("fora do inventario nao conta", 'contagens["simbolos_fora_do_inventario"] += 1', "pass"),
    ("sem area nao conta", 'contagens["simbolos_sem_area"] += 1', "pass"),
    ("sem simbolo nao conta", 'contagens["equipamentos_sem_simbolo"] += 1', "pass"),
    ("poste ausente nao ignorado", "        if poste is None:\n            continue\n", ""),
    (
        "simbolo no primeiro poste",
        'poste["simbolos"].append(',
        'next(iter(postes.values()))["simbolos"].append(',
    ),
    ("inventario nao checado", _CLASSE, "if False:"),
    (
        "so inventario (classe de poste aceita)",
        _CLASSE,
        'if classe not in __import__("scripts.ficha_poste", fromlist=["x"])'
        "._classes_do_inventario():",
    ),
    ("origem comprimento fixa", "else vao.origem_comprimento.value", "else 'INFORMADO'"),
    (
        "origem comprimento sempre none",
        '"origem_comprimento": None\n                if vao.origem_comprimento is None\n'
        "                else vao.origem_comprimento.value",
        '"origem_comprimento": None',
    ),
    (
        "cabo por identificador",
        "cabos[vao.cabo_id].codigo_observado",
        "cabos[vao.cabo_id].identificador_operacional",
    ),
    ("vao usa pontos", '"de": str(vao.poste_origem_id),', '"de": str(vao.ponto_origem_id),'),
    (
        "de e para trocados",
        _DE_PARA,
        '"de": str(vao.poste_destino_id),\n            "para": str(vao.poste_origem_id),',
    ),
    (
        "comprimento zero em vez de none",
        "None if vao.comprimento_m is None else float(vao.comprimento_m)",
        "0.0 if vao.comprimento_m is None else float(vao.comprimento_m)",
    ),
    ("native_only fixo", '"native_only": native_only,', '"native_only": True,'),
    (
        "versao extracao",
        'VERSAO_EXTRACAO: Final = "projeto-promovido-v1"',
        'VERSAO_EXTRACAO: Final = "projeto-promovido-v2"',
    ),
    (
        "leste norte trocados",
        _COORD,
        '"leste": float(coordenada.norte),\n            "norte": float(coordenada.leste),',
    ),
    ("zona perdida", '"zona": coordenada.zona,', '"zona": None,'),
    (
        "coordenada sempre none",
        '"coordenada": None\n        if coordenada is None\n        else {',
        '"coordenada": None\n        if True\n        else {',
    ),
    (
        "escopo regional",
        '"escopo_anotacao": {"tipo": "completo"},',
        '"escopo_anotacao": {"tipo": "regional"},',
    ),
    ("tipo referencia", '"tipo": "predicao",', '"tipo": "referencia",'),
    ("sha fixo", '"pdf_sha256": pdf_sha256,', '"pdf_sha256": "0" * 64,'),
    ("sha nao checado", 'if ficha_referencia["pdf_sha256"] != antes[2]:', "if False:"),
    (
        "sha invertido",
        'if ficha_referencia["pdf_sha256"] != antes[2]:',
        'if ficha_referencia["pdf_sha256"] == antes[2]:',
    ),
    ("pdf nao reverificado", "if _impressao(pdf) != antes:", "if False:"),
    (
        "so tamanho reverificado",
        "if _impressao(pdf) != antes:",
        "if _impressao(pdf)[0] != antes[0]:",
    ),
    ("sort_keys off", "indent=2, sort_keys=True", "indent=2, sort_keys=False"),
    ("ensure_ascii on", "ensure_ascii=False, indent=2", "ensure_ascii=True, indent=2"),
    ("indent off", "indent=2, sort_keys=True", "indent=None, sort_keys=True"),
    (
        "encoding latin1",
        'encoding="utf-8"\n    )',
        'encoding="latin-1", errors="replace"\n    )',
    ),
    (
        "grava antes de validar",
        "    erros = validar_ficha(predita)\n",
        '    _grava(saida / "ficha-predita.json", predita)\n    erros = validar_ficha(predita)\n',
    ),
    (
        "grava antes de avaliar",
        "    relatorio = avaliar(ficha_referencia, predita)\n",
        '    _grava(saida / "ficha-predita.json", predita)\n'
        "    relatorio = avaliar(ficha_referencia, predita)\n",
    ),
    ("main retorna 1", "    return 0\n\n\nif __name__", "    return 1\n\n\nif __name__"),
    (
        "runtime default",
        'default=Path("tmp/benchmark-runtime")',
        'default=Path("tmp/runtime")',
    ),
    ("native-only default true", 'action="store_true"', 'action="store_false"'),
    (
        "ocr idiomas",
        '"+".join(runtime.idiomas_selecionados)',
        '",".join(runtime.idiomas_selecionados)',
    ),
    ("ocr portugues nao exigido", "if not runtime.portugues_pronto:", "if False:"),
    ("ocr nao verificado", "    verify_ocr(ocr)\n", ""),
    ("native_only inverte", _NATIVO, _NATIVO.replace("if native_only", "if not native_only")),
    ("ocr sempre", _NATIVO + "\n", ""),
    (
        "run_variant recebe ocr None",
        "run_variant(pdf, Path(temporario), ocr=ocr)",
        "run_variant(pdf, Path(temporario), ocr=None)",
    ),
    (
        "ocr nunca preparado",
        "    ocr = _preparar_ocr(runtime_directory, native_only=native_only)\n",
        "    ocr = None\n",
    ),
    ("pdf sem resolve", "pdf = pdf.resolve(strict=True)", "pdf = pdf"),
    (
        "temporario vaza",
        _TEMP,
        'temporario = __import__("tempfile").mkdtemp(prefix="ficha-poste-", dir=saida)\n'
        "    variante = run_variant(pdf, Path(temporario), ocr=ocr)",
    ),
    (
        "json de tipos",
        "return valor if valor is None or isinstance(valor, str | int | float | bool) "
        "else str(valor)",
        "return valor",
    ),
    (
        "gerador versao trocada",
        '"analisador_versao": _json(variante["analyzer"]["version"]),',
        '"analisador_versao": _json(variante["analyzer"]["signature"]),',
    ),
    (
        "pendentes preenchido",
        '"pendentes": [],\n        "atributos_extras": (',
        '"pendentes": ["coordenada"],\n        "atributos_extras": (',
    ),
]


def rodar_um(indice: int) -> int:
    nome, antigo, novo = MUTANTES[indice]
    fonte = ALVO.read_text(encoding="utf-8")
    assert antigo in fonte, f"padrão ausente: {nome}"
    mutado = fonte.replace(antigo, novo, 1)
    sys.path.insert(0, str(RAIZ))
    import scripts  # noqa: F401

    especificacao = importlib.util.spec_from_loader("scripts.benchmark_ficha_poste", loader=None)
    assert especificacao is not None
    modulo = importlib.util.module_from_spec(especificacao)
    modulo.__file__ = str(ALVO)
    sys.modules["scripts.benchmark_ficha_poste"] = modulo
    exec(compile(mutado, str(ALVO), "exec"), modulo.__dict__)
    import pytest

    return int(
        pytest.main(
            [
                "tests/unit/test_benchmark_ficha_poste.py",
                "tests/unit/test_benchmark_ficha_poste_adversarial.py",
                "-q",
                "-x",
                "--no-cov",
                "-p",
                "no:cacheprovider",
            ]
        )
    )


def main() -> None:
    if len(sys.argv) > 1:
        raise SystemExit(rodar_um(int(sys.argv[1])))
    vivos = []
    for indice, (nome, _, _) in enumerate(MUTANTES):
        resultado = subprocess.run(
            [sys.executable, __file__, str(indice)], capture_output=True, text=True, check=False
        )
        if resultado.returncode != 1:
            vivos.append(nome)
            print(resultado.stdout[-400:])
        estado = "MORTO" if resultado.returncode == 1 else f"VIVO(rc={resultado.returncode})"
        print(f"{indice:02d} {nome}: {estado}", flush=True)
    print("VIVOS:", vivos)


if __name__ == "__main__":
    main()
