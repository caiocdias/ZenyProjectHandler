"""Casos de uso para fotos, pacote portátil, backup e recuperação."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4, uuid5

from zeny_project_handler.application.errors import (
    PortabilidadeProjetoError,
    ProjetoNaoEncontradoError,
)
from zeny_project_handler.domain.portability import (
    ArquivoPacoteProjeto,
    ManifestoProjetoPortatil,
    ProblemaIntegridadeProjeto,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.domain.project import ElementoProjetoType, FotoElemento, Projeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort
from zeny_project_handler.ports.portability import (
    ArquivoProjetoPortatilPort,
    BackupLocalPort,
    BancoProjetoPortatilPort,
    ConteudoBancoProjetoPortatil,
    OrigemArquivoPacote,
)

ProgressCallback = Callable[[int, int, str], None]
_BACKUP_ID = UUID(int=0)
_SUPPORTED_PHOTO_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoProjetoPortabilidade:
    projeto_id: UUID
    nome: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoElementoFotos:
    elemento_id: UUID
    rotulo: str
    fotos: tuple[FotoElemento, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoPdfProjeto:
    documento_id: UUID
    nome: str
    disponivel: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoFotoProjeto:
    projeto: Projeto
    foto: FotoElemento | None
    deduplicada: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoExportacaoProjeto:
    caminho: Path
    manifesto: ManifestoProjetoPortatil
    integridade_origem: RelatorioIntegridadeProjeto


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoImportacaoProjeto:
    projeto: Projeto
    integridade_pacote: RelatorioIntegridadeProjeto
    substituiu_existente: bool


class ServicoPortabilidadeProjeto:
    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        arquivo_portatil: ArquivoProjetoPortatilPort,
        banco_portatil: BancoProjetoPortatilPort,
        backup_local: BackupLocalPort,
        *,
        diretorio_dados: Path,
        caminho_banco: Path,
        descartar_conexoes: Callable[[], None] | None = None,
        relogio: Callable[[], datetime] | None = None,
        gerar_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._archive = arquivo_portatil
        self._portable_database = banco_portatil
        self._backup = backup_local
        self._data_directory = diretorio_dados.expanduser().resolve()
        self._database_path = caminho_banco.expanduser().resolve()
        self._managed_root = self._data_directory / "project-files"
        self._dispose_connections = descartar_conexoes or (lambda: None)
        self._clock = relogio or (lambda: datetime.now(UTC))
        self._new_id = gerar_id

    def listar_projetos(self) -> tuple[ResumoProjetoPortabilidade, ...]:
        with self._unit_of_work() as work:
            return tuple(
                ResumoProjetoPortabilidade(
                    projeto_id=project.id,
                    nome=project.nome,
                )
                for project in work.projetos.listar()
            )

    def listar_elementos(self, projeto_id: UUID) -> tuple[ResumoElementoFotos, ...]:
        project = self._project(projeto_id)
        return tuple(
            ResumoElementoFotos(
                elemento_id=item.id,
                rotulo=(
                    item.referencia_desenho
                    or item.identificador_operacional
                    or item.codigo_observado
                    or f"{item.categoria.value} {str(item.id)[:8]}"
                ),
                fotos=item.fotos,
            )
            for item in project.elementos
        )

    def listar_pdfs(self, projeto_id: UUID) -> tuple[ResumoPdfProjeto, ...]:
        project = self._project(projeto_id)
        with self._unit_of_work() as work:
            sources = {
                document.id: work.fontes_pdf.obter(document.id) for document in project.documentos
            }
        return tuple(
            ResumoPdfProjeto(
                documento_id=document.id,
                nome=document.nome_arquivo,
                disponivel=_pdf_source_available(sources[document.id]),
            )
            for document in project.documentos
        )

    def localizar_pdf(
        self, projeto_id: UUID, documento_id: UUID, origem: Path
    ) -> ReferenciaFontePdf:
        project = self._project(projeto_id)
        document = next((item for item in project.documentos if item.id == documento_id), None)
        if document is None:
            raise PortabilidadeProjetoError("PDF não pertence ao projeto")
        source = origem.expanduser().resolve()
        if not source.is_file():
            raise PortabilidadeProjetoError("Arquivo PDF localizado não existe")
        digest, size = _file_digest(source)
        with source.open("rb") as stream:
            is_pdf = stream.read(5).startswith(b"%PDF-")
        if not is_pdf:
            raise PortabilidadeProjetoError("Arquivo localizado não é um PDF válido")
        if digest != document.sha256:
            raise PortabilidadeProjetoError("PDF localizado não corresponde ao hash importado")
        stat_result = source.stat()
        reference = ReferenciaFontePdf(
            documento_id=document.id,
            projeto_id=project.id,
            caminho_canonico=source,
            sha256=digest,
            tamanho_bytes=size,
            modificado_em_ns=stat_result.st_mtime_ns,
        )
        with self._unit_of_work() as work:
            work.fontes_pdf.salvar(reference)
            work.commit()
        return reference

    def anexar_foto(
        self,
        projeto_id: UUID,
        elemento_id: UUID,
        origem: Path,
        *,
        legenda: str | None = None,
    ) -> ResultadoFotoProjeto:
        source = origem.expanduser().resolve()
        digest, size, mime_type = _inspect_photo(source)
        relative = f"photos/{digest}{_SUPPORTED_PHOTO_MIME[mime_type]}"
        project = self._project(projeto_id)
        element = _element(project, elemento_id)
        existing = next((item for item in element.fotos if item.sha256 == digest), None)
        if existing is not None:
            return ResultadoFotoProjeto(projeto=project, foto=existing, deduplicada=True)
        destination = self._managed_path(projeto_id, relative)
        created = not destination.exists()
        if created:
            _copy_atomic(source, destination)
        photo = FotoElemento(
            id=uuid5(element.id, f"foto:{digest}"),
            caminho_relativo=relative,
            legenda=legenda,
            sha256=digest,
            tipo_mime=mime_type,
            tamanho_bytes=size,
        )
        updated_element = replace(element, fotos=(*element.fotos, photo))
        updated = _replace_element(project, updated_element)
        try:
            self._save_project(updated)
        except Exception:
            if created:
                with suppress(OSError):
                    destination.unlink(missing_ok=True)
            raise
        return ResultadoFotoProjeto(projeto=updated, foto=photo)

    def remover_foto(
        self, projeto_id: UUID, elemento_id: UUID, foto_id: UUID
    ) -> ResultadoFotoProjeto:
        project = self._project(projeto_id)
        element = _element(project, elemento_id)
        photo = next((item for item in element.fotos if item.id == foto_id), None)
        if photo is None:
            raise PortabilidadeProjetoError("Foto não pertence ao elemento selecionado")
        updated_element = replace(
            element, fotos=tuple(item for item in element.fotos if item.id != foto_id)
        )
        updated = _replace_element(project, updated_element)
        self._save_project(updated)
        if not any(
            item.caminho_relativo == photo.caminho_relativo
            for other in updated.elementos
            for item in other.fotos
        ):
            with suppress(OSError):
                self._managed_path(projeto_id, photo.caminho_relativo).unlink(missing_ok=True)
        return ResultadoFotoProjeto(projeto=updated, foto=photo)

    def localizar_foto(
        self,
        projeto_id: UUID,
        elemento_id: UUID,
        foto_id: UUID,
        origem: Path,
    ) -> ResultadoFotoProjeto:
        project = self._project(projeto_id)
        element = _element(project, elemento_id)
        photo = next((item for item in element.fotos if item.id == foto_id), None)
        if photo is None:
            raise PortabilidadeProjetoError("Foto não pertence ao elemento selecionado")
        source = origem.expanduser().resolve()
        digest, size, mime_type = _inspect_photo(source)
        if photo.sha256 is not None and digest != photo.sha256:
            raise PortabilidadeProjetoError("Arquivo localizado não corresponde ao hash da foto")
        relative = f"photos/{digest}{_SUPPORTED_PHOTO_MIME[mime_type]}"
        _copy_atomic(source, self._managed_path(projeto_id, relative))
        repaired = replace(
            photo,
            caminho_relativo=relative,
            sha256=digest,
            tipo_mime=mime_type,
            tamanho_bytes=size,
        )
        updated_element = replace(
            element,
            fotos=tuple(repaired if item.id == foto_id else item for item in element.fotos),
        )
        updated = _replace_element(project, updated_element)
        self._save_project(updated)
        return ResultadoFotoProjeto(projeto=updated, foto=repaired)

    def verificar_integridade(self, projeto_id: UUID) -> RelatorioIntegridadeProjeto:
        project = self._project(projeto_id)
        problems: list[ProblemaIntegridadeProjeto] = []
        with self._unit_of_work() as work:
            sources = {
                document.id: work.fontes_pdf.obter(document.id) for document in project.documentos
            }
        for document in project.documentos:
            source = sources[document.id]
            if source is None:
                problems.append(
                    _problem(
                        "ORIGEM_PDF_AUSENTE",
                        f"A origem de {document.nome_arquivo} precisa ser localizada "
                        "ou restaurada.",
                    )
                )
                continue
            problems.extend(_source_problems(source, document.nome_arquivo))
        checked_paths: set[str] = set()
        for element in project.elementos:
            for photo in element.fotos:
                if photo.caminho_relativo in checked_paths:
                    continue
                checked_paths.add(photo.caminho_relativo)
                problems.extend(self._photo_problems(project.id, photo))
        return RelatorioIntegridadeProjeto(problemas=tuple(problems))

    def exportar_projeto(
        self,
        projeto_id: UUID,
        destino: Path,
        *,
        progresso: ProgressCallback | None = None,
    ) -> ResultadoExportacaoProjeto:
        report = self.verificar_integridade(projeto_id)
        content, sources = self._portable_content(projeto_id)
        notify = progresso or (lambda _current, _total, _message: None)
        with TemporaryDirectory(prefix="zeny-export-") as temporary_name:
            temporary = Path(temporary_name)
            notify(1, 4, "Criando banco exclusivo do projeto")
            database = self._portable_database.criar(temporary / "project.sqlite3", content)
            origins = [
                _package_origin(database, "project.sqlite3", "BANCO", "application/vnd.sqlite3"),
            ]
            notify(2, 4, "Coletando PDFs íntegros")
            for document in content.projeto.documentos:
                source = sources.get(document.id)
                if source is not None and not _source_problems(source, document.nome_arquivo):
                    origins.append(
                        _package_origin(
                            source.caminho_canonico,
                            f"files/pdfs/{document.id}.pdf",
                            "PDF",
                            "application/pdf",
                            document.id,
                        )
                    )
            notify(3, 4, "Coletando fotos íntegras")
            seen_photos: set[str] = set()
            for element in content.projeto.elementos:
                for photo in element.fotos:
                    if photo.caminho_relativo in seen_photos or self._photo_problems(
                        projeto_id, photo
                    ):
                        continue
                    seen_photos.add(photo.caminho_relativo)
                    origins.append(
                        _package_origin(
                            self._managed_path(projeto_id, photo.caminho_relativo),
                            f"files/{photo.caminho_relativo}",
                            "FOTO",
                            photo.tipo_mime or "application/octet-stream",
                            photo.id,
                        )
                    )
            manifest = ManifestoProjetoPortatil(
                versao_formato=1,
                projeto_id=content.projeto.id,
                catalogo_id=content.catalogo.id,
                nome_projeto=content.projeto.nome,
                criado_em=self._aware_now(),
                arquivos=tuple(item.arquivo for item in origins),
            )
            notify(4, 4, "Publicando pacote de projeto")
            path = self._archive.criar(destino, manifest, tuple(origins))
        return ResultadoExportacaoProjeto(
            caminho=path,
            manifesto=manifest,
            integridade_origem=report,
        )

    def importar_projeto(
        self,
        pacote: Path,
        *,
        substituir_existente: bool = False,
        progresso: ProgressCallback | None = None,
    ) -> ResultadoImportacaoProjeto:
        notify = progresso or (lambda _current, _total, _message: None)
        with TemporaryDirectory(prefix="zeny-import-") as temporary_name:
            temporary = Path(temporary_name)
            notify(1, 4, "Validando manifesto e arquivos")
            extracted = self._archive.extrair_validado(pacote, temporary / "package")
            if not extracted.integridade.utilizavel:
                raise PortabilidadeProjetoError("Pacote possui problemas críticos de integridade")
            database_entry = next(
                (item for item in extracted.manifesto.arquivos if item.tipo == "BANCO"), None
            )
            if database_entry is None:
                raise PortabilidadeProjetoError("Pacote não possui banco de projeto")
            content = self._portable_database.carregar(
                extracted.diretorio / PurePosixPath(database_entry.caminho_relativo),
                extracted.manifesto.projeto_id,
            )
            if content.catalogo.id != extracted.manifesto.catalogo_id:
                raise PortabilidadeProjetoError("Catálogo do banco diverge do manifesto")
            notify(2, 4, "Preparando PDFs e fotos gerenciados")
            staging = self._stage_imported_files(extracted.diretorio, extracted.manifesto)
            final_root = self._project_root(content.projeto.id)
            recovery_root = final_root.with_name(f".{final_root.name}.{uuid4().hex}.previous")
            replaced_assets = final_root.exists()
            if replaced_assets:
                os.replace(final_root, recovery_root)
            final_root.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, final_root)
            try:
                notify(3, 4, "Persistindo projeto e histórico")
                replaced_project = self._persist_imported_content(
                    content,
                    extracted.manifesto,
                    substituir_existente=substituir_existente,
                )
            except Exception:
                shutil.rmtree(final_root, ignore_errors=True)
                if recovery_root.exists():
                    os.replace(recovery_root, final_root)
                raise
            shutil.rmtree(recovery_root, ignore_errors=True)
            notify(4, 4, "Conferindo projeto importado")
            imported = self._project(content.projeto.id)
        return ResultadoImportacaoProjeto(
            projeto=imported,
            integridade_pacote=extracted.integridade,
            substituiu_existente=replaced_project,
        )

    def criar_backup(self, destino: Path, *, progresso: ProgressCallback | None = None) -> Path:
        notify = progresso or (lambda _current, _total, _message: None)
        with TemporaryDirectory(prefix="zeny-backup-") as temporary_name:
            temporary = Path(temporary_name)
            notify(1, 3, "Criando snapshot consistente do banco")
            snapshot = self._backup.criar_snapshot(
                self._database_path, temporary / "database.sqlite3"
            )
            notify(2, 3, "Coletando arquivos gerenciados")
            managed_origins: dict[str, OrigemArquivoPacote] = {}
            if self._managed_root.is_dir():
                for path in sorted(
                    item for item in self._managed_root.rglob("*") if item.is_file()
                ):
                    relative = path.relative_to(self._managed_root).as_posix()
                    managed_origins[relative] = _package_origin(
                        path,
                        f"managed/{relative}",
                        "ARQUIVO_GERENCIADO",
                        _mime_for_path(path),
                    )
            restored_pdf_paths: dict[UUID, Path] = {}
            with self._unit_of_work() as work:
                for project in work.projetos.listar():
                    for document in project.documentos:
                        source = work.fontes_pdf.obter(document.id)
                        if source is None or _source_problems(source, document.nome_arquivo):
                            continue
                        relative = f"{project.id}/pdfs/{document.id}.pdf"
                        managed_origins[relative] = _package_origin(
                            source.caminho_canonico,
                            f"managed/{relative}",
                            "ARQUIVO_GERENCIADO",
                            "application/pdf",
                            document.id,
                        )
                        restored_pdf_paths[document.id] = self._managed_root / relative
            self._backup.preparar_origens_pdf(snapshot, restored_pdf_paths)
            origins = [
                _package_origin(snapshot, "database.sqlite3", "BANCO", "application/vnd.sqlite3"),
                *managed_origins.values(),
            ]
            manifest = ManifestoProjetoPortatil(
                versao_formato=1,
                projeto_id=_BACKUP_ID,
                catalogo_id=_BACKUP_ID,
                nome_projeto="Backup local completo",
                criado_em=self._aware_now(),
                arquivos=tuple(item.arquivo for item in origins),
            )
            notify(3, 3, "Publicando backup atômico")
            return self._archive.criar(destino, manifest, tuple(origins))

    def restaurar_backup(self, origem: Path, *, progresso: ProgressCallback | None = None) -> Path:
        notify = progresso or (lambda _current, _total, _message: None)
        with TemporaryDirectory(prefix="zeny-restore-") as temporary_name:
            temporary = Path(temporary_name)
            notify(1, 4, "Validando backup")
            extracted = self._archive.extrair_validado(origem, temporary / "backup")
            if extracted.manifesto.projeto_id != _BACKUP_ID:
                raise PortabilidadeProjetoError("Arquivo selecionado não é um backup completo")
            if not extracted.integridade.integro:
                raise PortabilidadeProjetoError("Backup possui problemas de integridade")
            database_entry = next(
                (item for item in extracted.manifesto.arquivos if item.tipo == "BANCO"), None
            )
            if database_entry is None:
                raise PortabilidadeProjetoError("Backup não possui snapshot do banco")
            restored_database = extracted.diretorio / PurePosixPath(database_entry.caminho_relativo)
            notify(2, 4, "Preservando estado atual para reversão")
            recovery_database = self._backup.criar_snapshot(
                self._database_path, temporary / "recovery.sqlite3"
            )
            staging = temporary / "managed-staging"
            staging.mkdir()
            for entry in extracted.manifesto.arquivos:
                if entry.tipo != "ARQUIVO_GERENCIADO":
                    continue
                relative = PurePosixPath(entry.caminho_relativo).relative_to("managed")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(extracted.diretorio / entry.caminho_relativo, destination)
            old_assets = temporary / "managed-previous"
            self._dispose_connections()
            notify(3, 4, "Restaurando banco e anexos")
            try:
                if self._managed_root.exists():
                    os.replace(self._managed_root, old_assets)
                self._managed_root.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, self._managed_root)
                self._backup.restaurar_snapshot(restored_database, self._database_path)
            except Exception:
                self._dispose_connections()
                self._backup.restaurar_snapshot(recovery_database, self._database_path)
                shutil.rmtree(self._managed_root, ignore_errors=True)
                if old_assets.exists():
                    os.replace(old_assets, self._managed_root)
                raise
            notify(4, 4, "Recuperação concluída")
        return self._database_path

    def _portable_content(
        self, projeto_id: UUID
    ) -> tuple[ConteudoBancoProjetoPortatil, dict[UUID, ReferenciaFontePdf]]:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para exportação")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise PortabilidadeProjetoError("Catálogo do projeto não está disponível")
            executions = work.execucoes_analise.listar_do_projeto(project.id)
            evidence = tuple(
                item
                for execution in executions
                for item in work.evidencias.listar_da_execucao(execution.id)
            )
            proposals = tuple(
                item
                for execution in executions
                for item in work.propostas.listar_da_execucao(execution.id)
            )
            decisions = tuple(
                decision
                for proposal in proposals
                if (decision := work.decisoes_revisao.obter_da_proposta(proposal.id)) is not None
            )
            sources = {
                document.id: source
                for document in project.documentos
                if (source := work.fontes_pdf.obter(document.id)) is not None
            }
        return (
            ConteudoBancoProjetoPortatil(
                projeto=project,
                catalogo=catalog,
                execucoes=executions,
                evidencias=evidence,
                propostas=proposals,
                decisoes=decisions,
            ),
            sources,
        )

    def _persist_imported_content(
        self,
        content: ConteudoBancoProjetoPortatil,
        manifest: ManifestoProjetoPortatil,
        *,
        substituir_existente: bool,
    ) -> bool:
        final_root = self._project_root(content.projeto.id)
        pdf_entries = {
            item.referencia_id: item
            for item in manifest.arquivos
            if item.tipo == "PDF" and item.referencia_id is not None
        }
        with self._unit_of_work() as work:
            existing = work.projetos.obter(content.projeto.id)
            if existing is not None and not substituir_existente:
                raise PortabilidadeProjetoError(
                    "Projeto já existe; confirme explicitamente a substituição"
                )
            if existing is not None:
                work.projetos.remover(content.projeto.id)
            work.catalogos.salvar(content.catalogo)
            work.projetos.salvar(content.projeto)
            for execution in content.execucoes:
                work.execucoes_analise.salvar(execution)
            for evidence in content.evidencias:
                work.evidencias.salvar(evidence)
            for proposal in content.propostas:
                work.propostas.salvar(proposal)
            for decision in content.decisoes:
                work.decisoes_revisao.salvar(decision)
            for document in content.projeto.documentos:
                entry = pdf_entries.get(document.id)
                if entry is None:
                    continue
                path = final_root / PurePosixPath(entry.caminho_relativo).relative_to("files")
                stat_result = path.stat()
                work.fontes_pdf.salvar(
                    ReferenciaFontePdf(
                        documento_id=document.id,
                        projeto_id=content.projeto.id,
                        caminho_canonico=path,
                        sha256=entry.sha256,
                        tamanho_bytes=entry.tamanho_bytes,
                        modificado_em_ns=stat_result.st_mtime_ns,
                    )
                )
            work.commit()
            return existing is not None

    def _stage_imported_files(
        self, extracted_root: Path, manifest: ManifestoProjetoPortatil
    ) -> Path:
        staging = self._managed_root.parent / f".import-{manifest.projeto_id}-{uuid4().hex}"
        staging.mkdir(parents=True)
        try:
            for entry in manifest.arquivos:
                if entry.tipo not in {"PDF", "FOTO"}:
                    continue
                relative = PurePosixPath(entry.caminho_relativo).relative_to("files")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(extracted_root / entry.caminho_relativo, destination)
            return staging
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _project(self, project_id: UUID) -> Projeto:
        with self._unit_of_work() as work:
            project = work.projetos.obter(project_id)
        if project is None:
            raise ProjetoNaoEncontradoError("Projeto não encontrado")
        return project

    def _save_project(self, project: Projeto) -> None:
        with self._unit_of_work() as work:
            work.projetos.salvar(project)
            work.commit()

    def _project_root(self, project_id: UUID) -> Path:
        return self._managed_root / str(project_id)

    def _managed_path(self, project_id: UUID, relative: str) -> Path:
        root = self._project_root(project_id).resolve()
        path = (root / PurePosixPath(relative)).resolve()
        if not path.is_relative_to(root):
            raise PortabilidadeProjetoError("Caminho de anexo saiu da pasta do projeto")
        return path

    def _photo_problems(
        self, project_id: UUID, photo: FotoElemento
    ) -> tuple[ProblemaIntegridadeProjeto, ...]:
        path = self._managed_path(project_id, photo.caminho_relativo)
        if not path.is_file():
            return (
                _problem(
                    "FOTO_AUSENTE",
                    "Foto não foi encontrada; use Localizar arquivo.",
                    photo.caminho_relativo,
                ),
            )
        if photo.sha256 is None or photo.tipo_mime is None or photo.tamanho_bytes is None:
            return (
                _problem(
                    "FOTO_SEM_METADADOS",
                    "Foto legada precisa ser localizada para registrar hash e tipo.",
                    photo.caminho_relativo,
                ),
            )
        digest, size = _file_digest(path)
        problems: list[ProblemaIntegridadeProjeto] = []
        if digest != photo.sha256 or size != photo.tamanho_bytes:
            problems.append(
                _problem(
                    "FOTO_ADULTERADA",
                    "Hash ou tamanho da foto diverge do registro.",
                    photo.caminho_relativo,
                )
            )
        detected = _detect_photo_mime(path)
        if detected != photo.tipo_mime:
            problems.append(
                _problem(
                    "TIPO_FOTO_DIVERGENTE",
                    "Assinatura do arquivo não corresponde ao tipo registrado.",
                    photo.caminho_relativo,
                )
            )
        return tuple(problems)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value


def _element(project: Projeto, element_id: UUID) -> ElementoProjetoType:
    element = next((item for item in project.elementos if item.id == element_id), None)
    if element is None:
        raise PortabilidadeProjetoError("Elemento não pertence ao projeto")
    return element


def _replace_element(project: Projeto, updated: ElementoProjetoType) -> Projeto:
    return replace(
        project,
        elementos=tuple(updated if item.id == updated.id else item for item in project.elementos),
    )


def _inspect_photo(path: Path) -> tuple[str, int, str]:
    if not path.is_file():
        raise PortabilidadeProjetoError("Arquivo de foto não existe")
    digest, size = _file_digest(path)
    mime_type = _detect_photo_mime(path)
    if mime_type is None:
        raise PortabilidadeProjetoError("Selecione uma imagem JPEG, PNG, TIFF ou WebP válida")
    return digest, size, mime_type


def _detect_photo_mime(path: Path) -> str | None:
    with path.open("rb") as source:
        header = source.read(16)
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def _source_problems(
    source: ReferenciaFontePdf, name: str
) -> tuple[ProblemaIntegridadeProjeto, ...]:
    path = source.caminho_canonico.expanduser().resolve()
    if not path.is_file():
        return (_problem("PDF_AUSENTE", f"PDF {name} não foi encontrado.", str(path)),)
    digest, size = _file_digest(path)
    problems: list[ProblemaIntegridadeProjeto] = []
    if digest != source.sha256 or size != source.tamanho_bytes:
        problems.append(
            _problem("PDF_ADULTERADO", f"PDF {name} diverge do hash ou tamanho importado.")
        )
    with path.open("rb") as stream:
        if not stream.read(5).startswith(b"%PDF-"):
            problems.append(_problem("TIPO_PDF_INVALIDO", f"Arquivo {name} não é um PDF."))
    return tuple(problems)


def _pdf_source_available(source: ReferenciaFontePdf | None) -> bool:
    return source is not None and source.caminho_canonico.is_file()


def _package_origin(
    source: Path,
    relative: str,
    kind: str,
    mime_type: str,
    reference_id: UUID | None = None,
) -> OrigemArquivoPacote:
    digest, size = _file_digest(source)
    return OrigemArquivoPacote(
        arquivo=ArquivoPacoteProjeto(
            caminho_relativo=relative,
            tipo=kind,
            sha256=digest,
            tamanho_bytes=size,
            tipo_mime=mime_type,
            referencia_id=reference_id,
        ),
        caminho_origem=source,
    )


def _file_digest(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except OSError as error:
        raise PortabilidadeProjetoError("Não foi possível copiar o arquivo") from error
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _problem(code: str, message: str, path: str | None = None) -> ProblemaIntegridadeProjeto:
    return ProblemaIntegridadeProjeto(
        codigo=code,
        mensagem=message,
        caminho_relativo=path,
    )


def _mime_for_path(path: Path) -> str:
    photo_mime = _detect_photo_mime(path)
    if photo_mime is not None:
        return photo_mime
    with path.open("rb") as source:
        if source.read(5).startswith(b"%PDF-"):
            return "application/pdf"
    return "application/octet-stream"
