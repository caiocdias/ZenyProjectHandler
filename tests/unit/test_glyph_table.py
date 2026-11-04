from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from zeny_project_handler.adapters.analysis.drawing_model import glyph_table
from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PONTOS_POR_SUBCAMINHO,
    AssinaturaGlifo,
    diferenca_caixa,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    VERSAO_TABELA_GLIFOS,
    EntradaGlifo,
    TabelaGlifos,
    carregar_tabela_glifos,
    resolver_glifo,
    serializar_tabela_glifos,
)


def _contorno(largura: float, altura: float, extra: float = 0.0) -> tuple[tuple[float, float], ...]:
    pontos = []
    n = PONTOS_POR_SUBCAMINHO
    for i in range(n):
        t = i / n
        if t < 0.25:
            ponto = (-largura / 2 + 4 * t * largura, -altura / 2)
        elif t < 0.5:
            ponto = (largura / 2, -altura / 2 + 4 * (t - 0.25) * altura)
        elif t < 0.75:
            ponto = (largura / 2 - 4 * (t - 0.5) * largura, altura / 2)
        else:
            ponto = (-largura / 2, altura / 2 - 4 * (t - 0.75) * altura)
        pontos.append((round(ponto[0] + (extra if i == 3 else 0.0), 4), round(ponto[1], 4)))
    return tuple(pontos)


def _assinatura(largura: float, altura: float, extra: float = 0.0) -> AssinaturaGlifo:
    return AssinaturaGlifo(
        subcaminhos=1,
        caixa=(largura, altura, 0.0),
        contornos=(_contorno(largura, altura, extra),),
    )


def _tabela(*entradas: EntradaGlifo) -> TabelaGlifos:
    return TabelaGlifos(
        versao=VERSAO_TABELA_GLIFOS,
        sha256="0" * 64,
        tolerancia=0.08,
        margem_ambiguidade=0.02,
        espaco=0.38,
        quebra=1.5,
        glifos=entradas,
    )


def _serializar(*entradas: EntradaGlifo) -> str:
    return serializar_tabela_glifos(
        tolerancia=0.08, margem_ambiguidade=0.02, espaco=0.38, quebra=1.5, glifos=entradas
    )


def _arquivo_empacotado() -> Path:
    return Path(glyph_table.__file__).parent.parent / "data" / "tabela-glifos-v1.json"


def test_tabela_empacotada_real_e_valida_e_sem_dados_de_folha() -> None:
    tabela = carregar_tabela_glifos()
    assert tabela.versao == "tabela-glifos-v1"
    assert len(tabela.sha256) == 64
    caracteres = {g.caractere for g in tabela.glifos if g.caractere is not None}
    assert sum(1 for g in tabela.glifos if g.caractere is not None) >= 30
    assert set("0123456789") <= caracteres
    texto = _arquivo_empacotado().read_text(encoding="utf-8").lower()
    for proibido in ("pdf", "png", "sha", "base64"):
        assert proibido not in texto
    assert re.search(r"[0-9a-f]{12,}", texto) is None


def test_ida_e_volta_preserva_a_tabela(tmp_path: Path) -> None:
    entradas = (
        EntradaGlifo("g0002", None, _assinatura(0.3, 0.9)),
        EntradaGlifo("g0001", "P", _assinatura(0.6, 1.0)),
    )
    texto = _serializar(*entradas)
    assert _serializar(*entradas) == texto
    arquivo = tmp_path / "tabela.json"
    arquivo.write_bytes(texto.encode("utf-8"))
    tabela = carregar_tabela_glifos(arquivo)
    assert [g.id for g in tabela.glifos] == ["g0001", "g0002"]
    assert tabela.glifos[0].assinatura == entradas[1].assinatura
    assert tabela.glifos[1].caractere is None
    assert tabela.tolerancia == 0.08 and tabela.quebra == 1.5
    assert _serializar(*tabela.glifos) == texto


def _json_base() -> dict[str, Any]:
    resultado: dict[str, Any] = json.loads(
        _serializar(EntradaGlifo("g0001", "P", _assinatura(0.6, 1.0)))
    )
    return resultado


def _com(mutacao: Any) -> str:
    dados = _json_base()
    mutacao(dados)
    return json.dumps(dados)


