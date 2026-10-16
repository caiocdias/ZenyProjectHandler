"""Rodada de curadoria: corpus, ondas, reuso por hash e máquina de fases por PDF."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_round import (
    FASES,
    RodadaError,
    TransicaoInvalidaError,
    caminho_pdf_fonte,
    carregar_checkpoint,
    carregar_rodada,
    checkpoint_codigo,
    diretorio_pdf,
    escrever_json_atomico,
    iniciar_rodada,
    main,
    resumo_status,
    selecionar_pdfs,
    transicionar,
)
from tests.pdf_fixtures import create_catalog_pdf, create_feature_pdf

AGORA = "2026-10-15T12:00:00+00:00"


def _corpus(raiz: Path) -> Path:
    """Quatro PDFs sintéticos, um deles cópia byte a byte de outro."""
    (raiz / "sub").mkdir(parents=True)
    create_catalog_pdf(raiz / "b.pdf", "CODIGO-B")
    create_feature_pdf(raiz / "A.PDF")
    create_catalog_pdf(raiz / "sub" / "c.pdf", "CODIGO-C")
    shutil.copyfile(raiz / "b.pdf", raiz / "sub" / "copia-b.pdf")
    (raiz / "notas.txt").write_text("não é PDF", encoding="utf-8")
    return raiz


def _iniciar(tmp_path: Path, nome: str = "rodada", **opcoes: Any) -> Path:
    rodada = tmp_path / nome
    opcoes.setdefault("concorrencia", 3)
    opcoes.setdefault("raiz_repositorio", tmp_path / "sem-git")
    opcoes.setdefault("agora", AGORA)
    iniciar_rodada(rodada, tmp_path / "corpus", **opcoes)
    return rodada


def _id_por_caminho(rodada: Path, caminho: str) -> str:
    for item in carregar_rodada(rodada)["pdfs"]:
        if item["caminho_relativo"] == caminho:
            return str(item["pdf_id"])
    raise AssertionError(caminho)


def _congelar(rodada: Path, pdf_id: str, conteudo: str = '{"observacoes": []}\n') -> Path:
    transicionar(rodada, pdf_id, "renderizado", agora=AGORA)
    referencia = diretorio_pdf(rodada, pdf_id) / "referencia" / "referencia-v001.json"
    referencia.parent.mkdir(parents=True)
    referencia.write_text(conteudo, encoding="utf-8")
    transicionar(rodada, pdf_id, "referencia_congelada", artefatos=[referencia], agora=AGORA)
    return referencia


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return _corpus(tmp_path / "corpus")


@pytest.mark.usefixtures("corpus")
def test_init_descobre_ordena_divide_ondas_e_lista_duplicatas(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)

    dados = carregar_rodada(rodada)
    caminhos = [item["caminho_relativo"] for item in dados["pdfs"]]
    assert caminhos == ["A.PDF", "b.pdf", "sub/c.pdf", "sub/copia-b.pdf"]
    assert [item["ordem"] for item in dados["pdfs"]] == [1, 2, 3, 4]
    assert dados["concorrencia"] == 3
    assert [onda["pdfs"] for onda in dados["ondas"]] == [
        [item["pdf_id"] for item in dados["pdfs"][:3]],
        [dados["pdfs"][3]["pdf_id"]],
    ]
    paginas = {item["caminho_relativo"]: item["paginas"] for item in dados["pdfs"]}
    assert paginas == {"A.PDF": 3, "b.pdf": 1, "sub/c.pdf": 1, "sub/copia-b.pdf": 1}
    assert len(dados["duplicatas"]) == 1
    assert dados["totais"]["grupos_duplicados"] == 1
    assert dados["totais"]["pdfs_em_duplicata"] == 2
    duplicata = dados["duplicatas"][0]
    assert duplicata["caminhos"] == ["b.pdf", "sub/copia-b.pdf"]
    assert len(duplicata["pdf_ids"]) == 2
    assert duplicata["sha256"] == dados["pdfs"][1]["sha256"] == dados["pdfs"][3]["sha256"]
    for item in dados["pdfs"]:
        assert item["pdf_id"] == f"{item['ordem']:03d}-{item['sha256'][:12]}"
        assert item["bytes"] == (tmp_path / "corpus" / item["caminho_relativo"]).stat().st_size
        assert item["estado_frente_anterior"] == "novo"
        checkpoint = carregar_checkpoint(rodada, item["pdf_id"])
        assert checkpoint["fase"] == "preparado"
        assert checkpoint["sha256"] == item["sha256"]
        assert checkpoint["onda"] == item["onda"]
        assert (rodada / "pdfs" / item["pdf_id"] / "checkpoint.json").is_file()
    assert len(list((rodada / "pdfs").iterdir())) == 4


@pytest.mark.usefixtures("corpus")
def test_rodada_json_nao_grava_caminhos_absolutos(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    texto = (rodada / "rodada.json").read_text(encoding="utf-8")
    absolutos = {str(tmp_path), tmp_path.as_posix(), str(tmp_path).replace("\\", "\\\\")}
    assert not any(marca in texto for marca in absolutos)
    dados = carregar_rodada(rodada)
    assert not Path(dados["raiz_corpus"]).is_absolute()
    pdf_id = dados["pdfs"][0]["pdf_id"]
    assert caminho_pdf_fonte(rodada, pdf_id) == (tmp_path / "corpus" / "A.PDF").resolve()


@pytest.mark.usefixtures("corpus")
def test_init_e_deterministico(tmp_path: Path) -> None:
    primeira = _iniciar(tmp_path, "r1")
    segunda = _iniciar(tmp_path, "r2")
    assert (primeira / "rodada.json").read_bytes() == (segunda / "rodada.json").read_bytes()
    for item in carregar_rodada(primeira)["pdfs"]:
        relativo = Path("pdfs") / item["pdf_id"] / "checkpoint.json"
        assert (primeira / relativo).read_bytes() == (segunda / relativo).read_bytes()


@pytest.mark.parametrize("concorrencia", [0, 6, -1])
@pytest.mark.usefixtures("corpus")
def test_concorrencia_fora_do_intervalo_e_recusada(tmp_path: Path, concorrencia: int) -> None:
    with pytest.raises(RodadaError, match="concorrência"):
        _iniciar(tmp_path, concorrencia=concorrencia)
    assert not (tmp_path / "rodada").exists()


@pytest.mark.usefixtures("corpus")
def test_cli_recusa_concorrencia_invalida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo = main(
        [
            "init",
            "--rodada",
            str(tmp_path / "rodada"),
            "--raiz",
            str(tmp_path / "corpus"),
            "--concorrencia",
            "6",
        ]
    )
    assert codigo != 0
    assert "concorrência" in capsys.readouterr().err
    assert not (tmp_path / "rodada" / "rodada.json").exists()


@pytest.mark.parametrize(("concorrencia", "tamanhos"), [(1, [1, 1, 1, 1]), (5, [4]), (2, [2, 2])])
@pytest.mark.usefixtures("corpus")
def test_ondas_respeitam_o_tamanho_pedido(
    tmp_path: Path, concorrencia: int, tamanhos: list[int]
) -> None:
    rodada = _iniciar(tmp_path, concorrencia=concorrencia)
    dados = carregar_rodada(rodada)
    assert [len(onda["pdfs"]) for onda in dados["ondas"]] == tamanhos
    assert [onda["numero"] for onda in dados["ondas"]] == list(range(1, len(tamanhos) + 1))


def test_init_recusa_corpus_vazio_e_rodada_existente(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    with pytest.raises(RodadaError, match="nenhum PDF"):
        _iniciar(tmp_path)
    create_catalog_pdf(tmp_path / "corpus" / "a.pdf", "A")
    rodada = _iniciar(tmp_path)
    antes = (rodada / "rodada.json").read_bytes()
    with pytest.raises(RodadaError, match=r"rodada\.json"):
        _iniciar(tmp_path)
    assert (rodada / "rodada.json").read_bytes() == antes


@pytest.mark.usefixtures("corpus")
def test_estado_frente_a_rodada_anterior(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    create_catalog_pdf(tmp_path / "corpus" / "sub" / "c.pdf", "CODIGO-C-ALTERADO")
    create_catalog_pdf(tmp_path / "corpus" / "novo.pdf", "NOVO")
    atual = _iniciar(tmp_path, "atual", anterior=anterior)

    dados = carregar_rodada(atual)
    estados = {item["caminho_relativo"]: item["estado_frente_anterior"] for item in dados["pdfs"]}
    assert estados == {
        "A.PDF": "inalterado",
        "b.pdf": "inalterado",
        "novo.pdf": "novo",
        "sub/c.pdf": "modificado",
        "sub/copia-b.pdf": "inalterado",
    }
    assert dados["rodada_anterior"]["caminho"] == "../anterior"
    assert dados["rodada_anterior"]["criada_em"] == AGORA


@pytest.mark.usefixtures("corpus")
def test_reuso_copia_referencia_com_hash_conferido(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    id_anterior = _id_por_caminho(anterior, "b.pdf")
    original = _congelar(anterior, id_anterior, '{"leitura": "b"}\n')
    id_modificado = _id_por_caminho(anterior, "sub/c.pdf")
    _congelar(anterior, id_modificado)
    create_catalog_pdf(tmp_path / "corpus" / "sub" / "c.pdf", "CODIGO-C-ALTERADO")

    atual = _iniciar(tmp_path, "atual", anterior=anterior)

    pdf_id = _id_por_caminho(atual, "b.pdf")
    checkpoint = carregar_checkpoint(atual, pdf_id)
    assert checkpoint["fase"] == "referencia_congelada"
    referencia = checkpoint["referencia"]
    assert referencia["origem"] == "reuso"
    assert referencia["arquivo"] == f"pdfs/{pdf_id}/referencia/referencia-v001.json"
    copia = atual / referencia["arquivo"]
    assert copia.read_bytes() == original.read_bytes()
    assert referencia["rodada_anterior"]["pdf_id"] == id_anterior
    assert referencia["rodada_anterior"]["sha256"] == referencia["sha256"]
    assert set(checkpoint["marcos"]) == {"preparado", "referencia_congelada"}
    assert checkpoint["historico"][-1]["para"] == "referencia_congelada"
    reuso = {
        item["caminho_relativo"]: item["reuso_referencia"]
        for item in carregar_rodada(atual)["pdfs"]
    }
    assert reuso == {"A.PDF": False, "b.pdf": True, "sub/c.pdf": False, "sub/copia-b.pdf": False}
    assert carregar_checkpoint(atual, _id_por_caminho(atual, "sub/c.pdf"))["fase"] == "preparado"


@pytest.mark.usefixtures("corpus")
def test_reuso_com_hash_de_referencia_adulterado_falha(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    referencia = _congelar(anterior, _id_por_caminho(anterior, "b.pdf"))
    referencia.write_text('{"observacoes": ["adulterada"]}\n', encoding="utf-8")

    with pytest.raises(RodadaError, match="SHA-256 da referência") as erro:
        _iniciar(tmp_path, "atual", anterior=anterior)
    assert "b.pdf" in str(erro.value)
    assert not (tmp_path / "atual").exists()


@pytest.mark.usefixtures("corpus")
def test_reuso_com_referencia_ausente_falha(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    _congelar(anterior, _id_por_caminho(anterior, "b.pdf")).unlink()
    with pytest.raises(RodadaError, match="referência"):
        _iniciar(tmp_path, "atual", anterior=anterior)


@pytest.mark.usefixtures("corpus")
def test_sem_reuso_nenhum_pdf_reutiliza(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    _congelar(anterior, _id_por_caminho(anterior, "b.pdf"))
    atual = _iniciar(tmp_path, "atual", anterior=anterior, reusar_referencias=False)
    dados = carregar_rodada(atual)
    assert dados["reuso_referencias"] is False
    for item in dados["pdfs"]:
        assert item["reuso_referencia"] is False
        assert carregar_checkpoint(atual, item["pdf_id"])["fase"] == "preparado"
    assert not list(atual.glob("pdfs/*/referencia"))


def test_cli_init_reuso_padrao_e_opcao_sem_reuso(tmp_path: Path, corpus: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    _congelar(anterior, _id_por_caminho(anterior, "b.pdf"))
    base = ["init", "--raiz", str(corpus), "--concorrencia", "3", "--anterior", str(anterior)]
    assert main([*base, "--rodada", str(tmp_path / "padrao")]) == 0
    assert main([*base, "--rodada", str(tmp_path / "sem"), "--sem-reuso"]) == 0
    assert main([*base, "--rodada", str(tmp_path / "com"), "--reusar-referencias"]) == 0
    reutilizados = {
        nome: sum(item["reuso_referencia"] for item in carregar_rodada(tmp_path / nome)["pdfs"])
        for nome in ("padrao", "sem", "com")
    }
    assert reutilizados == {"padrao": 1, "sem": 0, "com": 1}
    with pytest.raises(SystemExit):
        main([*base, "--rodada", str(tmp_path / "x"), "--sem-reuso", "--reusar-referencias"])


@pytest.mark.usefixtures("corpus")
def test_transicoes_validas_ate_fechado(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    pasta = diretorio_pdf(rodada, pdf_id)
    inferencia = pasta / "inferencia-v001" / "simbolos"
    inferencia.mkdir(parents=True)
    (inferencia / "predictions.json").write_text("{}\n", encoding="utf-8")

    transicionar(rodada, pdf_id, "inferido", artefatos=[inferencia.parent], agora=AGORA)
    _congelar(rodada, pdf_id)
    comparacao = pasta / "comparacao-v001.json"
    comparacao.write_text("{}\n", encoding="utf-8")
    transicionar(rodada, pdf_id, "comparado", artefatos=[comparacao], agora=AGORA)
    transicionar(rodada, pdf_id, "auditado", agora=AGORA, nota="concordância 1,0")
    checkpoint = transicionar(rodada, pdf_id, "fechado", agora=AGORA)

    assert checkpoint["fase"] == "fechado"
    assert [evento["para"] for evento in checkpoint["historico"]] == [
        "preparado",
        "inferido",
        "renderizado",
        "referencia_congelada",
        "comparado",
        "auditado",
        "fechado",
    ]
    assert checkpoint["historico"][1]["de"] == "preparado"
    assert all(evento["horario"] == AGORA for evento in checkpoint["historico"])
    assert checkpoint["historico"][5]["nota"] == "concordância 1,0"
    artefato = checkpoint["historico"][1]["artefatos"][0]
    assert artefato["caminho"] == f"pdfs/{pdf_id}/inferencia-v001"
    assert artefato["tipo"] == "diretorio"
    assert len(artefato["sha256"]) == 64
    assert checkpoint["referencia"]["origem"] == "leitura"
    assert carregar_checkpoint(rodada, pdf_id) == checkpoint


@pytest.mark.usefixtures("corpus")
def test_hash_de_artefato_muda_com_o_conteudo(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    alvo = diretorio_pdf(rodada, pdf_id) / "render" / "indice-tiles.json"
    alvo.parent.mkdir()
    alvo.write_text('{"tiles": 1}\n', encoding="utf-8")
    primeiro = transicionar(rodada, pdf_id, "renderizado", artefatos=[alvo], agora=AGORA)
    registro = primeiro["historico"][-1]["artefatos"][0]
    assert registro == {
        "caminho": f"pdfs/{pdf_id}/render/indice-tiles.json",
        "tipo": "arquivo",
        "bytes": alvo.stat().st_size,
        "sha256": hashlib.sha256(alvo.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize(
    ("preparar", "fase"),
    [
        ([], "comparado"),
        (["inferido"], "comparado"),
        (["renderizado", "referencia_congelada"], "comparado"),
        ([], "referencia_congelada"),
        ([], "fechado"),
        (["inferido", "renderizado", "referencia_congelada", "comparado"], "fechado"),
        (["renderizado", "referencia_congelada"], "fechado"),
        ([], "em_correcao"),
        ([], "preparado"),
        ([], "auditado"),
        ([], "fase_inexistente"),
    ],
)
@pytest.mark.usefixtures("corpus")
def test_transicoes_invalidas_sao_recusadas_sem_alterar_checkpoint(
    tmp_path: Path, preparar: list[str], fase: str
) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    for anterior in preparar:
        if anterior == "referencia_congelada":
            referencia = diretorio_pdf(rodada, pdf_id) / "referencia" / "referencia-v001.json"
            referencia.parent.mkdir(parents=True)
            referencia.write_text("{}\n", encoding="utf-8")
            transicionar(rodada, pdf_id, anterior, artefatos=[referencia], agora=AGORA)
        else:
            transicionar(rodada, pdf_id, anterior, agora=AGORA)
    arquivo = diretorio_pdf(rodada, pdf_id) / "checkpoint.json"
    antes = arquivo.read_bytes()

    with pytest.raises(TransicaoInvalidaError):
        transicionar(rodada, pdf_id, fase, agora=AGORA)
    assert arquivo.read_bytes() == antes


@pytest.mark.usefixtures("corpus")
def test_cli_avancar_para_comparado_sem_requisitos_falha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    arquivo = diretorio_pdf(rodada, pdf_id) / "checkpoint.json"
    antes = arquivo.read_bytes()

    codigo = main(["avancar", "--rodada", str(rodada), "--pdf", pdf_id, "--fase", "comparado"])

    assert codigo != 0
    erro = capsys.readouterr().err
    assert "inferido" in erro
    assert "referencia_congelada" in erro
    assert arquivo.read_bytes() == antes


@pytest.mark.usefixtures("corpus")
def test_fases_terminais_nao_aceitam_transicao(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    with pytest.raises(TransicaoInvalidaError, match="nota"):
        transicionar(rodada, pdf_id, "encerrado_com_pendencias", agora=AGORA)
    transicionar(
        rodada, pdf_id, "encerrado_com_pendencias", nota="método indisponível", agora=AGORA
    )
    for fase in FASES:
        with pytest.raises(TransicaoInvalidaError):
            transicionar(rodada, pdf_id, fase, nota="x", agora=AGORA)


@pytest.mark.usefixtures("corpus")
def test_reinferencia_e_correcao_exigem_nova_comparacao(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    transicionar(rodada, pdf_id, "inferido", agora=AGORA)
    _congelar(rodada, pdf_id)
    transicionar(rodada, pdf_id, "comparado", agora=AGORA)
    transicionar(rodada, pdf_id, "auditado", agora=AGORA)
    transicionar(rodada, pdf_id, "em_correcao", agora=AGORA)
    with pytest.raises(TransicaoInvalidaError, match="comparado"):
        transicionar(rodada, pdf_id, "fechado", agora=AGORA)
    transicionar(rodada, pdf_id, "inferido", agora=AGORA)
    with pytest.raises(TransicaoInvalidaError, match="comparado"):
        transicionar(rodada, pdf_id, "fechado", agora=AGORA)
    transicionar(rodada, pdf_id, "comparado", agora=AGORA)
    assert transicionar(rodada, pdf_id, "fechado", agora=AGORA)["fase"] == "fechado"


@pytest.mark.usefixtures("corpus")
def test_nova_versao_da_referencia_exige_nova_comparacao_e_nova_auditoria(
    tmp_path: Path,
) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    transicionar(rodada, pdf_id, "inferido", agora=AGORA)
    _congelar(rodada, pdf_id)
    transicionar(rodada, pdf_id, "comparado", agora=AGORA)
    transicionar(rodada, pdf_id, "auditado", agora=AGORA)
    revisada = diretorio_pdf(rodada, pdf_id) / "referencia" / "referencia-v002.json"
    revisada.write_text('{"observacoes": [1]}\n', encoding="utf-8")
    checkpoint = transicionar(
        rodada,
        pdf_id,
        "referencia_congelada",
        artefatos=[revisada],
        origem_referencia="revisao",
        agora=AGORA,
    )
    assert "auditado" not in checkpoint["marcos"]
    assert "comparado" not in checkpoint["marcos"]
    transicionar(rodada, pdf_id, "comparado", agora=AGORA)
    with pytest.raises(TransicaoInvalidaError, match="auditado"):
        transicionar(rodada, pdf_id, "fechado", agora=AGORA)
    transicionar(rodada, pdf_id, "auditado", agora=AGORA)
    assert transicionar(rodada, pdf_id, "fechado", agora=AGORA)["fase"] == "fechado"


@pytest.mark.usefixtures("corpus")
def test_rerenderizar_apos_congelar_e_recusado(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    transicionar(rodada, pdf_id, "renderizado", agora=AGORA)
    transicionar(rodada, pdf_id, "renderizado", agora=AGORA)
    referencia = diretorio_pdf(rodada, pdf_id) / "referencia" / "referencia-v001.json"
    referencia.parent.mkdir(parents=True)
    referencia.write_text("{}\n", encoding="utf-8")
    transicionar(rodada, pdf_id, "referencia_congelada", artefatos=[referencia], agora=AGORA)
    with pytest.raises(TransicaoInvalidaError, match="renderizado"):
        transicionar(rodada, pdf_id, "renderizado", agora=AGORA)


@pytest.mark.usefixtures("corpus")
def test_referencia_reutilizada_pode_ser_renderizada_uma_vez(tmp_path: Path) -> None:
    anterior = _iniciar(tmp_path, "anterior")
    _congelar(anterior, _id_por_caminho(anterior, "b.pdf"))
    atual = _iniciar(tmp_path, "atual", anterior=anterior)
    pdf_id = _id_por_caminho(atual, "b.pdf")
    assert transicionar(atual, pdf_id, "renderizado", agora=AGORA)["fase"] == "renderizado"
    with pytest.raises(TransicaoInvalidaError):
        transicionar(atual, pdf_id, "renderizado", agora=AGORA)


@pytest.mark.parametrize(
    "caso", ["sem_artefato", "dois_artefatos", "fora_da_pasta_referencia", "nome_invalido"]
)
@pytest.mark.usefixtures("corpus")
def test_congelar_referencia_exige_um_arquivo_versionado(tmp_path: Path, caso: str) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    pasta = diretorio_pdf(rodada, pdf_id)
    transicionar(rodada, pdf_id, "renderizado", agora=AGORA)
    (pasta / "referencia").mkdir()
    validos = [
        pasta / "referencia" / "referencia-v001.json",
        pasta / "referencia" / "referencia-v002.json",
    ]
    for arquivo in [*validos, pasta / "referencia-v001.json", pasta / "referencia" / "ref.json"]:
        arquivo.write_text("{}\n", encoding="utf-8")
    artefatos = {
        "sem_artefato": [],
        "dois_artefatos": validos,
        "fora_da_pasta_referencia": [pasta / "referencia-v001.json"],
        "nome_invalido": [pasta / "referencia" / "ref.json"],
    }[caso]
    antes = (pasta / "checkpoint.json").read_bytes()
    with pytest.raises(TransicaoInvalidaError, match="referência"):
        transicionar(rodada, pdf_id, "referencia_congelada", artefatos=artefatos, agora=AGORA)
    assert (pasta / "checkpoint.json").read_bytes() == antes


@pytest.mark.usefixtures("corpus")
def test_artefato_ausente_ou_fora_da_rodada_e_recusado(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    arquivo = diretorio_pdf(rodada, pdf_id) / "checkpoint.json"
    antes = arquivo.read_bytes()
    externo = tmp_path / "externo.json"
    externo.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RodadaError, match="fora da rodada"):
        transicionar(rodada, pdf_id, "renderizado", artefatos=[externo], agora=AGORA)
    with pytest.raises(RodadaError, match="não existe"):
        transicionar(rodada, pdf_id, "renderizado", artefatos=[rodada / "nada.json"], agora=AGORA)
    assert arquivo.read_bytes() == antes


@pytest.mark.usefixtures("corpus")
def test_pdf_desconhecido_e_recusado(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    with pytest.raises(RodadaError, match="desconhecido"):
        diretorio_pdf(rodada, "999-000000000000")
    with pytest.raises(RodadaError, match="desconhecido"):
        diretorio_pdf(rodada, "../fora")
    assert main(["avancar", "--rodada", str(rodada), "--pdf", "x", "--fase", "inferido"]) != 0


def test_escrita_atomica_preserva_arquivo_quando_serializacao_falha(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    escrever_json_atomico(destino, {"versao": 1})
    antes = destino.read_bytes()
    with pytest.raises(ValueError):
        escrever_json_atomico(destino, {"invalido": float("nan")})
    assert destino.read_bytes() == antes
    assert sorted(item.name for item in tmp_path.iterdir()) == ["dados.json"]
    assert json.loads(antes) == {"versao": 1}


def test_escrita_atomica_usa_os_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[tuple[str, str]] = []
    original = os.replace

    def espiao(origem: str | os.PathLike[str], destino: str | os.PathLike[str]) -> None:
        chamadas.append((Path(origem).name, Path(destino).name))
        original(origem, destino)

    monkeypatch.setattr("scripts.curation_round.os.replace", espiao)
    escrever_json_atomico(tmp_path / "x.json", {"a": 1})
    assert len(chamadas) == 1
    assert chamadas[0][1] == "x.json"
    assert chamadas[0][0] != "x.json"


@pytest.mark.usefixtures("corpus")
def test_transicoes_concorrentes_no_mesmo_pdf_nao_perdem_eventos(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    erros: list[BaseException] = []

    def avancar(fase: str) -> None:
        try:
            for _ in range(5):
                transicionar(rodada, pdf_id, fase, agora=AGORA)
        except BaseException as erro:  # pragma: no cover - falha relatada abaixo
            erros.append(erro)

    tarefas = [
        threading.Thread(target=avancar, args=(fase,)) for fase in ("inferido", "renderizado")
    ]
    for tarefa in tarefas:
        tarefa.start()
    for tarefa in tarefas:
        tarefa.join()

    assert erros == []
    historico = carregar_checkpoint(rodada, pdf_id)["historico"]
    assert len(historico) == 11
    assert not list(diretorio_pdf(rodada, pdf_id).glob("*.lock"))


def test_checkpoint_codigo_indisponivel_fora_de_repositorio(tmp_path: Path) -> None:
    pacotes = tmp_path / "src/zeny_project_handler/adapters/analysis/symbol_packages"
    pacotes.mkdir(parents=True)
    (pacotes / "pacote.json").write_text("{}\n", encoding="utf-8")
    resultado = checkpoint_codigo(tmp_path, git_executavel="git-inexistente-zeny")
    assert resultado["git_write_tree"] == "indisponivel"
    assert resultado["motivo"]
    assert len(resultado["digest_pacotes"]) == 64


@pytest.mark.usefixtures("corpus")
def test_init_registra_checkpoint_indisponivel_sem_abortar(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path, raiz_repositorio=tmp_path / "nao-repositorio")
    codigo = carregar_rodada(rodada)["checkpoint_codigo"]
    assert codigo["git_write_tree"] == "indisponivel"
    assert codigo["digest_pacotes"] == "indisponivel"


@pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")
def test_checkpoint_codigo_em_repositorio_nao_altera_indice(tmp_path: Path) -> None:
    repositorio = tmp_path / "repo"
    pacotes = repositorio / "src/zeny_project_handler/adapters/analysis/symbol_packages"
    pacotes.mkdir(parents=True)
    (pacotes / "pacote.json").write_text('{"a": 1}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repositorio)], check=True)
    resultado = checkpoint_codigo(repositorio)
    assert len(resultado["git_write_tree"]) == 40
    status = subprocess.run(
        ["git", "-C", str(repositorio), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status.startswith("??")
    (pacotes / "pacote.json").write_text('{"a": 2}\n', encoding="utf-8")
    alterado = checkpoint_codigo(repositorio)
    assert alterado["git_write_tree"] != resultado["git_write_tree"]
    assert alterado["digest_pacotes"] != resultado["digest_pacotes"]


@pytest.mark.usefixtures("corpus")
def test_status_lista_fases_e_pendencias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _iniciar(tmp_path)
    ids = [item["pdf_id"] for item in carregar_rodada(rodada)["pdfs"]]
    transicionar(rodada, ids[0], "inferido", agora=AGORA)
    linhas = resumo_status(rodada)
    assert [linha["pdf_id"] for linha in linhas] == ids
    assert linhas[0]["fase"] == "inferido"
    assert linhas[0]["pendencias"] == [
        "renderizado",
        "referencia_congelada",
        "comparado",
        "auditado",
    ]
    assert [linha["pdf_id"] for linha in resumo_status(rodada, onda=2)] == [ids[3]]
    with pytest.raises(RodadaError, match="onda"):
        resumo_status(rodada, onda=3)

    assert main(["status", "--rodada", str(rodada), "--onda", "1"]) == 0
    saida = capsys.readouterr().out
    assert ids[0] in saida and "inferido" in saida and ids[3] not in saida
    assert main(["status", "--rodada", str(rodada), "--json"]) == 0
    dados = json.loads(capsys.readouterr().out)
    assert dados["por_fase"]["preparado"] == 3
    assert dados["por_fase"]["inferido"] == 1


@pytest.mark.usefixtures("corpus")
def test_selecionar_pdfs_por_onda_ou_id(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    ids = [item["pdf_id"] for item in carregar_rodada(rodada)["pdfs"]]
    assert selecionar_pdfs(rodada, onda=1) == ids[:3]
    assert selecionar_pdfs(rodada, pdf_ids=[ids[3], ids[0]]) == [ids[3], ids[0]]
    with pytest.raises(RodadaError):
        selecionar_pdfs(rodada)
    with pytest.raises(RodadaError):
        selecionar_pdfs(rodada, onda=1, pdf_ids=[ids[0]])
    with pytest.raises(RodadaError, match="desconhecido"):
        selecionar_pdfs(rodada, pdf_ids=["nao-existe"])


@pytest.mark.usefixtures("corpus")
def test_cli_avancar_grava_artefato_e_nota(tmp_path: Path) -> None:
    rodada = _iniciar(tmp_path)
    pdf_id = carregar_rodada(rodada)["pdfs"][0]["pdf_id"]
    indice = diretorio_pdf(rodada, pdf_id) / "render" / "indice-tiles.json"
    indice.parent.mkdir()
    indice.write_text("{}\n", encoding="utf-8")
    codigo = main(
        [
            "avancar",
            "--rodada",
            str(rodada),
            "--pdf",
            pdf_id,
            "--fase",
            "renderizado",
            "--artefato",
            str(indice),
            "--nota",
            "dpi 200",
        ]
    )
    assert codigo == 0
    evento = carregar_checkpoint(rodada, pdf_id)["historico"][-1]
    assert evento["para"] == "renderizado"
    assert evento["nota"] == "dpi 200"
    assert evento["artefatos"][0]["caminho"] == f"pdfs/{pdf_id}/render/indice-tiles.json"
    assert evento["horario"].endswith("+00:00")
