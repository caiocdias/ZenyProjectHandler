"""Exclusão transacional e recuperável de arquivos gerenciados."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from zeny_project_handler.application.errors import RecuperacaoLimpezaBloqueadaError
from zeny_project_handler.domain.project import FotoElemento, Projeto
from zeny_project_handler.logging_config import operation_logger

from .import_recovery import fingerprint_arvore_gerenciada
from .recovery_journal import (
    read_json_object,
    validated_relative_path,
    write_json_object_atomic,
)

JOURNAL_VERSION = 1
RECOVERY_DIRECTORY_NAME = ".cleanup-recovery"
JOURNAL_SUFFIX = ".cleanup-v1.json"
_MAX_JOURNAL_BYTES = 256 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_JOURNAL_FIELDS = frozenset(
    {
        "version",
        "operation_id",
        "project_id",
        "kind",
        "root_existed",
        "created_at",
        "paths",
        "candidates",
    }
)
_PATH_FIELDS = frozenset({"project", "tombstone"})
_CANDIDATE_FIELDS = frozenset({"relative_path", "sha256"})


class TipoLimpezaGerenciada(StrEnum):
    PROJETO = "project"
    BLOBS = "blobs"


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidatoLimpezaGerenciada:
    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CaminhosLimpezaGerenciada:
    project: str
    tombstone: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JournalLimpezaGerenciada:
    version: int
    operation_id: UUID
    project_id: UUID
    kind: TipoLimpezaGerenciada
    root_existed: bool
    created_at: datetime
    paths: CaminhosLimpezaGerenciada
    candidates: tuple[CandidatoLimpezaGerenciada, ...] = ()

    @classmethod
    def novo(
        cls,
        *,
        operation_id: UUID,
        project_id: UUID,
        kind: TipoLimpezaGerenciada,
        root_existed: bool,
        created_at: datetime,
        candidates: tuple[CandidatoLimpezaGerenciada, ...] = (),
    ) -> JournalLimpezaGerenciada:
        return cls(
            version=JOURNAL_VERSION,
            operation_id=operation_id,
            project_id=project_id,
            kind=kind,
            root_existed=root_existed,
            created_at=created_at,
            paths=CaminhosLimpezaGerenciada(
                project=str(project_id),
                tombstone=(f"{RECOVERY_DIRECTORY_NAME}/{operation_id}.tombstone"),
            ),
            candidates=candidates,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoLimpezaGerenciada:
    arquivos_removidos: int = 0
    pendente: bool = False


class ArmazenamentoJournalLimpeza:
    """Persista tarefas independentes dentro da raiz gerenciada."""

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory.expanduser().resolve()
        self.managed_root = self.data_directory / "project-files"
        self.recovery_root = self.managed_root / RECOVERY_DIRECTORY_NAME

    def escrever(self, journal: JournalLimpezaGerenciada) -> None:
        _validate_journal(journal)
        self._prepare_root()
        payload = asdict(journal)
        payload["operation_id"] = str(journal.operation_id)
        payload["project_id"] = str(journal.project_id)
        payload["kind"] = journal.kind.value
        payload["created_at"] = journal.created_at.isoformat()
        write_json_object_atomic(
            self.journal_path(journal.operation_id),
            payload,
            max_bytes=_MAX_JOURNAL_BYTES,
            error=_blocked,
        )

    def carregar_todos(self) -> tuple[JournalLimpezaGerenciada, ...]:
        self._validate_roots()
        if not self.recovery_root.exists():
            return ()
        try:
            entries = tuple(self.recovery_root.iterdir())
        except OSError as caught:
            raise _blocked("a raiz de recuperação não pôde ser inspecionada") from caught
        journal_paths = tuple(path for path in entries if path.name.endswith(JOURNAL_SUFFIX))
        journals = tuple(self._read(path) for path in journal_paths)
        expected_entries = {self.journal_path(item.operation_id).name for item in journals} | {
            self.tombstone_path(item).name
            for item in journals
            if item.kind is TipoLimpezaGerenciada.PROJETO and self.tombstone_path(item).exists()
        }
        unexpected = {path.name for path in entries} - expected_entries
        if unexpected:
            raise _blocked("a raiz de recuperação contém resíduos sem journal válido")
        return tuple(sorted(journals, key=lambda item: (item.created_at, str(item.operation_id))))

    def remover(self, journal: JournalLimpezaGerenciada) -> None:
        try:
            self.journal_path(journal.operation_id).unlink(missing_ok=True)
        except OSError as caught:
            raise OSError("o journal concluído não pôde ser removido") from caught

    def journal_path(self, operation_id: UUID) -> Path:
        return self.recovery_root / f"{operation_id}{JOURNAL_SUFFIX}"

    def project_path(self, journal: JournalLimpezaGerenciada) -> Path:
        _validate_journal(journal)
        return self.managed_root / PurePosixPath(journal.paths.project)

    def tombstone_path(self, journal: JournalLimpezaGerenciada) -> Path:
        _validate_journal(journal)
        return self.managed_root / PurePosixPath(journal.paths.tombstone)

    def _read(self, path: Path) -> JournalLimpezaGerenciada:
        raw_operation_id = path.name.removesuffix(JOURNAL_SUFFIX)
        try:
            path_operation_id = UUID(raw_operation_id)
        except ValueError as caught:
            raise _blocked("o nome do journal não identifica uma operação") from caught
        payload = read_json_object(
            path,
            max_bytes=_MAX_JOURNAL_BYTES,
            error=_blocked,
        )
        journal = _parse_journal(payload)
        if journal.operation_id != path_operation_id:
            raise _blocked("o nome e o conteúdo do journal divergem")
        return journal

    def _prepare_root(self) -> None:
        self._validate_roots()
        try:
            self.managed_root.mkdir(parents=True, exist_ok=True)
            self.recovery_root.mkdir(exist_ok=True)
        except OSError as caught:
            raise _blocked("a raiz reservada da limpeza não pôde ser criada") from caught
        self._validate_roots()

    def _validate_roots(self) -> None:
        for path, label in (
            (self.data_directory, "a raiz de dados"),
            (self.managed_root, "a raiz gerenciada"),
            (self.recovery_root, "a raiz de recuperação"),
        ):
            if not os.path.lexists(path):
                continue
            if path.is_symlink() or not path.is_dir():
                raise _blocked(f"{label} não é um diretório regular")


class GerenciadorArquivosGerenciados:
    """Coordene tombstones e coleta por digest ao redor do commit SQLite."""

    def __init__(
        self,
        data_directory: Path,
        listar_projetos: Callable[[], tuple[Projeto, ...]],
        *,
        relogio: Callable[[], datetime] | None = None,
        gerar_id: Callable[[], UUID] = uuid4,
        remover_arvore: Callable[[Path], None] = shutil.rmtree,
        remover_arquivo: Callable[[Path], None] | None = None,
    ) -> None:
        self._store = ArmazenamentoJournalLimpeza(data_directory)
        self._list_projects = listar_projetos
        self._clock = relogio or (lambda: datetime.now(UTC))
        self._new_id = gerar_id
        self._remove_tree = remover_arvore
        self._remove_file = remover_arquivo or (lambda path: path.unlink())

    @property
    def armazenamento(self) -> ArmazenamentoJournalLimpeza:
        return self._store

    def preparar_exclusao_projeto(self, project_id: UUID) -> JournalLimpezaGerenciada:
        project = self._store.managed_root / str(project_id)
        root_existed = os.path.lexists(project)
        if root_existed:
            fingerprint_arvore_gerenciada(project)
        journal = JournalLimpezaGerenciada.novo(
            operation_id=self._new_id(),
            project_id=project_id,
            kind=TipoLimpezaGerenciada.PROJETO,
            root_existed=root_existed,
            created_at=self._aware_now(),
        )
        self._store.escrever(journal)
        if root_existed:
            tombstone = self._store.tombstone_path(journal)
            try:
                os.replace(project, tombstone)
            except OSError:
                self._store.remover(journal)
                raise
        return journal

    def preparar_coleta_fotos(
        self,
        project_id: UUID,
        photos: Iterable[FotoElemento],
    ) -> JournalLimpezaGerenciada | None:
        candidates: dict[str, CandidatoLimpezaGerenciada] = {}
        for photo in photos:
            relative = validated_relative_path(photo.caminho_relativo, error=_blocked)
            path = self._managed_file_path(project_id, relative)
            digest = photo.sha256
            if digest is None:
                if not os.path.lexists(path):
                    continue
                self._assert_regular_file(path)
                digest = _file_digest(path)
            candidate = CandidatoLimpezaGerenciada(
                relative_path=relative.as_posix(),
                sha256=digest,
            )
            key = candidate.relative_path.casefold()
            existing = candidates.get(key)
            if existing is not None and existing.sha256 != candidate.sha256:
                raise _blocked("duas referências divergem sobre o digest do mesmo caminho")
            candidates[key] = candidate
        if not candidates:
            return None
        journal = JournalLimpezaGerenciada.novo(
            operation_id=self._new_id(),
            project_id=project_id,
            kind=TipoLimpezaGerenciada.BLOBS,
            root_existed=False,
            created_at=self._aware_now(),
            candidates=tuple(
                sorted(candidates.values(), key=lambda item: (item.relative_path, item.sha256))
            ),
        )
        self._store.escrever(journal)
        return journal

    def cancelar(self, journal: JournalLimpezaGerenciada | None) -> None:
        if journal is None:
            return
        if journal.kind is TipoLimpezaGerenciada.PROJETO:
            self._restore_project(journal)
        self._store.remover(journal)

    def concluir(
        self,
        journal: JournalLimpezaGerenciada | None,
    ) -> ResultadoLimpezaGerenciada:
        if journal is None:
            return ResultadoLimpezaGerenciada()
        observation = operation_logger(
            "managed_files.cleanup",
            project_id=journal.project_id,
        )
        observation.started(phase=journal.kind.value, journal_version=journal.version)
        try:
            removed = self._execute_committed(journal)
            self._store.remover(journal)
        except Exception as caught:
            observation.failed(
                caught,
                expected=True,
                phase=journal.kind.value,
                journal_version=journal.version,
                recovery_action="retry_cleanup",
            )
            return ResultadoLimpezaGerenciada(pendente=True)
        observation.succeeded(
            phase=journal.kind.value,
            journal_version=journal.version,
            item_count=removed,
        )
        return ResultadoLimpezaGerenciada(arquivos_removidos=removed)

    def reconciliar_pendencias(self) -> int:
        """Restaure rollback comprovado ou repita limpeza confirmada pelo SQLite."""
        pending = self._store.carregar_todos()
        if not pending:
            return 0
        projects = {project.id: project for project in self._list_projects()}
        remaining = 0
        for journal in pending:
            observation = operation_logger(
                "managed_files.recovery",
                project_id=journal.project_id,
            )
            observation.started(phase=journal.kind.value, journal_version=journal.version)
            try:
                if journal.kind is TipoLimpezaGerenciada.PROJETO and journal.project_id in projects:
                    self._restore_project(journal)
                    action = "restore_tombstone"
                    removed = 0
                else:
                    removed = self._execute_committed(journal, projects=tuple(projects.values()))
                    action = "retry_cleanup"
                self._store.remover(journal)
            except RecuperacaoLimpezaBloqueadaError as caught:
                observation.failed(
                    caught,
                    expected=True,
                    phase=journal.kind.value,
                    journal_version=journal.version,
                    recovery_action="blocked",
                )
                raise
            except OSError as caught:
                remaining += 1
                observation.failed(
                    caught,
                    expected=True,
                    phase=journal.kind.value,
                    journal_version=journal.version,
                    recovery_action="retry_cleanup",
                )
                continue
            observation.succeeded(
                phase=journal.kind.value,
                journal_version=journal.version,
                recovery_action=action,
                item_count=removed,
            )
        return remaining

    def _execute_committed(
        self,
        journal: JournalLimpezaGerenciada,
        *,
        projects: tuple[Projeto, ...] | None = None,
    ) -> int:
        if journal.kind is TipoLimpezaGerenciada.PROJETO:
            return self._remove_tombstone(journal)
        current_projects = projects if projects is not None else self._list_projects()
        live_digests = {
            photo.sha256
            for project in current_projects
            if project.id == journal.project_id
            for element in project.elementos
            for photo in element.fotos
            if photo.sha256 is not None
        }
        removed = 0
        for candidate in journal.candidates:
            if candidate.sha256 in live_digests:
                continue
            relative = validated_relative_path(candidate.relative_path, error=_blocked)
            path = self._managed_file_path(journal.project_id, relative)
            if not os.path.lexists(path):
                continue
            self._assert_regular_file(path)
            if _file_digest(path) != candidate.sha256:
                raise _blocked("um blob candidato diverge do digest registrado")
            self._remove_file(path)
            removed += 1
        return removed

    def _restore_project(self, journal: JournalLimpezaGerenciada) -> None:
        project = self._store.project_path(journal)
        tombstone = self._store.tombstone_path(journal)
        project_exists = os.path.lexists(project)
        tombstone_exists = os.path.lexists(tombstone)
        if not journal.root_existed:
            if tombstone_exists:
                raise _blocked("um tombstone existe para uma raiz originalmente ausente")
            return
        if project_exists and tombstone_exists:
            raise _blocked("projeto e tombstone existem simultaneamente")
        if project_exists:
            fingerprint_arvore_gerenciada(project)
            return
        if not tombstone_exists:
            raise _blocked("a raiz e o tombstone esperados estão ausentes")
        fingerprint_arvore_gerenciada(tombstone)
        try:
            os.replace(tombstone, project)
        except OSError as caught:
            raise OSError("o tombstone não pôde ser restaurado") from caught

    def _remove_tombstone(self, journal: JournalLimpezaGerenciada) -> int:
        project = self._store.project_path(journal)
        tombstone = self._store.tombstone_path(journal)
        if os.path.lexists(project):
            raise _blocked("a raiz do projeto reapareceu depois do commit de exclusão")
        if not os.path.lexists(tombstone):
            if journal.root_existed:
                return 0
            return 0
        if not journal.root_existed:
            raise _blocked("um tombstone existe para uma raiz originalmente ausente")
        fingerprint = fingerprint_arvore_gerenciada(tombstone)
        if fingerprint is None:
            return 0
        file_count = sum(1 for path in tombstone.rglob("*") if path.is_file())
        self._remove_tree(tombstone)
        return file_count

    def _managed_file_path(self, project_id: UUID, relative: PurePosixPath) -> Path:
        data_root = self._store.data_directory.resolve()
        managed_root = self._store.managed_root.resolve()
        project_root = (managed_root / str(project_id)).resolve()
        path = (project_root / relative).resolve()
        if (
            not managed_root.is_relative_to(data_root)
            or not project_root.is_relative_to(managed_root)
            or not path.is_relative_to(project_root)
        ):
            raise _blocked("um caminho candidato saiu da raiz de dados gerenciada")
        return path

    @staticmethod
    def _assert_regular_file(path: Path) -> None:
        if path.is_symlink() or not path.is_file():
            raise _blocked("um blob candidato não é um arquivo regular")

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Relógio da limpeza deve retornar data com fuso horário")
        return value


def fotos_removidas(project: Projeto, updated: Projeto) -> tuple[FotoElemento, ...]:
    """Retorne fotos que perderam sua referência de entidade na nova versão."""
    live_ids = {photo.id for element in updated.elementos for photo in element.fotos}
    return tuple(
        photo
        for element in project.elementos
        for photo in element.fotos
        if photo.id not in live_ids
    )


def _parse_journal(payload: dict[str, object]) -> JournalLimpezaGerenciada:
    if set(payload) != _JOURNAL_FIELDS:
        raise _blocked("a estrutura do journal de limpeza não corresponde ao formato suportado")
    paths_payload = payload.get("paths")
    candidates_payload = payload.get("candidates")
    if not isinstance(paths_payload, dict) or set(paths_payload) != _PATH_FIELDS:
        raise _blocked("a estrutura de caminhos do journal de limpeza é inválida")
    if not isinstance(candidates_payload, list):
        raise _blocked("a lista de candidatos do journal de limpeza é inválida")
    candidates: list[CandidatoLimpezaGerenciada] = []
    for raw_candidate in candidates_payload:
        if not isinstance(raw_candidate, dict) or set(raw_candidate) != _CANDIDATE_FIELDS:
            raise _blocked("um candidato do journal de limpeza é inválido")
        candidates.append(
            CandidatoLimpezaGerenciada(
                relative_path=_strict_string(raw_candidate["relative_path"]),
                sha256=_strict_string(raw_candidate["sha256"]),
            )
        )
    try:
        journal = JournalLimpezaGerenciada(
            version=_strict_int(payload["version"]),
            operation_id=UUID(_strict_string(payload["operation_id"])),
            project_id=UUID(_strict_string(payload["project_id"])),
            kind=TipoLimpezaGerenciada(_strict_string(payload["kind"])),
            root_existed=_strict_bool(payload["root_existed"]),
            created_at=datetime.fromisoformat(_strict_string(payload["created_at"])),
            paths=CaminhosLimpezaGerenciada(
                project=_strict_string(paths_payload["project"]),
                tombstone=_strict_string(paths_payload["tombstone"]),
            ),
            candidates=tuple(candidates),
        )
    except (KeyError, TypeError, ValueError) as caught:
        raise _blocked("os valores do journal de limpeza são inválidos") from caught
    _validate_journal(journal)
    return journal


def _validate_journal(journal: JournalLimpezaGerenciada) -> None:
    if journal.version != JOURNAL_VERSION:
        raise _blocked("a versão do journal de limpeza não é suportada")
    if journal.created_at.tzinfo is None or journal.created_at.utcoffset() is None:
        raise _blocked("o journal de limpeza não possui horário absoluto")
    validated_relative_path(journal.paths.project, error=_blocked)
    validated_relative_path(journal.paths.tombstone, error=_blocked)
    expected = JournalLimpezaGerenciada.novo(
        operation_id=journal.operation_id,
        project_id=journal.project_id,
        kind=journal.kind,
        root_existed=journal.root_existed,
        created_at=journal.created_at,
        candidates=journal.candidates,
    ).paths
    if journal.paths != expected:
        raise _blocked("os caminhos do journal não correspondem à identidade da limpeza")
    if journal.kind is TipoLimpezaGerenciada.PROJETO:
        if journal.candidates:
            raise _blocked("uma exclusão de projeto não pode listar blobs parciais")
    elif journal.root_existed or not journal.candidates:
        raise _blocked("uma coleta parcial deve listar candidatos sem tombstone de projeto")
    paths: set[str] = set()
    for candidate in journal.candidates:
        relative = validated_relative_path(candidate.relative_path, error=_blocked).as_posix()
        digest = candidate.sha256.strip().lower()
        if relative != candidate.relative_path or digest != candidate.sha256:
            raise _blocked("um candidato do journal não está em forma canônica")
        if not _SHA256_PATTERN.fullmatch(digest):
            raise _blocked("um candidato do journal possui digest inválido")
        key = relative.casefold()
        if key in paths:
            raise _blocked("o journal repete um caminho candidato de limpeza")
        paths.add(key)


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected integer")
    return value


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected boolean")
    return value


def _blocked(detail: str) -> RecuperacaoLimpezaBloqueadaError:
    return RecuperacaoLimpezaBloqueadaError(
        "A limpeza de arquivos gerenciados foi bloqueada: "
        f"{detail}. Preserve project-files/.cleanup-recovery e recupere por backup ou suporte."
    )