def _duplicar_id(d: dict[str, Any]) -> None:
    d["glifos"].append(copy.deepcopy(d["glifos"][0]))


def _contorno_curto(d: dict[str, Any]) -> None:
    d["glifos"][0]["assinatura"]["contornos"][0].pop()


CASOS_INVALIDOS: dict[str, str] = {
    "chave_extra": _com(lambda d: d["glifos"][0].update(png="x")),
    "chave_extra_assinatura": _com(lambda d: d["glifos"][0]["assinatura"].update(png="x")),
    "caractere_com_dois": _com(lambda d: d["glifos"][0].update(caractere="PR")),
    "caractere_espaco": _com(lambda d: d["glifos"][0].update(caractere=" ")),
    "nan": json.dumps(_json_base()).replace('"tolerancia": 0.08', '"tolerancia": NaN'),
    "infinity": json.dumps(_json_base()).replace('"quebra": 1.5', '"quebra": Infinity'),
    "coordenada_grande": _com(
        lambda d: d["glifos"][0]["assinatura"]["contornos"][0].__setitem__(0, [4.5, 0.0])
    ),
    "contorno_curto": _com(_contorno_curto),
    "subcaminhos_diferente": _com(lambda d: d["glifos"][0]["assinatura"].update(subcaminhos=2)),
    "id_repetido": _com(_duplicar_id),
    "schema_version": _com(lambda d: d.update(schema_version=2)),
    "bool_no_lugar_de_numero": _com(lambda d: d.update(tolerancia=True)),
    "bool_na_coordenada": _com(
        lambda d: d["glifos"][0]["assinatura"]["contornos"][0].__setitem__(0, [True, 0.0])
    ),
    "chave_ausente": _com(lambda d: d.pop("espaco")),
    "nao_e_json": "{",
}


@pytest.mark.parametrize("conteudo", list(CASOS_INVALIDOS.values()), ids=list(CASOS_INVALIDOS))
def test_tabela_invalida_e_recusada(tmp_path: Path, conteudo: str) -> None:
    arquivo = tmp_path / "tabela.json"
    arquivo.write_bytes(conteudo.encode("utf-8"))
    with pytest.raises(ValueError):
        carregar_tabela_glifos(arquivo)


def test_arquivo_inexistente_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        carregar_tabela_glifos(tmp_path / "nao-existe.json")


def test_resolver_reconhece_ignora_desconhece_e_detecta_ambiguidade() -> None:
    p = EntradaGlifo("g1", "P", _assinatura(0.6, 1.0))
    r = EntradaGlifo("g2", "R", _assinatura(0.6, 1.0, extra=1.0))
    ignorar = EntradaGlifo("g3", None, _assinatura(0.2, 0.3))
    letra_o = EntradaGlifo("g4", "O", _assinatura(0.8, 0.9))
    zero = EntradaGlifo("g5", "0", _assinatura(0.8, 0.9, extra=0.012))
    tabela = _tabela(p, r, ignorar, letra_o, zero)

    reconhecido = resolver_glifo(tabela, p.assinatura)
    assert (reconhecido.situacao, reconhecido.caractere) == ("reconhecido", "P")
    assert reconhecido.distancia == pytest.approx(0, abs=1e-9)

    ignorado = resolver_glifo(tabela, ignorar.assinatura)
    assert (ignorado.situacao, ignorado.caractere) == ("ignorar", None)

    desconhecido = resolver_glifo(tabela, _assinatura(0.1, 0.1))
    assert (desconhecido.situacao, desconhecido.caractere) == ("desconhecido", None)

    ambiguo = resolver_glifo(tabela, letra_o.assinatura)
    assert (ambiguo.situacao, ambiguo.caractere) == ("ambiguo", None)

    sem_ambiguidade = resolver_glifo(_tabela(letra_o), letra_o.assinatura)
    assert sem_ambiguidade.situacao == "reconhecido"


def _com_caixa(assinatura: AssinaturaGlifo, caixa: tuple[float, float, float]) -> AssinaturaGlifo:
    """Mesmo desenho (contorno) com outra caixa: outra largura, altura ou base relativas a h."""
    return AssinaturaGlifo(subcaminhos=1, caixa=caixa, contornos=assinatura.contornos)


