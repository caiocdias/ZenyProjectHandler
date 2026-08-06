"""Journal e reconciliação de substituições de projetos interrompidas."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.application.errors import RecuperacaoImportacaoBloqueadaError
from zeny_project_handler.logging_config import operation_logger
from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao

JOURNAL_VERSION = 1
RECOVERY_DIRECTORY_NAME = ".import-recovery"
JOURNAL_FILE_NAME = "import-journal-v1.json"
_MAX_JOURNAL_BYTES = 64 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_JOURNAL_FIELDS = frozenset(
    {
        "version",
        "operation_id",
        "project_id",
        "package_sha256",
        "plan_sha256",
        "target_state_sha256",
        "new_files_sha256",
        "previous_files_sha256",
        "previous_assets_existed",
        "phase",
        "created_at",
        "paths",
    }
)
_PATH_FIELDS = frozenset({"project", "workspace", "staging", "previous"})


class FaseJournalImportacao(StrEnum):
    PREPARANDO = "preparing"
    PREPARADO = "prepared"
    ARQUIVOS_TROCADOS = "files_swapped"
    BANCO_CONFIRMADO = "database_committed"
    RESTAURANDO_ANTERIOR = "restoring_previous"
    LIMPEZA_CONCLUIDA = "cleanup_complete"


class PontoFalhaImportacao(StrEnum):
    """Fronteiras estáveis para simular encerramento abrupto em testes."""

    ANTES_PREPARAR = "before_prepared"
    DEPOIS_PREPARAR = "after_prepared"
    ANTES_TROCAR_ARQUIVOS = "before_files_swapped"
    DEPOIS_MOVER_ANTERIOR = "after_previous_moved"
    DEPOIS_TROCAR_ARQUIVOS = "after_files_swapped"
    ANTES_COMMIT_BANCO = "before_database_commit"
    DEPOIS_COMMIT_BANCO = "after_database_commit"
    DEPOIS_CONFIRMAR_BANCO = "after_database_committed"
    ANTES_LIMPEZA = "before_cleanup"
    DEPOIS_LIMPEZA = "after_cleanup"


@dataclass(frozen=True, slots=True, kw_only=True)
class CaminhosJournalImportacao:
    project: str
    workspace: str
    staging: str
    previous: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JournalImportacaoProjeto:
    version: int
    operation_id: UUID
    project_id: UUID
    package_sha256: str
    plan_sha256: str
    target_state_sha256: str
    new_files_sha256: str
    previous_files_sha256: str | None
    previous_assets_existed: bool
    phase: FaseJournalImportacao
    created_at: datetime
    paths: CaminhosJournalImportacao

    @classmethod
    def novo(
        cls,
        *,
        operation_id: UUID,
        project_id: UUID,
        package_sha256: str,
        plan_sha256: str,
        target_state_sha256: str,
        new_files_sha256: str,
        previous_files_sha256: str | None,
        previous_assets_existed: bool,
        created_at: datetime,
    ) -> JournalImportacaoProjeto:
        workspace = f"{RECOVERY_DIRECTORY_NAME}/{operation_id}"
        return cls(
            version=JOURNAL_VERSION,
            operation_id=operation_id,
            project_id=project_id,
            package_sha256=package_sha256,
            plan_sha256=plan_sha256,
            target_state_sha256=target_state_sha256,
            new_files_sha256=new_files_sha256,
            previous_files_sha256=previous_files_sha256,
            previous_assets_existed=previous_assets_existed,
            phase=FaseJournalImportacao.PREPARANDO,
            created_at=created_at,
            paths=CaminhosJournalImportacao(
                project=str(project_id),
                workspace=workspace,
                staging=f"{workspace}/staging",
                previous=f"{workspace}/previous",
            ),
        )

    def avancar(self, phase: FaseJournalImportacao) -> JournalImportacaoProjeto:
        return replace(self, phase=phase)


@dataclass(frozen=True, slots=True, kw_only=True)
class CaminhosImportacaoResolvidos:
    project: Path
    workspace: Path
    staging: Path
    previous: Path


class ArmazenamentoJournalImportacao:
    """Publique um único journal canônico dentro da raiz gerenciada."""

    def __init__(self, data_directory: Path) -> None:
        self._data_directory = data_directory.expanduser().resolve()
        self.managed_root = self._data_directory / "project-files"
        self.recovery_root = self.managed_root / RECOVERY_DIRECTORY_NAME
        self.journal_path = self.recovery_root / JOURNAL_FILE_NAME

    def carregar(self) -> JournalImportacaoProjeto | None:
        self._validar_raizes_existentes()
        if not _path_exists(self.journal_path):
            self._validar_ausencia_de_residuo_sem_journal()
            return None
        if self.journal_path.is_symlink() or not self.journal_path.is_file():
            raise _blocked("o journal não é um arquivo regular")
        try:
            if self.journal_path.stat().st_size > _MAX_JOURNAL_BYTES:
                raise _blocked("o journal excede o limite de tamanho")
            raw = self.journal_path.read_text(encoding="utf-8")
            payload = json.loads(raw, object_pairs_hook=_object_without_duplicates)
        except RecuperacaoImportacaoBloqueadaError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise _blocked("o journal está corrompido ou ilegível") from error
        return _parse_journal(payload)

    def escrever(self, journal: JournalImportacaoProjeto) -> None:
        _validate_journal(journal)
        self._preparar_raiz()
        payload = asdict(journal)
        payload["operation_id"] = str(journal.operation_id)
        payload["project_id"] = str(journal.project_id)
        payload["phase"] = journal.phase.value
        payload["created_at"] = journal.created_at.isoformat()
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > _MAX_JOURNAL_BYTES:
            raise _blocked("o journal excede o limite de tamanho")
        try:
            with sibling_temporary_file(self.journal_path) as temporary:
                with temporary.open("wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.journal_path)
        except OSError as error:
            raise RecuperacaoImportacaoBloqueadaError(
                "Não foi possível publicar atomicamente o journal de importação; "
                "preserve project-files/.import-recovery e tente iniciar novamente."
            ) from error

    def remover(self) -> None:
        try:
            self.journal_path.unlink(missing_ok=True)
        except OSError as error:
            raise _blocked("o journal concluído não pôde ser removido") from error

    def resolver(self, journal: JournalImportacaoProjeto) -> CaminhosImportacaoResolvidos:
        _validate_journal(journal)
        return CaminhosImportacaoResolvidos(
            project=self.managed_root / PurePosixPath(journal.paths.project),
            workspace=self.managed_root / PurePosixPath(journal.paths.workspace),
            staging=self.managed_root / PurePosixPath(journal.paths.staging),
            previous=self.managed_root / PurePosixPath(journal.paths.previous),
        )

    def preparar_workspace(self, journal: JournalImportacaoProjeto) -> CaminhosImportacaoResolvidos:
        paths = self.resolver(journal)
        self._preparar_raiz()
        try:
            paths.workspace.mkdir()
            paths.staging.mkdir()
        except OSError as error:
            raise RecuperacaoImportacaoBloqueadaError(
                "Não foi possível reservar o workspace da importação; "
                "preserve project-files/.import-recovery e reinicie para reconciliar."
            ) from error
        return paths

    def _preparar_raiz(self) -> None:
        self._validar_raizes_existentes()
        try:
            self.managed_root.mkdir(parents=True, exist_ok=True)
            self.recovery_root.mkdir(exist_ok=True)
        except OSError as error:
            raise _blocked("a raiz reservada do journal não pôde ser criada") from error
        self._validar_raizes_existentes()

    def _validar_raizes_existentes(self) -> None:
        for path, label in (
            (self.managed_root, "a raiz gerenciada"),
            (self.recovery_root, "a raiz de recuperação"),
        ):
            if not _path_exists(path):
                continue
            if path.is_symlink() or not path.is_dir():
                raise _blocked(f"{label} não é um diretório regular")

    def _validar_ausencia_de_residuo_sem_journal(self) -> None:
        if not self.recovery_root.exists():
            return
        try:
            residues = tuple(self.recovery_root.iterdir())
        except OSError as error:
            raise _blocked("a raiz de recuperação não pôde ser inspecionada") from error
        if residues:
            raise _blocked("há resíduos sem journal que identifique sua operação")


class RecuperadorImportacaoProjeto:
    """Decida por recibo transacional e reconcilie apenas caminhos comprovados."""

    def __init__(self, data_directory: Path) -> None:
        self._store = ArmazenamentoJournalImportacao(data_directory)

    @property
    def armazenamento(self) -> ArmazenamentoJournalImportacao:
        return self._store

    def registrar(self, journal: JournalImportacaoProjeto) -> None:
        self._store.escrever(journal)
        observation = operation_logger(
            "portability.import.journal",
            project_id=journal.project_id,
        )
        observation.succeeded(phase=journal.phase.value, journal_version=journal.version)

    def reconciliar(
        self,
        obter_comprovante: Callable[[UUID], ComprovanteCommitImportacao | None],
    ) -> str | None:
        inspection = operation_logger("portability.import.recovery")
        inspection.started(phase="inspect")
        try:
            journal = self._store.carregar()
        except RecuperacaoImportacaoBloqueadaError as error:
            inspection.failed(error, expected=True, phase="invalid_journal")
            raise
        if journal is None:
            inspection.succeeded(phase="idle", recovery_action="none")
            return None
        observation = operation_logger(
            "portability.import.recovery",
            project_id=journal.project_id,
        )
        observation.started(phase=journal.phase.value, journal_version=journal.version)
        try:
            receipt = obter_comprovante(journal.operation_id)
            if receipt is None:
                self._restaurar_anterior(journal)
                action = "previous_restored"
            else:
                self.concluir_commit(journal, receipt)
                action = "commit_completed"
        except RecuperacaoImportacaoBloqueadaError as error:
            observation.failed(error, expected=True, phase=journal.phase.value)
            raise
        except (OSError, RuntimeError) as error:
            blocked = _blocked("a reconciliação foi interrompida por uma falha local")
            observation.failed(blocked, expected=True, phase=journal.phase.value)
            raise blocked from error
        observation.succeeded(phase="cleanup_complete", recovery_action=action)
        return action

    def _restaurar_anterior(self, journal: JournalImportacaoProjeto) -> None:
        paths = self._store.resolver(journal)
        self._validar_workspace(paths)
        current_digest = fingerprint_arvore_gerenciada(paths.project)
        previous_digest = fingerprint_arvore_gerenciada(paths.previous)
        recovery_in_progress = journal.phase is FaseJournalImportacao.RESTAURANDO_ANTERIOR
        if not recovery_in_progress:
            self._validar_estado_para_restauracao(
                journal,
                current_digest=current_digest,
                previous_digest=previous_digest,
            )
            journal = journal.avancar(FaseJournalImportacao.RESTAURANDO_ANTERIOR)
            self.registrar(journal)
        if journal.previous_assets_existed:
            self._restaurar_raiz_existente(
                journal,
                paths,
                current_digest=current_digest,
                previous_digest=previous_digest,
                recovery_in_progress=recovery_in_progress,
            )
        else:
            self._restaurar_raiz_ausente(
                journal,
                paths,
                current_digest=current_digest,
                previous_digest=previous_digest,
                recovery_in_progress=recovery_in_progress,
            )
        self._remover_workspace(paths)
        self.registrar(journal.avancar(FaseJournalImportacao.LIMPEZA_CONCLUIDA))
        self._store.remover()

    def _restaurar_raiz_existente(
        self,
        journal: JournalImportacaoProjeto,
        paths: CaminhosImportacaoResolvidos,
        *,
        current_digest: str | None,
        previous_digest: str | None,
        recovery_in_progress: bool,
    ) -> None:
        expected_previous = journal.previous_files_sha256
        if expected_previous is None:
            raise _blocked("o journal não identifica os arquivos anteriores")
        if previous_digest == expected_previous:
            if not recovery_in_progress and current_digest not in {
                None,
                journal.new_files_sha256,
            }:
                raise _blocked("a pasta publicada não corresponde ao journal")
            if current_digest is not None:
                if recovery_in_progress:
                    _remove_owned_regular_tree(paths.project)
                else:
                    _remove_verified_tree(paths.project, journal.new_files_sha256)
            os.replace(paths.previous, paths.project)
            return
        if previous_digest is None and current_digest == expected_previous:
            return
        raise _blocked("o estado dos arquivos anteriores é ambíguo")

    @staticmethod
    def _restaurar_raiz_ausente(
        journal: JournalImportacaoProjeto,
        paths: CaminhosImportacaoResolvidos,
        *,
        current_digest: str | None,
        previous_digest: str | None,
        recovery_in_progress: bool,
    ) -> None:
        if journal.previous_files_sha256 is not None or previous_digest is not None:
            raise _blocked("o journal diverge sobre a existência da pasta anterior")
        if not recovery_in_progress and current_digest not in {None, journal.new_files_sha256}:
            raise _blocked("a pasta publicada não corresponde ao journal")
        if current_digest is not None:
            if recovery_in_progress:
                _remove_owned_regular_tree(paths.project)
            else:
                _remove_verified_tree(paths.project, journal.new_files_sha256)

    @staticmethod
    def _validar_estado_para_restauracao(
        journal: JournalImportacaoProjeto,
        *,
        current_digest: str | None,
        previous_digest: str | None,
    ) -> None:
        if journal.previous_assets_existed:
            expected_previous = journal.previous_files_sha256
            if expected_previous is None:
                raise _blocked("o journal não identifica os arquivos anteriores")
            valid = (
                previous_digest == expected_previous
                and current_digest in {None, journal.new_files_sha256}
            ) or (previous_digest is None and current_digest == expected_previous)
            if not valid:
                raise _blocked("o estado dos arquivos anteriores é ambíguo")
            return
        if previous_digest is not None or current_digest not in {
            None,
            journal.new_files_sha256,
        }:
            raise _blocked("o estado do destino novo é ambíguo")

    def concluir_commit(
        self,
        journal: JournalImportacaoProjeto,
        receipt: ComprovanteCommitImportacao,
        *,
        injetar_falha: Callable[[PontoFalhaImportacao], None] | None = None,
    ) -> None:
        _validate_receipt(journal, receipt)
        if journal.phase in {
            FaseJournalImportacao.PREPARANDO,
            FaseJournalImportacao.PREPARADO,
            FaseJournalImportacao.RESTAURANDO_ANTERIOR,
        }:
            raise _blocked("o recibo e a fase do journal são incompatíveis")
        paths = self._store.resolver(journal)
        self._validar_workspace(paths)
        if fingerprint_arvore_gerenciada(paths.project) != journal.new_files_sha256:
            raise _blocked("os arquivos publicados não correspondem ao recibo do banco")
        if _path_exists(paths.staging):
            raise _blocked("há staging inesperado depois do commit do banco")
        if journal.phase is FaseJournalImportacao.ARQUIVOS_TROCADOS:
            previous_digest = fingerprint_arvore_gerenciada(paths.previous)
            if journal.previous_assets_existed:
                if previous_digest != journal.previous_files_sha256:
                    raise _blocked("os arquivos anteriores divergem do journal")
            elif previous_digest is not None:
                raise _blocked("há uma pasta anterior não declarada no journal")
            journal = journal.avancar(FaseJournalImportacao.BANCO_CONFIRMADO)
            self.registrar(journal)
        _inject(injetar_falha, PontoFalhaImportacao.DEPOIS_CONFIRMAR_BANCO)
        _inject(injetar_falha, PontoFalhaImportacao.ANTES_LIMPEZA)
        self._remover_workspace(paths)
        journal = journal.avancar(FaseJournalImportacao.LIMPEZA_CONCLUIDA)
        self.registrar(journal)
        _inject(injetar_falha, PontoFalhaImportacao.DEPOIS_LIMPEZA)
        self._store.remover()

    @staticmethod
    def _validar_workspace(paths: CaminhosImportacaoResolvidos) -> None:
        if not _path_exists(paths.workspace):
            if _path_exists(paths.staging) or _path_exists(paths.previous):
                raise _blocked("os caminhos filhos existem sem o workspace esperado")
            return
        if paths.workspace.is_symlink() or not paths.workspace.is_dir():
            raise _blocked("o workspace não é um diretório regular")
        try:
            unexpected = {
                item.name
                for item in paths.workspace.iterdir()
                if item.name not in {"staging", "previous"}
            }
        except OSError as error:
            raise _blocked("o workspace não pôde ser inspecionado") from error
        if unexpected:
            raise _blocked("o workspace contém resíduos não identificados")
        for child in (paths.staging, paths.previous):
            if _path_exists(child) and (child.is_symlink() or not child.is_dir()):
                raise _blocked("o workspace contém um caminho não regular")

    def _remover_workspace(self, paths: CaminhosImportacaoResolvidos) -> None:
        self._validar_workspace(paths)
        if not paths.workspace.exists():
            return
        _assert_tree_has_no_links(paths.workspace)
        shutil.rmtree(paths.workspace)


def fingerprint_arquivos_esperados(
    files: Iterable[tuple[str, int, str]],
) -> str:
    """Assine caminhos relativos, tamanhos e hashes sem depender de metadados do SO."""
    digest = sha256()
    normalized: list[tuple[str, int, str]] = []
    for relative, size, file_digest in files:
        path = _validated_relative_path(relative)
        if size < 0 or not _SHA256_PATTERN.fullmatch(file_digest):
            raise RecuperacaoImportacaoBloqueadaError(
                "A identidade dos arquivos preparados é inválida."
            )
        normalized.append((path.as_posix(), size, file_digest))
    for relative, size, file_digest in sorted(normalized):
        _update_tree_digest(digest, relative, size, file_digest)
    return digest.hexdigest()


def fingerprint_arvore_gerenciada(root: Path) -> str | None:
    """Assine uma árvore regular sem seguir links ou junções."""
    if not _path_exists(root):
        return None
    if root.is_symlink() or not root.is_dir():
        raise _blocked("uma árvore gerenciada não é um diretório regular")
    digest = sha256()
    _update_directory_digest(root, root, digest)
    return digest.hexdigest()


def _update_directory_digest(root: Path, directory: Path, digest: Any) -> None:
    try:
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
    except OSError as error:
        raise _blocked("uma árvore gerenciada não pôde ser inspecionada") from error
    for entry in entries:
        path = Path(entry.path)
        relative = path.relative_to(root).as_posix()
        if entry.is_symlink() or _is_junction(path):
            raise _blocked("uma árvore gerenciada contém link ou junção")
        if entry.is_dir(follow_symlinks=False):
            _update_directory_digest(root, path, digest)
            continue
        if not entry.is_file(follow_symlinks=False):
            raise _blocked("uma árvore gerenciada contém entrada não regular")
        try:
            file_digest, size = _file_digest(path)
        except OSError as error:
            raise _blocked("um arquivo gerenciado não pôde ser verificado") from error
        _update_tree_digest(digest, relative, size, file_digest)


def _assert_tree_has_no_links(root: Path) -> None:
    if fingerprint_arvore_gerenciada(root) is None:
        raise _blocked("o workspace desapareceu durante a reconciliação")


def _remove_verified_tree(path: Path, expected_digest: str | None) -> None:
    if expected_digest is None or fingerprint_arvore_gerenciada(path) != expected_digest:
        raise _blocked("uma pasta só pode ser removida depois de verificar sua identidade")
    shutil.rmtree(path)


def _remove_owned_regular_tree(path: Path) -> None:
    _assert_tree_has_no_links(path)
    shutil.rmtree(path)


def _validate_receipt(
    journal: JournalImportacaoProjeto,
    receipt: ComprovanteCommitImportacao,
) -> None:
    if (
        receipt.operacao_id != journal.operation_id
        or receipt.projeto_id != journal.project_id
        or receipt.pacote_sha256 != journal.package_sha256
        or receipt.plano_sha256 != journal.plan_sha256
        or receipt.arquivos_sha256 != journal.new_files_sha256
    ):
        raise _blocked("o recibo do banco diverge da identidade do journal")


def _parse_journal(payload: object) -> JournalImportacaoProjeto:
    if not isinstance(payload, dict) or set(payload) != _JOURNAL_FIELDS:
        raise _blocked("a estrutura do journal não corresponde ao formato suportado")
    paths_payload = payload.get("paths")
    if not isinstance(paths_payload, dict) or set(paths_payload) != _PATH_FIELDS:
        raise _blocked("a estrutura de caminhos do journal é inválida")
    try:
        journal = JournalImportacaoProjeto(
            version=_strict_int(payload["version"]),
            operation_id=UUID(_strict_string(payload["operation_id"])),
            project_id=UUID(_strict_string(payload["project_id"])),
            package_sha256=_strict_string(payload["package_sha256"]),
            plan_sha256=_strict_string(payload["plan_sha256"]),
            target_state_sha256=_strict_string(payload["target_state_sha256"]),
            new_files_sha256=_strict_string(payload["new_files_sha256"]),
            previous_files_sha256=_optional_string(payload["previous_files_sha256"]),
            previous_assets_existed=_strict_bool(payload["previous_assets_existed"]),
            phase=FaseJournalImportacao(_strict_string(payload["phase"])),
            created_at=datetime.fromisoformat(_strict_string(payload["created_at"])),
            paths=CaminhosJournalImportacao(
                project=_strict_string(paths_payload["project"]),
                workspace=_strict_string(paths_payload["workspace"]),
                staging=_strict_string(paths_payload["staging"]),
                previous=_strict_string(paths_payload["previous"]),
            ),
        )
    except (TypeError, ValueError, KeyError) as error:
        raise _blocked("os valores do journal são inválidos") from error
    _validate_journal(journal)
    return journal


def _validate_journal(journal: JournalImportacaoProjeto) -> None:
    if journal.version != JOURNAL_VERSION:
        raise _blocked("a versão do journal não é suportada")
    for value in (
        journal.package_sha256,
        journal.plan_sha256,
        journal.target_state_sha256,
        journal.new_files_sha256,
    ):
        if not _SHA256_PATTERN.fullmatch(value):
            raise _blocked("o journal contém uma identidade SHA-256 inválida")
    if journal.previous_files_sha256 is not None and not _SHA256_PATTERN.fullmatch(
        journal.previous_files_sha256
    ):
        raise _blocked("o journal contém uma identidade anterior inválida")
    if journal.previous_assets_existed != (journal.previous_files_sha256 is not None):
        raise _blocked("o journal é ambíguo sobre a pasta anterior")
    if journal.created_at.tzinfo is None or journal.created_at.utcoffset() is None:
        raise _blocked("o journal não possui horário absoluto")
    expected = JournalImportacaoProjeto.novo(
        operation_id=journal.operation_id,
        project_id=journal.project_id,
        package_sha256=journal.package_sha256,
        plan_sha256=journal.plan_sha256,
        target_state_sha256=journal.target_state_sha256,
        new_files_sha256=journal.new_files_sha256,
        previous_files_sha256=journal.previous_files_sha256,
        previous_assets_existed=journal.previous_assets_existed,
        created_at=journal.created_at,
    ).paths
    if journal.paths != expected:
        raise _blocked("os caminhos do journal não correspondem à identidade da operação")
    for value in asdict(journal.paths).values():
        _validated_relative_path(value)


def _validated_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise _blocked("o journal contém caminho relativo inválido")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _blocked("o journal contém caminho fora da raiz gerenciada")
    return path


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate journal field")
        result[key] = value
    return result


def _strict_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _strict_string(value)


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected integer")
    return value


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected boolean")
    return value


def _update_tree_digest(digest: Any, relative: str, size: int, file_digest: str) -> None:
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(size).encode("ascii"))
    digest.update(b"\0")
    digest.update(file_digest.encode("ascii"))
    digest.update(b"\0")


def _file_digest(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if checker is not None else False


def _blocked(reason: str) -> RecuperacaoImportacaoBloqueadaError:
    return RecuperacaoImportacaoBloqueadaError(
        "A recuperação automática da importação foi bloqueada porque "
        f"{reason}. Preserve project-files/.import-recovery, restaure um backup confiável "
        "ou solicite suporte antes de tentar novas alterações."
    )


def _inject(
    callback: Callable[[PontoFalhaImportacao], None] | None,
    point: PontoFalhaImportacao,
) -> None:
    if callback is not None:
        callback(point)
