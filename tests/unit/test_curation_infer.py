from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_infer import (
    JOBS_MAXIMO,
    METODOS,
    ResultadoComando,
    comandos_inferencia,
    executar_subprocesso,
    inferir,
    main,
    reservar_versao,
)
from scripts.curation_round import (
    RodadaError,
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    hash_diretorio,
    iniciar_rodada,
    transicionar,
)
from tests.pdf_fixtures import create_catalog_pdf, create_feature_pdf

AGORA = "2026-10-15T12:00:00+00:00"
Registro = dict[str, Any]


def _corpus(raiz: Path) -> Path:
    (raiz / "sub").mkdir(parents=True)
    create_catalog_pdf(raiz / "b.pdf", "CODIGO-B")
    create_feature_pdf(raiz / "A.PDF")
    create_catalog_pdf(raiz / "sub" / "c.pdf", "CODIGO-C")
    return raiz


def _rodada(tmp_path: Path, concorrencia: int = 3) -> Path:
    rodada = tmp_path / "rodada"
    iniciar_rodada(
        rodada,
        _corpus(tmp_path / "corpus"),
        concorrencia=concorrencia,
        raiz_repositorio=tmp_path / "sem-git",
        agora=AGORA,
    )
    return rodada


def _ids(rodada: Path) -> list[str]:
    return [str(item["pdf_id"]) for item in carregar_rodada(rodada)["pdfs"]]


def _id_por_caminho(rodada: Path, caminho: str) -> str:
    for item in carregar_rodada(rodada)["pdfs"]:
        if item["caminho_relativo"] == caminho:
            return str(item["pdf_id"])
    raise AssertionError(caminho)


def _valor(comando: Sequence[str], opcao: str) -> str:
    return comando[list(comando).index(opcao) + 1]


class ExecutorFalso:
    """Simula os CLIs de inferência sem detectores, medindo a concorrência."""

    def __init__(
        self,
        *,
        espera_s: float = 0.1,
        codigo: Callable[[Sequence[str]], int] = lambda _: 0,
        escrever: Callable[[Sequence[str]], bool] = lambda _: True,
        sha_errado: bool = False,
        falhas: Sequence[Registro] = (),
        execucoes: Sequence[Registro] | None = None,
    ) -> None:
        self.espera_s = espera_s
        self.codigo = codigo
        self.escrever = escrever
        self.sha_errado = sha_errado
        self.falhas = [dict(item) for item in falhas]
        self.execucoes = None if execucoes is None else [dict(item) for item in execucoes]
        self.ativos = 0
        self.maximo = 0
        self.chamadas: list[list[str]] = []
        self._trava = threading.Lock()

    def __call__(self, comando: Sequence[str], *, cwd: Path, log: Path) -> ResultadoComando:
        with self._trava:
            self.ativos += 1
            self.maximo = max(self.maximo, self.ativos)
            self.chamadas.append(list(comando))
        try:
            time.sleep(self.espera_s)
            log.write_text("saida simulada\n", encoding="utf-8")
            if self.escrever(comando):
                self._gravar_saidas(comando)
            return ResultadoComando(codigo_saida=self.codigo(comando))
        finally:
            with self._trava:
                self.ativos -= 1

    def _gravar_saidas(self, comando: Sequence[str]) -> None:
        saida = Path(_valor(comando, "--output"))
        if "scripts.benchmark_network_pdf" in comando:
            saida.write_text("{}\n", encoding="utf-8")
            return
        raiz = Path(_valor(comando, "--root"))
        pdf = Path(_valor(comando, "--pdf"))
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if self.sha_errado:
            sha = "0" * 64
        documento = {"id": "example:" + pdf.relative_to(raiz).as_posix(), "sha256": sha}
        saida.mkdir(parents=True)
        predicoes: Registro = {"documents": [documento]}
        if self.execucoes is not None:
            predicoes["executions"] = [
                {"document_id": documento["id"], **item} for item in self.execucoes
            ]
        (saida / "predictions.json").write_text(json.dumps(predicoes), encoding="utf-8")
        manifesto: Registro = {
            "documents": [
                {
                    "failures": self.falhas,
                    "id": documento["id"],
                    "memory": {"python_peak_bytes": 4321},
                }
            ]
        }
        (saida / "manifest.json").write_text(json.dumps(manifesto), encoding="utf-8")


