"""Credenciais efêmeras, indexadas pela identidade verificável da origem PDF."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock

from zeny_project_handler.domain.documents import SHA256_PATTERN
from zeny_project_handler.ports.pdf import InspecaoPdf, ReferenciaFontePdf

_READ_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class IdentidadeCredencialPdf:
    """Identidade de conteúdo e arquivo que invalida senhas após qualquer troca."""

    sha256: str
    tamanho_bytes: int
    modificado_em_ns: int

    def __post_init__(self) -> None:
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("A identidade da credencial requer um SHA-256 válido")
        if self.tamanho_bytes < 1:
            raise ValueError("A identidade da credencial requer tamanho positivo")
        if self.modificado_em_ns < 0:
            raise ValueError("A identidade da credencial requer data de modificação válida")

    @classmethod
    def da_inspecao(cls, inspecao: InspecaoPdf) -> IdentidadeCredencialPdf:
        return cls(
            sha256=inspecao.documento.sha256,
            tamanho_bytes=inspecao.tamanho_bytes,
            modificado_em_ns=inspecao.modificado_em_ns,
        )

    @classmethod
    def da_fonte(cls, fonte: ReferenciaFontePdf) -> IdentidadeCredencialPdf:
        return cls(
            sha256=fonte.sha256,
            tamanho_bytes=fonte.tamanho_bytes,
            modificado_em_ns=fonte.modificado_em_ns,
        )

    def ainda_descreve(self, caminho: Path) -> bool:
        """Cheque metadados baratos antes de reutilizar uma senha da sessão."""
        try:
            status = caminho.expanduser().resolve(strict=True).stat()
        except OSError:
            return False
        return status.st_size == self.tamanho_bytes and status.st_mtime_ns == self.modificado_em_ns


class ProvedorCredenciaisPdfMemoria:
    """Guarde senhas apenas no processo atual, sem serialização ou fallback persistente."""

    def __init__(self) -> None:
        self._senhas: dict[IdentidadeCredencialPdf, str] = {}
        self._lock = RLock()

    def obter(self, identidade: IdentidadeCredencialPdf) -> str | None:
        with self._lock:
            return self._senhas.get(identidade)

    def guardar(self, identidade: IdentidadeCredencialPdf, senha: str) -> None:
        if not senha:
            raise ValueError("Uma senha PDF vazia não pode ser mantida na sessão")
        with self._lock:
            self._senhas[identidade] = senha

    def descartar(self, identidade: IdentidadeCredencialPdf) -> None:
        with self._lock:
            self._senhas.pop(identidade, None)

    def reter(self, identidades: set[IdentidadeCredencialPdf]) -> None:
        """Descarte credenciais de documentos que deixaram a sessão visual ativa."""
        with self._lock:
            for identidade in self._senhas.keys() - identidades:
                del self._senhas[identidade]

    def limpar(self) -> None:
        with self._lock:
            self._senhas.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._senhas)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(quantidade={len(self)})"


def identificar_origem_pdf(caminho: Path) -> IdentidadeCredencialPdf:
    """Calcule uma chave sem abrir o PDF nem depender de sua senha."""
    try:
        origem = caminho.expanduser().resolve(strict=True)
        inicial = origem.stat()
        digest = sha256()
        with origem.open("rb") as stream:
            while trecho := stream.read(_READ_CHUNK_SIZE):
                digest.update(trecho)
        final = origem.stat()
    except OSError as error:
        raise ValueError("A origem PDF não está disponível para validar a identidade") from error
    if (
        inicial.st_size != final.st_size
        or inicial.st_mtime_ns != final.st_mtime_ns
        or inicial.st_ctime_ns != final.st_ctime_ns
    ):
        raise ValueError("A origem PDF mudou durante a validação da identidade")
    return IdentidadeCredencialPdf(
        sha256=digest.hexdigest(),
        tamanho_bytes=final.st_size,
        modificado_em_ns=final.st_mtime_ns,
    )