@pytest.mark.parametrize(
    ("caixa", "situacao"),
    [
        ((0.6, 1.06, 0.0), "desconhecido"),  # mesma forma, 6 % mais alta: outro caso (V/v)
        ((0.6, 0.94, 0.0), "desconhecido"),
        ((0.6, 1.03, 0.0), "reconhecido"),
        ((0.6, 0.97, 0.0), "reconhecido"),
        ((0.6, 1.0, 0.06), "reconhecido"),  # a base segue só a tolerância da caixa
        ((0.6, 1.0, -0.06), "reconhecido"),
        ((0.66, 1.0, 0.0), "reconhecido"),  # a largura também
    ],
)
def test_altura_relativa_a_h_tem_tolerancia_propria(
    caixa: tuple[float, float, float], situacao: str
) -> None:
    p = EntradaGlifo("g1", "P", _assinatura(0.6, 1.0))
    glifo = _com_caixa(p.assinatura, caixa)
    assert diferenca_caixa(p.assinatura, glifo) <= 0.08
    assert 0.03 < glyph_table.TOLERANCIA_ALTURA < 0.06
    assert resolver_glifo(_tabela(p), glifo).situacao == situacao


def test_altura_so_reprova_e_nunca_promove_outro_caractere() -> None:
    # o melhor ("Q") falha na altura; o "O", mais distante e de altura compatível, não pode
    # virar a leitura: o glifo fica desconhecido
    glifo = _assinatura(0.6, 1.0)
    q = EntradaGlifo("g1", "Q", _com_caixa(glifo, (0.6, 1.056, 0.0)))
    o = EntradaGlifo("g2", "O", _assinatura(0.6, 1.0, extra=1.872))
    tabela = _tabela(q, o)
    assert (
        distancia_assinaturas(o.assinatura, glifo)
        > distancia_assinaturas(q.assinatura, glifo) + tabela.margem_ambiguidade
    )
    assert distancia_assinaturas(o.assinatura, glifo) <= tabela.tolerancia
    resolucao = resolver_glifo(tabela, glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("desconhecido", None)


def test_variante_do_mesmo_caractere_com_altura_compativel_mantem_a_leitura() -> None:
    glifo = _assinatura(0.6, 1.0)
    alta = EntradaGlifo("g1", "P", _com_caixa(glifo, (0.6, 1.07, 0.0)))
    compativel = EntradaGlifo(
        "g2", "P", _com_caixa(_assinatura(0.6, 1.0, extra=0.6), (0.6, 1.0, 0.0))
    )
    resolucao = resolver_glifo(_tabela(alta, compativel), glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", "P")


def test_outro_caractere_de_contorno_tao_proximo_quanto_o_melhor_e_ambiguo() -> None:
    # "o" casa pela caixa, mas o "O" tem o mesmo desenho: só a caixa decide, e ela vem da
    # altura da própria linha. Falha fechada em vez de afirmar o caractere da caixa mais próxima.
    glifo = _assinatura(0.6, 1.0, extra=0.6)
    minuscula = EntradaGlifo("g1", "o", _assinatura(0.6, 1.0))
    maiuscula = EntradaGlifo("g2", "O", _com_caixa(glifo, (0.67, 1.0, 0.0)))
    tabela = _tabela(minuscula, maiuscula)
    melhor = distancia_assinaturas(minuscula.assinatura, glifo)
    outro = distancia_assinaturas(maiuscula.assinatura, glifo)
    assert outro > melhor + tabela.margem_ambiguidade and outro <= tabela.tolerancia
    assert resolver_glifo(tabela, glifo).situacao == "ambiguo"


def test_outro_caractere_de_desenho_diferente_nao_torna_ambiguo() -> None:
    glifo = _assinatura(0.6, 1.0)
    proprio = EntradaGlifo("g1", "o", _assinatura(0.6, 1.0, extra=0.6))
    outro = EntradaGlifo("g2", "Q", _com_caixa(_assinatura(0.6, 1.0, extra=1.6), (0.6, 1.0, 0.0)))
    tabela = _tabela(proprio, outro)
    assert distancia_assinaturas(outro.assinatura, glifo) <= tabela.tolerancia
    resolucao = resolver_glifo(tabela, glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", "o")


def test_forma_de_outro_caractere_fora_da_caixa_impede_a_leitura() -> None:
    # o desenho do glifo é o do "f", mas a largura do "f" da tabela passa da tolerância; o "t",
    # de desenho mais distante, cabe na tolerância: a forma aponta o "f" e o "t" não é afirmado
    glifo = _assinatura(0.6, 1.0)
    f = EntradaGlifo("g1", "f", _com_caixa(glifo, (0.695, 1.0, 0.0)))
    t = EntradaGlifo("g2", "t", _assinatura(0.6, 1.0, extra=1.44))
    tabela = _tabela(f, t)
    assert diferenca_caixa(f.assinatura, glifo) > tabela.tolerancia
    assert 0.05 < distancia_assinaturas(t.assinatura, glifo) <= tabela.tolerancia
    resolucao = resolver_glifo(tabela, glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("desconhecido", None)


def test_altura_deslocada_nunca_escolhe_outro_caractere_pela_caixa() -> None:
    # "8" e "B": a altura do glifo saiu 0.07 h abaixo da do "8" (h local do trecho); pela
    # distância total, que inclui a caixa, o "B" ficaria mais perto. A forma é a do "8", que a
    # altura reprova: desconhecido, nunca "B"
    glifo = _assinatura(0.6, 1.0)
    oito = EntradaGlifo("g1", "8", _com_caixa(glifo, (0.6, 1.07, 0.0)))
    b = EntradaGlifo("g2", "B", _assinatura(0.6, 1.0, extra=1.2))
    tabela = _tabela(oito, b)
    assert distancia_assinaturas(b.assinatura, glifo) < distancia_assinaturas(
        oito.assinatura, glifo
    )
    resolucao = resolver_glifo(tabela, glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("desconhecido", None)


def test_mesmo_desenho_em_outra_altura_da_linha_nao_disputa_a_forma() -> None:
    # "," e "'" têm o mesmo desenho e só a base os separa: a forma só é comparada com entradas
    # de caixa próxima, e a vírgula continua lida
    glifo = AssinaturaGlifo(1, (0.15, 0.3, 0.2), _assinatura(0.15, 0.3).contornos)
    virgula = EntradaGlifo("g1", ",", glifo)
    apostrofo = EntradaGlifo("g2", "'", _com_caixa(glifo, (0.15, 0.3, -0.6)))
    resolucao = resolver_glifo(_tabela(virgula, apostrofo), glifo)
    assert (resolucao.situacao, resolucao.caractere) == ("reconhecido", ",")


@pytest.mark.parametrize("delta", [-0.08, -0.07, -0.06, 0.06, 0.07, 0.08])
def test_ruido_de_caixa_ate_a_tolerancia_nunca_troca_o_caractere_na_tabela_empacotada(
    delta: float,
) -> None:
    # acima da tolerância de altura a resolução falha fechada; a caixa nunca escolhe outro
    # caractere (antes: "O"/"o", "s"/"S", "c"/"C" e "8"/"B" com a altura a ±0.06 a 0.08)
    tabela = carregar_tabela_glifos()
    trocados = []
    for entrada in tabela.glifos:
        for eixo in range(3):
            caixa = list(entrada.assinatura.caixa)
            caixa[eixo] += delta
            ruidosa = AssinaturaGlifo(
                entrada.assinatura.subcaminhos,
                (caixa[0], caixa[1], caixa[2]),
                entrada.assinatura.contornos,
            )
            r = resolver_glifo(tabela, ruidosa)
            if r.situacao in ("reconhecido", "ignorar") and r.caractere != entrada.caractere:
                trocados.append((entrada.id, entrada.caractere, eixo, r.caractere))
    assert trocados == []


def test_sha256_nao_depende_do_fim_de_linha(tmp_path: Path) -> None:
    texto = _serializar(EntradaGlifo("g0001", "P", _assinatura(0.6, 1.0)))
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(texto.encode("utf-8"))
    crlf.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))
    a, b = carregar_tabela_glifos(lf), carregar_tabela_glifos(crlf)
    assert a.sha256 == b.sha256
    assert a.glifos == b.glifos