def _falha_para(nome: str) -> Callable[[Sequence[str]], int]:
    return lambda comando: 1 if any(item.endswith(nome) for item in comando) else 0


def _execucao(rodada: Path, pdf_id: str, versao: str = "inferencia-v001") -> Registro:
    arquivo = diretorio_pdf(rodada, pdf_id) / versao / "execucao.json"
    dados: Registro = json.loads(arquivo.read_text(encoding="utf-8"))
    return dados


def test_jobs_limita_concorrencia_e_falha_isolada(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    ids = _ids(rodada)
    executor = ExecutorFalso(codigo=_falha_para("b.pdf"))
    resultado = inferir(
        rodada, ids, jobs=2, executor=executor, raiz_repositorio=tmp_path / "sem-git"
    )
    assert executor.maximo == 2
    assert len(executor.chamadas) == 3
    por_id = {item["pdf_id"]: item for item in resultado["pdfs"]}
    falho = _id_por_caminho(rodada, "b.pdf")
    assert por_id[falho]["status"] == "falha"
    assert carregar_checkpoint(rodada, falho)["fase"] == "preparado"
    execucao = _execucao(rodada, falho)
    assert execucao["status"] == "falha"
    assert execucao["etapas"][0]["codigo_saida"] == 1
    assert any("código 1" in falha for falha in execucao["falhas"])
    for pdf_id in ids:
        if pdf_id == falho:
            continue
        assert por_id[pdf_id]["status"] == "sucesso"
        checkpoint = carregar_checkpoint(rodada, pdf_id)
        assert checkpoint["fase"] == "inferido"
        artefato = checkpoint["marcos"]["inferido"]["artefatos"][0]
        assert artefato["caminho"] == f"pdfs/{pdf_id}/inferencia-v001"
        assert artefato["tipo"] == "diretorio"
    assert resultado["totais"] == {"falha": 1, "recusado": 0, "sucesso": 2, "sucesso_parcial": 0}


def test_jobs_um_executa_em_serie(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    executor = ExecutorFalso(espera_s=0.02)
    inferir(rodada, _ids(rodada), jobs=1, executor=executor, raiz_repositorio=tmp_path / "sem-git")
    assert executor.maximo == 1


def test_pipeline_conta_como_o_mesmo_processo_do_pdf(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    executor = ExecutorFalso(espera_s=0.05)
    resultado = inferir(
        rodada,
        _ids(rodada),
        jobs=2,
        pipeline=True,
        executor=executor,
        raiz_repositorio=tmp_path / "sem-git",
    )
    assert executor.maximo <= 2
    assert len(executor.chamadas) == 6
    assert resultado["totais"]["sucesso"] == 3


def test_segunda_execucao_cria_v002_sem_tocar_v001(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    executor = ExecutorFalso(espera_s=0)
    inferir(rodada, [pdf_id], executor=executor, raiz_repositorio=tmp_path / "sem-git")
    v001 = diretorio_pdf(rodada, pdf_id) / "inferencia-v001"
    antes = hash_diretorio(v001)
    bytes_antes = (v001 / "execucao.json").read_bytes()
    resultado = inferir(rodada, [pdf_id], executor=executor, raiz_repositorio=tmp_path / "sem-git")
    assert resultado["pdfs"][0]["versao"] == "inferencia-v002"
    assert hash_diretorio(v001) == antes
    assert (v001 / "execucao.json").read_bytes() == bytes_antes
    assert _execucao(rodada, pdf_id, "inferencia-v002")["versao"] == "inferencia-v002"
    checkpoint = carregar_checkpoint(rodada, pdf_id)
    assert checkpoint["marcos"]["inferido"]["artefatos"][0]["caminho"].endswith("v002")
    assert [evento["para"] for evento in checkpoint["historico"]].count("inferido") == 2


def test_versao_com_falha_tambem_nao_e_reutilizada(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    inferir(
        rodada,
        [pdf_id],
        executor=ExecutorFalso(espera_s=0, codigo=lambda _: 2),
        raiz_repositorio=tmp_path / "sem-git",
    )
    resultado = inferir(
        rodada, [pdf_id], executor=ExecutorFalso(espera_s=0), raiz_repositorio=tmp_path / "sem-git"
    )
    assert resultado["pdfs"][0]["versao"] == "inferencia-v002"
    assert _execucao(rodada, pdf_id)["status"] == "falha"
    assert _execucao(rodada, pdf_id, "inferencia-v002")["status"] == "sucesso"


def test_reservar_versao_pula_existentes_e_nunca_reusa(tmp_path: Path) -> None:
    pasta = tmp_path / "pdf"
    pasta.mkdir()
    (pasta / "inferencia-v001").mkdir()
    (pasta / "inferencia-v003").write_text("arquivo ocupa o nome", encoding="utf-8")
    (pasta / "inferencia-vxyz").mkdir()
    assert reservar_versao(pasta).name == "inferencia-v004"
    assert reservar_versao(pasta).name == "inferencia-v005"
    assert (pasta / "inferencia-v003").is_file()


def test_reserva_concorrente_gera_versoes_distintas(tmp_path: Path) -> None:
    pasta = tmp_path / "pdf"
    pasta.mkdir()
    nomes: list[str] = []
    trava = threading.Lock()

    def reservar() -> None:
        nome = reservar_versao(pasta).name
        with trava:
            nomes.append(nome)

    threads = [threading.Thread(target=reservar) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(nomes) == [f"inferencia-v{n:03d}" for n in range(1, 9)]


def test_execucao_registra_checkpoint_comando_duracao_e_memoria(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    codigo = {"caminho_pacotes": "x", "digest_pacotes": "d", "git_write_tree": "t"}
    inferir(
        rodada,
        [pdf_id],
        jobs=1,
        executor=ExecutorFalso(espera_s=0),
        raiz_repositorio=tmp_path / "sem-git",
        codigo=codigo,
        agora=lambda: AGORA,
    )
    execucao = _execucao(rodada, pdf_id)
    assert execucao["schema_version"] == "curadoria-inferencia-v1"
    assert execucao["checkpoint_codigo"] == codigo
    assert execucao["status"] == "sucesso"
    assert execucao["falhas"] == []
    assert execucao["falhas_metodos"] == []
    assert execucao["iniciado_em"] == AGORA
    assert execucao["concluido_em"] == AGORA
    assert execucao["duracao_s"] >= 0
    assert execucao["jobs"] == 1
    assert execucao["metodos"] == list(METODOS)
    entrada = carregar_rodada(rodada)["pdfs"][0]
    assert execucao["sha256"] == entrada["sha256"]
    assert execucao["document_id"] == "example:" + entrada["caminho_relativo"]
    etapa = execucao["etapas"][0]
    assert etapa["nome"] == "simbolos"
    assert etapa["codigo_saida"] == 0
    assert etapa["duracao_s"] >= 0
    assert etapa["memoria_python_pico_bytes"] == 4321
    assert "tracemalloc" in etapa["escopo_memoria"]
    assert etapa["log"] == "simbolos.log"
    texto = json.dumps(execucao)
    assert str(tmp_path) not in texto
    assert str(tmp_path).replace("\\", "/") not in texto
    assert sys.executable not in texto
    assert etapa["comando"][:4] == ["python", "-m", "scripts.benchmark_symbols", "examples"]
    assert _valor(etapa["comando"], "--root") == "../corpus"
    assert _valor(etapa["comando"], "--pdf") == "../corpus/" + entrada["caminho_relativo"]
    assert _valor(etapa["comando"], "--output") == (f"pdfs/{pdf_id}/inferencia-v001/simbolos")
    checkpoint = carregar_checkpoint(rodada, pdf_id)
    evento = checkpoint["historico"][-1]
    assert evento["dados"]["versao"] == "inferencia-v001"
    assert evento["dados"]["execucao"] == f"pdfs/{pdf_id}/inferencia-v001/execucao.json"
    assert "falhas_metodos" not in evento["dados"]


def test_comandos_padrao_usam_pdf_unico_e_todos_os_metodos(tmp_path: Path) -> None:
    raiz = tmp_path / "corpus"
    fonte = raiz / "sub" / "a.pdf"
    versao = tmp_path / "rodada" / "pdfs" / "001-x" / "inferencia-v001"
    etapas = comandos_inferencia(
        raiz, fonte, versao, metodos=METODOS, pipeline=True, native_only=True
    )
    assert [nome for nome, _ in etapas] == ["simbolos", "pipeline"]
    simbolos = etapas[0][1]
    assert simbolos[:4] == [sys.executable, "-m", "scripts.benchmark_symbols", "examples"]
    assert _valor(simbolos, "--root") == str(raiz)
    assert _valor(simbolos, "--pdf") == str(fonte)
    assert _valor(simbolos, "--output") == str(versao / "simbolos")
    for metodo in METODOS:
        assert f"--include-{metodo}" in simbolos
    assert "--legend-ocr" not in simbolos
    pipeline = etapas[1][1]
    assert pipeline[:3] == [sys.executable, "-m", "scripts.benchmark_network_pdf"]
    assert pipeline[3] == str(fonte)
    assert _valor(pipeline, "--output") == str(versao / "pipeline.json")
    assert "--native-only" in pipeline
    assert "--complementary-ocr" not in pipeline
    sem_metodos = comandos_inferencia(
        raiz, fonte, versao, metodos=(), pipeline=False, native_only=False
    )
    assert len(sem_metodos) == 1
    assert not [item for item in sem_metodos[0][1] if item.startswith("--include-")]


def test_excecao_do_executor_fica_isolada_no_pdf(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    ids = _ids(rodada)
    alvo = Path(carregar_rodada(rodada)["pdfs"][1]["caminho_relativo"]).name
    base = ExecutorFalso(espera_s=0.01)

    def executor(comando: Sequence[str], *, cwd: Path, log: Path) -> ResultadoComando:
        if _valor(comando, "--pdf").endswith(alvo):
            raise OSError("falha simulada ao iniciar o processo")
        return base(comando, cwd=cwd, log=log)

    resultado = inferir(
        rodada, ids, jobs=3, executor=executor, raiz_repositorio=tmp_path / "sem-git"
    )
    estados = [item["status"] for item in resultado["pdfs"]]
    assert estados == ["sucesso", "falha", "sucesso"]
    assert [item["pdf_id"] for item in resultado["pdfs"]] == ids
    execucao = _execucao(rodada, ids[1])
    assert any("OSError" in falha for falha in execucao["falhas"])
    assert carregar_checkpoint(rodada, ids[1])["fase"] == "preparado"
    assert carregar_checkpoint(rodada, ids[2])["fase"] == "inferido"


@pytest.mark.parametrize("caso", ["sem-saida", "sha-errado", "pipeline-sem-saida"])
def test_saida_ausente_ou_inconsistente_e_falha(tmp_path: Path, caso: str) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    executor = ExecutorFalso(
        espera_s=0,
        escrever=(
            (lambda c: "scripts.benchmark_network_pdf" not in c)
            if caso == "pipeline-sem-saida"
            else (lambda _: caso != "sem-saida")
        ),
        sha_errado=caso == "sha-errado",
    )
    resultado = inferir(
        rodada,
        [pdf_id],
        pipeline=caso == "pipeline-sem-saida",
        executor=executor,
        raiz_repositorio=tmp_path / "sem-git",
    )
    assert resultado["pdfs"][0]["status"] == "falha"
    assert carregar_checkpoint(rodada, pdf_id)["fase"] == "preparado"
    falhas = " ".join(_execucao(rodada, pdf_id)["falhas"])
    esperado = {
        "sem-saida": "predictions.json",
        "sha-errado": "SHA-256",
        "pipeline-sem-saida": "pipeline.json",
    }[caso]
    assert esperado in falhas


FALHA_RASTER = {
    "method_id": "structural-raster-graph",
    "page": 1,
    "reason": "Limite de traços raster alcançado",
}
EXECUTADO = {"layer": "base", "method_id": "legacy-vector-symbols", "page": 1, "status": "executed"}
FALHOU = {"layer": "base", "method_id": "structural-raster-graph", "page": 1, "status": "failed"}


def _simbolos_com_codigo_1(comando: Sequence[str]) -> int:
    return 1 if "scripts.benchmark_symbols" in comando else 0


def test_falha_de_um_metodo_com_predicoes_validas_e_sucesso_parcial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    executor = ExecutorFalso(
        espera_s=0,
        codigo=_simbolos_com_codigo_1,
        falhas=[FALHA_RASTER],
        execucoes=[EXECUTADO, FALHOU],
    )
    argumentos = ["--rodada", str(rodada), "--pdf", pdf_id, "--pipeline", "--native-only"]
    assert main(argumentos, executor=executor, raiz_repositorio=tmp_path / "sem-git") == 0
    assert len(executor.chamadas) == 2  # o pipeline roda depois do runner parcial
    esperado = [
        {
            "method_id": "structural-raster-graph",
            "motivo": "Limite de traços raster alcançado",
            "pagina": 1,
        }
    ]
    saida = json.loads(capsys.readouterr().out)
    assert saida["totais"] == {"falha": 0, "recusado": 0, "sucesso": 0, "sucesso_parcial": 1}
    resumo = saida["pdfs"][0]
    assert resumo["status"] == "sucesso_parcial"
    assert resumo["falhas"] == []
    assert resumo["falhas_metodos"] == esperado
    execucao = _execucao(rodada, pdf_id)
    assert execucao["status"] == "sucesso_parcial"
    assert execucao["falhas"] == []
    assert execucao["falhas_metodos"] == esperado
    assert execucao["etapas"][0]["codigo_saida"] == 1
    assert execucao["etapas"][0]["memoria_python_pico_bytes"] == 4321
    checkpoint = carregar_checkpoint(rodada, pdf_id)
    assert checkpoint["fase"] == "inferido"
    evento = checkpoint["historico"][-1]
    assert evento["dados"]["falhas_metodos"] == esperado
    assert evento["dados"]["status"] == "sucesso_parcial"


@pytest.mark.parametrize(
    ("caso", "falhas", "execucoes", "trecho"),
    [
        ("sem-predicoes", [FALHA_RASTER], [EXECUTADO, FALHOU], "predictions.json"),
        ("sem-method-id", [{"page": 1, "reason": "PDF ilegível"}], [EXECUTADO], "método"),
        ("sem-falhas-registradas", [], [EXECUTADO], "código 1"),
        ("nenhum-metodo-executado", [FALHA_RASTER], [FALHOU], "nenhum método"),
        ("falha-ausente-das-predicoes", [FALHA_RASTER], [EXECUTADO], "executions"),
        ("pipeline-falhou", [FALHA_RASTER], [EXECUTADO, FALHOU], "pipeline"),
    ],
)
def test_codigo_nao_zero_sem_falha_so_de_metodo_e_falha_do_pdf(
    tmp_path: Path,
    caso: str,
    falhas: list[Registro],
    execucoes: list[Registro],
    trecho: str,
) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    executor = ExecutorFalso(
        espera_s=0,
        codigo=(lambda _: 1) if caso == "pipeline-falhou" else _simbolos_com_codigo_1,
        escrever=lambda c: caso != "sem-predicoes" or "scripts.benchmark_symbols" not in c,
        falhas=falhas,
        execucoes=execucoes,
    )
    resultado = inferir(
        rodada,
        [pdf_id],
        pipeline=True,
        native_only=True,
        executor=executor,
        raiz_repositorio=tmp_path / "sem-git",
    )
    assert resultado["pdfs"][0]["status"] == "falha"
    assert resultado["totais"]["falha"] == 1
    assert carregar_checkpoint(rodada, pdf_id)["fase"] == "preparado"
    execucao = _execucao(rodada, pdf_id)
    assert execucao["status"] == "falha"
    assert trecho in " ".join(execucao["falhas"])


def test_pdf_alterado_desde_init_falha_sem_executar(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    caminho = tmp_path / "corpus" / carregar_rodada(rodada)["pdfs"][0]["caminho_relativo"]
    create_catalog_pdf(caminho, "OUTRO-CODIGO")
    executor = ExecutorFalso(espera_s=0)
    resultado = inferir(rodada, [pdf_id], executor=executor, raiz_repositorio=tmp_path / "sem-git")
    assert executor.chamadas == []
    assert resultado["pdfs"][0]["status"] == "falha"
    assert "SHA-256" in " ".join(_execucao(rodada, pdf_id)["falhas"])


def test_fase_terminal_recusa_sem_criar_versao(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    pdf_id = _ids(rodada)[0]
    transicionar(rodada, pdf_id, "encerrado_com_pendencias", nota="fora do escopo", agora=AGORA)
    executor = ExecutorFalso(espera_s=0)
    resultado = inferir(rodada, [pdf_id], executor=executor, raiz_repositorio=tmp_path / "sem-git")
    assert resultado["pdfs"][0]["status"] == "recusado"
    assert resultado["pdfs"][0]["versao"] is None
    assert "terminal" in resultado["pdfs"][0]["falhas"][0]
    assert executor.chamadas == []
    assert not list(diretorio_pdf(rodada, pdf_id).glob("inferencia-v*"))


@pytest.mark.parametrize("jobs", [0, JOBS_MAXIMO + 1])
def test_jobs_fora_do_intervalo_e_recusado(tmp_path: Path, jobs: int) -> None:
    rodada = _rodada(tmp_path)
    with pytest.raises(RodadaError, match="--jobs"):
        inferir(rodada, _ids(rodada), jobs=jobs, executor=ExecutorFalso())


def test_native_only_exige_pipeline(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path)
    with pytest.raises(RodadaError, match="--pipeline"):
        inferir(rodada, _ids(rodada), native_only=True, executor=ExecutorFalso())


def test_cli_infere_onda_e_retorna_codigo_por_resultado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _rodada(tmp_path, concorrencia=2)
    executor = ExecutorFalso(espera_s=0)
    argumentos = ["--rodada", str(rodada), "--onda", "1", "--jobs", "2", "--metodos", "guys"]
    assert main(argumentos, executor=executor, raiz_repositorio=tmp_path / "sem-git") == 0
    saida = json.loads(capsys.readouterr().out)
    onda = carregar_rodada(rodada)["ondas"][0]["pdfs"]
    assert [item["pdf_id"] for item in saida["pdfs"]] == onda
    assert len(executor.chamadas) == 2
    comando = executor.chamadas[0]
    assert "--include-guys" in comando
    assert "--include-packages" not in comando
    falhando = ExecutorFalso(espera_s=0, codigo=lambda _: 1)
    terceiro = carregar_rodada(rodada)["ondas"][1]["pdfs"][0]
    argumentos = ["--rodada", str(rodada), "--pdf", terceiro, "--jobs", "1"]
    assert main(argumentos, executor=falhando, raiz_repositorio=tmp_path / "sem-git") == 1


def test_cli_recusa_selecao_e_jobs_invalidos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _rodada(tmp_path)
    executor = ExecutorFalso()
    assert main(["--rodada", str(rodada), "--onda", "9"], executor=executor) == 1
    assert "onda inexistente" in capsys.readouterr().err
    assert main(["--rodada", str(rodada), "--onda", "1", "--jobs", "6"], executor=executor) == 1
    assert "--jobs" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["--rodada", str(rodada), "--onda", "1", "--pdf", "x"], executor=executor)
    assert executor.chamadas == []


def test_executor_padrao_roda_subprocesso_e_grava_log(tmp_path: Path) -> None:
    log = tmp_path / "etapa.log"
    comando = [sys.executable, "-c", "import sys; print('ok'); sys.exit(3)"]
    resultado = executar_subprocesso(comando, cwd=tmp_path, log=log)
    assert resultado.codigo_saida == 3
    assert "ok" in log.read_text(encoding="utf-8")
