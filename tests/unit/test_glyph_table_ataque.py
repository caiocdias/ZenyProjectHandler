"""Ataques adversariais à tabela de glifos: validação estrita, resolução, serialização."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PONTOS_POR_SUBCAMINHO,
    AssinaturaGlifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    VERSAO_TABELA_GLIFOS,
    EntradaGlifo,
    TabelaGlifos,
    carregar_tabela_glifos,
    resolver_glifo,
    serializar_tabela_glifos,
)

N = PONTOS_POR_SUBCAMINHO


def _contorno(raio: float = 0.5, deslocamento: float = 0.0, ponto: int = 3) -> tuple[Any, ...]:
    """Quadrado de 24 pontos centrado, com um ponto empurrado em x por `deslocamento`."""
    pontos = []
    for i in range(N):
        t = i / N
        if t < 0.25:
            p = (-raio + 4 * t * 2 * raio, -raio)
        elif t < 0.5:
            p = (raio, -raio + 4 * (t - 0.25) * 2 * raio)
        elif t < 0.75:
            p = (raio - 4 * (t - 0.5) * 2 * raio, raio)
        else:
            p = (-raio, raio - 4 * (t - 0.75) * 2 * raio)
        pontos.append((p[0] + (deslocamento if i == ponto else 0.0), p[1]))
    return tuple(pontos)


def _assinatura(
    deslocamento: float = 0.0, caixa: tuple[float, float, float] = (1.0, 1.0, 0.0)
) -> AssinaturaGlifo:
    return AssinaturaGlifo(subcaminhos=1, caixa=caixa, contornos=(_contorno(0.5, deslocamento),))


def _tabela(
    *entradas: EntradaGlifo, tolerancia: float = 0.08, margem: float = 0.02
) -> TabelaGlifos:
    return TabelaGlifos(
        versao=VERSAO_TABELA_GLIFOS,
        sha256="0" * 64,
        tolerancia=tolerancia,
        margem_ambiguidade=margem,
        espaco=0.38,
        quebra=1.5,
        glifos=entradas,
    )


def _serializar(*entradas: EntradaGlifo) -> str:
    return serializar_tabela_glifos(
        tolerancia=0.08, margem_ambiguidade=0.02, espaco=0.38, quebra=1.5, glifos=entradas
    )


def _base() -> dict[str, Any]:
    resultado: dict[str, Any] = json.loads(_serializar(EntradaGlifo("g0001", "P", _assinatura())))
    return resultado


def _carregar_texto(tmp_path: Path, texto: str) -> TabelaGlifos:
    arquivo = tmp_path / "t.json"
    arquivo.write_bytes(texto.encode("utf-8"))
    return carregar_tabela_glifos(arquivo)


def _carregar_bytes(tmp_path: Path, dados: bytes) -> TabelaGlifos:
    arquivo = tmp_path / "t.json"
    arquivo.write_bytes(dados)
    return carregar_tabela_glifos(arquivo)


# --- resolução ----------------------------------------------------------------------------------


def test_mesmo_caractere_em_duas_entradas_proximas_nao_e_ambiguo() -> None:
    a = EntradaGlifo("g1", "P", _assinatura())
    b = EntradaGlifo("g2", "P", _assinatura(0.01))
    resolucao = resolver_glifo(_tabela(a, b), a.assinatura)
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", "P")


def test_empate_exato_com_caracteres_diferentes_e_ambiguo() -> None:
    a = EntradaGlifo("g1", "O", _assinatura())
    b = EntradaGlifo("g2", "0", _assinatura())
    resolucao = resolver_glifo(_tabela(a, b), _assinatura())
    assert (resolucao.situacao, resolucao.caractere) == ("ambiguo", None)
    assert resolucao.distancia == pytest.approx(0, abs=1e-9)


def test_ambiguidade_nao_depende_da_ordem_das_entradas() -> None:
    a = EntradaGlifo("g1", "O", _assinatura())
    b = EntradaGlifo("g2", "0", _assinatura(0.012))
    assert resolver_glifo(_tabela(a, b), a.assinatura).situacao == "ambiguo"
    assert resolver_glifo(_tabela(b, a), a.assinatura).situacao == "ambiguo"


def test_entrada_ignorar_proxima_de_caractere_real_e_ambigua() -> None:
    letra = EntradaGlifo("g1", "P", _assinatura())
    ignorar = EntradaGlifo("g2", None, _assinatura(0.012))
    resolucao = resolver_glifo(_tabela(letra, ignorar), letra.assinatura)
    assert resolucao.situacao == "ambiguo"


def test_duas_entradas_ignorar_proximas_continuam_ignorar() -> None:
    a = EntradaGlifo("g1", None, _assinatura())
    b = EntradaGlifo("g2", None, _assinatura(0.01))
    resolucao = resolver_glifo(_tabela(a, b), a.assinatura)
    assert (resolucao.situacao, resolucao.caractere) == ("ignorar", None)


def test_segundo_colocado_fora_da_margem_nao_gera_ambiguidade() -> None:
    melhor = EntradaGlifo("g1", "P", _assinatura())
    longe = EntradaGlifo("g2", "R", _assinatura(0.6))
    resolucao = resolver_glifo(_tabela(melhor, longe, tolerancia=0.5, margem=0.01), _assinatura())
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", "P")


def test_terceiro_colocado_de_outro_caractere_na_margem_ainda_e_ambiguo() -> None:
    """P duplicado no topo; R só aparece depois do segundo P, mas dentro da margem do melhor."""
    p1 = EntradaGlifo("g1", "P", _assinatura())
    p2 = EntradaGlifo("g2", "P", _assinatura(0.005))
    r = EntradaGlifo("g3", "R", _assinatura(0.012))
    assert resolver_glifo(_tabela(p1, p2, r), p1.assinatura).situacao == "ambiguo"


def test_distancia_exatamente_na_tolerancia_ainda_reconhece() -> None:
    entrada = EntradaGlifo("g1", "P", _assinatura(caixa=(1.0, 1.0, 0.0)))
    consulta = _assinatura(caixa=(1.5, 1.0, 0.0))
    tabela = _tabela(entrada, tolerancia=0.5)
    assert resolver_glifo(tabela, consulta).situacao == "reconhecido"


def test_distancia_acima_da_tolerancia_e_desconhecida() -> None:
    entrada = EntradaGlifo("g1", "P", _assinatura(caixa=(1.0, 1.0, 0.0)))
    consulta = _assinatura(caixa=(1.5, 1.0, 0.0))
    tabela = _tabela(entrada, tolerancia=0.4999)
    assert resolver_glifo(tabela, consulta).situacao == "desconhecido"


def test_prefiltro_de_caixa_barra_contorno_identico_com_caixa_diferente() -> None:
    entrada = EntradaGlifo("g1", "P", _assinatura(caixa=(1.0, 1.0, 0.0)))
    consulta = _assinatura(caixa=(1.0, 1.0, 0.5))
    assert resolver_glifo(_tabela(entrada), consulta).situacao == "desconhecido"


def test_numero_de_subcaminhos_diferente_nunca_casa() -> None:
    entrada = EntradaGlifo("g1", "P", _assinatura())
    dois = AssinaturaGlifo(2, (1.0, 1.0, 0.0), (_contorno(), _contorno()))
    resolucao = resolver_glifo(_tabela(entrada), dois)
    assert resolucao.situacao == "desconhecido"


def test_tabela_vazia_so_devolve_desconhecido() -> None:
    resolucao = resolver_glifo(_tabela(), _assinatura())
    assert (resolucao.situacao, resolucao.caractere) == ("desconhecido", None)


def test_ambiguidade_ignora_entradas_fora_da_tolerancia() -> None:
    """Uma entrada de outro caractere dentro da margem, mas fora da tolerância, não conta."""
    melhor = EntradaGlifo("g1", "P", _assinatura())
    fora = EntradaGlifo("g2", "R", _assinatura(0.5))
    resolucao = resolver_glifo(_tabela(melhor, fora, tolerancia=0.001, margem=1.0), _assinatura())
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", "P")


def test_resolucao_e_deterministica_com_empate_de_mesmo_caractere() -> None:
    a = EntradaGlifo("g2", "P", _assinatura())
    b = EntradaGlifo("g1", "P", _assinatura())
    primeira = resolver_glifo(_tabela(a, b), _assinatura())
    segunda = resolver_glifo(_tabela(b, a), _assinatura())
    assert primeira == segunda


# --- validação estrita do arquivo ---------------------------------------------------------------


def _mut(mutacao: Any) -> str:
    dados = _base()
    mutacao(dados)
    return json.dumps(dados)


def _ponto_par(d: dict[str, Any], valor: Any) -> None:
    d["glifos"][0]["assinatura"]["contornos"][0][0] = valor


INVALIDOS: dict[str, str] = {
    "subcaminhos_float": _mut(lambda d: d["glifos"][0]["assinatura"].update(subcaminhos=1.0)),
    "subcaminhos_zero_com_contornos_vazios": _mut(
        lambda d: d["glifos"][0]["assinatura"].update(subcaminhos=0, contornos=[])
    ),
    "subcaminhos_bool": _mut(lambda d: d["glifos"][0]["assinatura"].update(subcaminhos=True)),
    "subcaminhos_texto": _mut(lambda d: d["glifos"][0]["assinatura"].update(subcaminhos="1")),
    "versao_diferente": _mut(lambda d: d.update(versao="tabela-glifos-v2")),
    "versao_ausente": _mut(lambda d: d.pop("versao")),
    "schema_version_bool": _mut(lambda d: d.update(schema_version=True)),
    "schema_version_texto": _mut(lambda d: d.update(schema_version="1")),
    "raiz_lista": "[]",
    "raiz_nula": "null",
    "raiz_numero": "1",
    "glifos_dict": _mut(lambda d: d.update(glifos={})),
    "glifos_nulo": _mut(lambda d: d.update(glifos=None)),
    "glifo_nao_objeto": _mut(lambda d: d.update(glifos=[1])),
    "glifo_sem_assinatura": _mut(lambda d: d["glifos"][0].pop("assinatura")),
    "glifo_sem_caractere": _mut(lambda d: d["glifos"][0].pop("caractere")),
    "id_vazio": _mut(lambda d: d["glifos"][0].update(id="")),
    "id_numerico": _mut(lambda d: d["glifos"][0].update(id=1)),
    "id_nulo": _mut(lambda d: d["glifos"][0].update(id=None)),
    "caractere_vazio": _mut(lambda d: d["glifos"][0].update(caractere="")),
    "caractere_numerico": _mut(lambda d: d["glifos"][0].update(caractere=5)),
    "caractere_tab": _mut(lambda d: d["glifos"][0].update(caractere="\t")),
    "caractere_nbsp": _mut(lambda d: d["glifos"][0].update(caractere=chr(0xA0))),
    "caractere_nfd_combinado": _mut(lambda d: d["glifos"][0].update(caractere="e" + chr(0x301))),
    "caractere_lista": _mut(lambda d: d["glifos"][0].update(caractere=["P"])),
    "caixa_com_dois": _mut(lambda d: d["glifos"][0]["assinatura"].update(caixa=[1.0, 1.0])),
    "caixa_com_quatro": _mut(
        lambda d: d["glifos"][0]["assinatura"].update(caixa=[1.0, 1.0, 0.0, 0.0])
    ),
    "caixa_com_texto": _mut(lambda d: d["glifos"][0]["assinatura"].update(caixa=[1.0, "1", 0.0])),
    "caixa_com_bool": _mut(lambda d: d["glifos"][0]["assinatura"].update(caixa=[1.0, 1.0, False])),
    "caixa_nula": _mut(lambda d: d["glifos"][0]["assinatura"].update(caixa=None)),
    "caixa_objeto": _mut(lambda d: d["glifos"][0]["assinatura"].update(caixa={})),
    "contornos_dict": _mut(lambda d: d["glifos"][0]["assinatura"].update(contornos={})),
    "contorno_nao_lista": _mut(lambda d: d["glifos"][0]["assinatura"].update(contornos=[1])),
    "contorno_longo": _mut(lambda d: d["glifos"][0]["assinatura"]["contornos"][0].append([0, 0])),
    "ponto_com_tres": _mut(lambda d: _ponto_par(d, [0.0, 0.0, 0.0])),
    "ponto_com_um": _mut(lambda d: _ponto_par(d, [0.0])),
    "ponto_string": _mut(lambda d: _ponto_par(d, "ab")),
    "ponto_dict": _mut(lambda d: _ponto_par(d, {"x": 0, "y": 0})),
    "ponto_nulo": _mut(lambda d: _ponto_par(d, None)),
    "ponto_com_nulo": _mut(lambda d: _ponto_par(d, [None, 0.0])),
    "ponto_com_texto": _mut(lambda d: _ponto_par(d, ["0", 0.0])),
    "ponto_aninhado": _mut(lambda d: _ponto_par(d, [[0.0], [0.0]])),
    "coordenada_negativa_grande": _mut(lambda d: _ponto_par(d, [0.0, -4.0001])),
    "coordenada_mil": _mut(lambda d: _ponto_par(d, [1000, 0])),
    "expoente_estoura_para_infinito": json.dumps(_base()).replace(
        '"tolerancia": 0.08', '"tolerancia": 1e999'
    ),
    "menos_infinity": json.dumps(_base()).replace('"espaco": 0.38', '"espaco": -Infinity'),
    "nan_na_coordenada": json.dumps(_base()).replace("-0.5, -0.5]", "NaN, -0.5]"),
    "tolerancia_zero": _mut(lambda d: d.update(tolerancia=0)),
    "tolerancia_negativa": _mut(lambda d: d.update(tolerancia=-0.08)),
    "margem_zero": _mut(lambda d: d.update(margem_ambiguidade=0)),
    "espaco_negativo": _mut(lambda d: d.update(espaco=-1)),
    "quebra_zero": _mut(lambda d: d.update(quebra=0)),
    "tolerancia_texto": _mut(lambda d: d.update(tolerancia="0.08")),
    "tolerancia_nula": _mut(lambda d: d.update(tolerancia=None)),
    "tolerancia_lista": _mut(lambda d: d.update(tolerancia=[0.08])),
    "chave_extra_na_raiz": _mut(lambda d: d.update(comentario="x")),
    "chave_extra_no_glifo": _mut(lambda d: d["glifos"][0].update(png="x")),
    "chave_com_caixa_diferente": _mut(lambda d: d.update(Tolerancia=0.08)),
    "ids_repetidos_com_caracteres_diferentes": _mut(
        lambda d: d["glifos"].append({**copy.deepcopy(d["glifos"][0]), "caractere": "R"})
    ),
    "inteiro_gigante_na_caixa": json.dumps(_base()).replace(
        '"caixa": [1.0, 1.0, 0.0]', '"caixa": [1' + "0" * 400 + ", 1.0, 0.0]"
    ),
    "inteiro_gigante_no_parametro": json.dumps(_base()).replace(
        '"quebra": 1.5', '"quebra": 1' + "0" * 400
    ),
    "texto_vazio": "",
    "so_espacos": "   \n",
    "json_truncado": json.dumps(_base())[:-5],
    "json_com_lixo_no_fim": json.dumps(_base()) + " x",
    "dois_documentos": json.dumps(_base()) + json.dumps(_base()),
    "virgula_sobrando": json.dumps(_base())[:-1] + ",}",
}


@pytest.mark.parametrize("conteudo", list(INVALIDOS.values()), ids=list(INVALIDOS))
def test_tabela_malformada_so_levanta_value_error(tmp_path: Path, conteudo: str) -> None:
    with pytest.raises(ValueError):
        _carregar_texto(tmp_path, conteudo)


def test_json_profundamente_aninhado_levanta_value_error_e_nao_recursion_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        _carregar_texto(tmp_path, "[" * 200_000)


def test_json_profundamente_aninhado_dentro_de_glifos_levanta_value_error(tmp_path: Path) -> None:
    dados = json.dumps(_base()).replace(
        '"glifos": [', '"glifos": [' + "[" * 100_000 + "]" * 100_000 + ","
    )
    with pytest.raises(ValueError):
        _carregar_texto(tmp_path, dados)


def test_chave_duplicada_no_json_e_recusada(tmp_path: Path) -> None:
    """Chave repetida em objeto JSON é ambígua (a última vence em silêncio): validação estrita."""
    texto = json.dumps(_base()).replace(
        '"tolerancia": 0.08', '"tolerancia": 0.5, "tolerancia": 0.08'
    )
    with pytest.raises(ValueError):
        _carregar_texto(tmp_path, texto)


def test_schema_version_float_com_mesmo_valor_e_recusada(tmp_path: Path) -> None:
    texto = json.dumps(_base()).replace('"schema_version": 1', '"schema_version": 1.0')
    assert '"schema_version": 1.0' in texto
    with pytest.raises(ValueError):
        _carregar_texto(tmp_path, texto)


def test_bytes_nao_utf8_levantam_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _carregar_bytes(tmp_path, b'{"\xff\xfe": 1}')


def test_bom_utf8_nao_e_aceito_em_silencio_nem_estoura(tmp_path: Path) -> None:
    """Com BOM o arquivo ou é recusado com ValueError ou carrega igual ao sem BOM; nunca outra
    exceção. Aqui exigimos recusa: o sha256 dos bytes com BOM seria outra identidade."""
    texto = _serializar(EntradaGlifo("g0001", "P", _assinatura()))
    with pytest.raises(ValueError):
        _carregar_bytes(tmp_path, b"\xef\xbb\xbf" + texto.encode("utf-8"))


def test_arquivo_vazio_em_bytes_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _carregar_bytes(tmp_path, b"")


def test_diretorio_no_lugar_do_arquivo_levanta_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        carregar_tabela_glifos(tmp_path)


def test_coordenada_no_limite_exato_de_4_e_aceita(tmp_path: Path) -> None:
    dados = _base()
    dados["glifos"][0]["assinatura"]["contornos"][0][0] = [4.0, -4.0]
    tabela = _carregar_texto(tmp_path, json.dumps(dados))
    assert tabela.glifos[0].assinatura.contornos[0][0] == (4.0, -4.0)


def test_caractere_precomposto_nfc_e_aceito_e_preservado(tmp_path: Path) -> None:
    dados = _base()
    dados["glifos"][0]["caractere"] = chr(0xE9)
    tabela = _carregar_texto(tmp_path, json.dumps(dados, ensure_ascii=False))
    assert tabela.glifos[0].caractere == chr(0xE9)


def test_inteiros_validos_no_lugar_de_float_sao_aceitos(tmp_path: Path) -> None:
    dados = _base()
    dados["tolerancia"] = 1
    dados["glifos"][0]["assinatura"]["caixa"] = [1, 1, 0]
    tabela = _carregar_texto(tmp_path, json.dumps(dados))
    assert tabela.tolerancia == 1.0
    assert tabela.glifos[0].assinatura.caixa == (1.0, 1.0, 0.0)


def test_entrada_ignorar_com_caractere_nulo_e_aceita(tmp_path: Path) -> None:
    dados = _base()
    dados["glifos"][0]["caractere"] = None
    tabela = _carregar_texto(tmp_path, json.dumps(dados))
    assert tabela.glifos[0].caractere is None


def test_tabela_grande_carrega_e_mantem_a_ordem_por_id(tmp_path: Path) -> None:
    entradas = [EntradaGlifo(f"g{i:05d}", "P", _assinatura(i * 1e-4)) for i in range(1500)]
    tabela = _carregar_texto(tmp_path, _serializar(*reversed(entradas)))
    assert [g.id for g in tabela.glifos] == [e.id for e in entradas]


# --- sha256 e fim de linha ----------------------------------------------------------------------


def test_sha256_e_dos_bytes_normalizados_em_lf(tmp_path: Path) -> None:
    texto = _serializar(EntradaGlifo("g0001", "P", _assinatura()))
    tabela = _carregar_texto(tmp_path, texto)
    assert tabela.sha256 == hashlib.sha256(texto.encode("utf-8")).hexdigest()


def test_sha256_muda_quando_o_conteudo_muda(tmp_path: Path) -> None:
    a = _carregar_texto(tmp_path, _serializar(EntradaGlifo("g0001", "P", _assinatura())))
    b = _carregar_texto(tmp_path, _serializar(EntradaGlifo("g0001", "R", _assinatura())))
    assert a.sha256 != b.sha256


def test_crlf_em_json_de_uma_linha_so_nao_altera_o_sha256(tmp_path: Path) -> None:
    texto = _serializar(EntradaGlifo("g0001", "P", _assinatura()))
    assert texto.count("\n") == 1
    lf = _carregar_texto(tmp_path, texto)
    crlf = _carregar_bytes(tmp_path, texto.replace("\n", "\r\n").encode("utf-8"))
    assert lf.sha256 == crlf.sha256


def test_json_indentado_com_crlf_tem_o_mesmo_sha256_que_com_lf(tmp_path: Path) -> None:
    texto = json.dumps(_base(), indent=2) + "\n"
    lf = _carregar_texto(tmp_path, texto)
    crlf = _carregar_bytes(tmp_path, texto.replace("\n", "\r\n").encode("utf-8"))
    assert lf.sha256 == crlf.sha256


# --- serialização -------------------------------------------------------------------------------


def test_serializacao_independe_da_ordem_das_entradas() -> None:
    a = EntradaGlifo("g0002", "R", _assinatura(0.1))
    b = EntradaGlifo("g0001", "P", _assinatura())
    c = EntradaGlifo("g0003", None, _assinatura(0.2))
    assert _serializar(a, b, c) == _serializar(c, b, a) == _serializar(b, c, a)


def test_serializacao_termina_em_lf_sem_cr_e_tem_chaves_ordenadas() -> None:
    texto = _serializar(EntradaGlifo("g0001", "P", _assinatura()))
    assert texto.endswith("\n") and "\r" not in texto
    dados = json.loads(texto)
    assert list(dados) == sorted(dados)
    assert list(dados["glifos"][0]) == sorted(dados["glifos"][0])


def test_serializacao_arredonda_a_4_casas() -> None:
    entrada = EntradaGlifo("g0001", "P", _assinatura(0.123456789))
    dados = json.loads(_serializar(entrada))
    for contorno in dados["glifos"][0]["assinatura"]["contornos"]:
        for x, y in contorno:
            assert round(x, 4) == x and round(y, 4) == y


def test_serializacao_nao_emite_menos_zero() -> None:
    contorno = tuple((-1e-9, -1e-9) for _ in range(N))
    assinatura = AssinaturaGlifo(1, (-1e-9, 1.0, -1e-12), (contorno,))
    texto = _serializar(EntradaGlifo("g0001", "P", assinatura))
    assert "-0.0" not in texto


def test_serializacao_preserva_caracteres_especiais_em_ida_e_volta(tmp_path: Path) -> None:
    for caractere in ['"', "\\", chr(0xE9), chr(0xB0), "/", chr(0x2264)]:
        texto = _serializar(EntradaGlifo("g0001", caractere, _assinatura()))
        assert _carregar_texto(tmp_path, texto).glifos[0].caractere == caractere


def test_ida_e_volta_com_valores_ja_arredondados_e_idempotente(tmp_path: Path) -> None:
    entradas = (
        EntradaGlifo("g0001", "P", _assinatura(0.123456)),
        EntradaGlifo("g0002", None, _assinatura(0.3333333)),
    )
    primeiro = _serializar(*entradas)
    tabela = _carregar_texto(tmp_path, primeiro)
    segundo = serializar_tabela_glifos(
        tolerancia=tabela.tolerancia,
        margem_ambiguidade=tabela.margem_ambiguidade,
        espaco=tabela.espaco,
        quebra=tabela.quebra,
        glifos=tabela.glifos,
    )
    assert segundo == primeiro


def test_serializacao_nao_altera_a_lista_de_entrada() -> None:
    entradas = [EntradaGlifo("g2", "R", _assinatura()), EntradaGlifo("g1", "P", _assinatura())]
    _serializar(*entradas)
    assert [e.id for e in entradas] == ["g2", "g1"]


# --- tabela empacotada --------------------------------------------------------------------------


def _arquivo_empacotado() -> Path:
    raiz = Path(__file__).resolve().parents[2]
    return raiz / "src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json"


def test_arquivo_empacotado_e_exatamente_a_saida_do_serializador() -> None:
    tabela = carregar_tabela_glifos()
    esperado = serializar_tabela_glifos(
        tolerancia=tabela.tolerancia,
        margem_ambiguidade=tabela.margem_ambiguidade,
        espaco=tabela.espaco,
        quebra=tabela.quebra,
        glifos=tabela.glifos,
    )
    atual = _arquivo_empacotado().read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert atual == esperado


def test_tabela_empacotada_tem_os_parametros_publicados_e_sha_dos_bytes() -> None:
    tabela = carregar_tabela_glifos()
    assert (tabela.tolerancia, tabela.margem_ambiguidade) == (0.08, 0.02)
    assert (tabela.espaco, tabela.quebra) == (0.43, 1.5)
    bytes_lf = _arquivo_empacotado().read_bytes().replace(b"\r\n", b"\n")
    assert tabela.sha256 == hashlib.sha256(bytes_lf).hexdigest()


def test_tabela_empacotada_e_igual_a_carga_por_caminho() -> None:
    assert carregar_tabela_glifos() == carregar_tabela_glifos(_arquivo_empacotado())
