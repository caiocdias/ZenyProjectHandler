"""Descoberta e provisionamento seguro dos dados locais do Tesseract."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import URLError
from urllib.request import Request, urlopen

TESSERACT_PATH_ENVIRONMENT_VARIABLE = "ZENY_TESSERACT_PATH"
TESSDATA_DIRECTORY_ENVIRONMENT_VARIABLE = "ZENY_TESSDATA_DIR"
TESSDATA_PREFIX_ENVIRONMENT_VARIABLE = "TESSDATA_PREFIX"
TESSDATA_FAST_RELEASE = "4.1.0"
TESSDATA_FAST_REVISION = "65727574dfcd264acbb0c3e07860e4e9e9b22185"
PORTUGUESE_TRAINEDDATA_SHA256 = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"
PORTUGUESE_TRAINEDDATA_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/"
    f"{TESSDATA_FAST_REVISION}/por.traineddata"
)

_DEFAULT_WINDOWS_PATHS = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
)
_PREFERRED_LANGUAGES = ("por", "eng")
_QUOTED_DIRECTORY_PATTERN = re.compile(r"[\"']([^\"']+)[\"']")
_CAPABILITY_TIMEOUT_SECONDS = 15
_DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class DiagnosticoRuntimeOcr:
    """Falha de inicialização sanitizada, acompanhada de remediação."""

    codigo: str
    mensagem: str
    remediacao: str

    @property
    def texto_ui(self) -> str:
        """Mensagem completa que pode ser mostrada sem revelar caminhos locais."""
        return f"{self.mensagem} {self.remediacao}"


@dataclass(frozen=True, slots=True)
class RuntimeTesseract:
    """Executável e diretório de dados efetivamente validados por ``--list-langs``."""

    executavel: Path | None
    diretorio_tessdata: Path | None
    idiomas_disponiveis: tuple[str, ...] = ()
    idiomas_selecionados: tuple[str, ...] = ()
    diagnostico: DiagnosticoRuntimeOcr | None = None

    @property
    def portugues_pronto(self) -> bool:
        """Indique sucesso somente quando ``por`` foi observado no subprocesso."""
        return (
            self.executavel is not None
            and self.diretorio_tessdata is not None
            and "por" in self.idiomas_disponiveis
            and "por" in self.idiomas_selecionados
            and self.diagnostico is None
        )


@dataclass(frozen=True, slots=True)
class _LanguageInspection:
    languages: frozenset[str]
    tessdata_directory: Path


def managed_tessdata_directory(
    data_directory: Path,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Retorne a pasta gravável controlada pelo app ou explicitamente pelo ambiente."""
    values = os.environ if environment is None else environment
    configured = values.get(TESSDATA_DIRECTORY_ENVIRONMENT_VARIABLE)
    selected = (
        Path(configured)
        if configured
        else data_directory / "ocr" / f"tessdata-fast-{TESSDATA_FAST_RELEASE}"
    )
    return selected.expanduser().resolve()


def inspect_tesseract_runtime(
    data_directory: Path,
    environment: Mapping[str, str] | None = None,
) -> RuntimeTesseract:
    """Descubra o Tesseract e exija português sem fazer rede nem alterar o ambiente global."""
    values = os.environ if environment is None else environment
    executable, discovery_diagnostic = _discover_executable(values)
    if executable is None:
        return RuntimeTesseract(
            executavel=None,
            diretorio_tessdata=None,
            diagnostico=discovery_diagnostic,
        )

    managed = managed_tessdata_directory(data_directory, values)
    default_inspection, default_error = _try_inspect_languages(executable, None, values)
    if default_inspection is not None and "por" in default_inspection.languages:
        return _successful_runtime(executable, default_inspection)

    managed_portuguese = managed / "por.traineddata"
    if managed_portuguese.is_file():
        try:
            digest = _file_sha256(managed_portuguese)
        except OSError:
            digest = ""
        if digest != PORTUGUESE_TRAINEDDATA_SHA256:
            return RuntimeTesseract(
                executavel=executable,
                diretorio_tessdata=(
                    default_inspection.tessdata_directory
                    if default_inspection is not None
                    else managed
                ),
                idiomas_disponiveis=_available_tuple(default_inspection),
                diagnostico=_checksum_diagnostic(),
            )
        managed_inspection, managed_error = _try_inspect_languages(executable, managed, values)
        if managed_inspection is not None and "por" in managed_inspection.languages:
            return _successful_runtime(executable, managed_inspection)
        if managed_error is not None:
            return RuntimeTesseract(
                executavel=executable,
                diretorio_tessdata=managed,
                diagnostico=managed_error,
            )

    if default_inspection is None and default_error is not None:
        return RuntimeTesseract(
            executavel=executable,
            diretorio_tessdata=None,
            diagnostico=default_error,
        )
    return RuntimeTesseract(
        executavel=executable,
        diretorio_tessdata=(
            default_inspection.tessdata_directory if default_inspection is not None else None
        ),
        idiomas_disponiveis=_available_tuple(default_inspection),
        diagnostico=DiagnosticoRuntimeOcr(
            codigo="ocr.portugues_ausente",
            mensagem=(
                "O Tesseract foi encontrado, mas tesseract --list-langs não confirmou o idioma "
                "por; "
                "o OCR em português está desativado."
            ),
            remediacao=_provisioning_remediation(),
        ),
    )


def provision_portuguese_language(
    data_directory: Path,
    environment: Mapping[str, str] | None = None,
) -> RuntimeTesseract:
    """Provisione o artefato pinado e valide o resultado pelo próprio Tesseract."""
    values = os.environ if environment is None else environment
    current = inspect_tesseract_runtime(data_directory, values)
    if current.portugues_pronto or current.executavel is None:
        return current

    managed = managed_tessdata_directory(data_directory, values)
    try:
        managed.mkdir(parents=True, exist_ok=True)
        if not managed.is_dir():
            raise OSError("managed tessdata is not a directory")
    except OSError:
        return _provisioning_failure(
            current,
            managed,
            "ocr.pasta_tessdata_indisponivel",
            "A pasta gravável de dados do OCR não pôde ser preparada.",
        )

    english_copy_error = _copy_installed_english(current, managed)
    if english_copy_error is not None:
        return _provisioning_failure(
            current,
            managed,
            "ocr.copia_ingles_falhou",
            "Os dados ingleses instalados não puderam ser copiados para a pasta do aplicativo.",
        )

    target = managed / "por.traineddata"
    if not _matches_portuguese_checksum(target):
        try:
            download_error = _download_verified_portuguese(target)
        except OSError:
            return _provisioning_failure(
                current,
                managed,
                "ocr.gravacao_portugues_falhou",
                "O por.traineddata validado não pôde ser gravado na pasta do aplicativo.",
            )
        if download_error is not None:
            return _provisioning_failure(
                current,
                managed,
                download_error.codigo,
                download_error.mensagem,
                remediation=download_error.remediacao,
            )

    validated = inspect_tesseract_runtime(data_directory, values)
    if not validated.portugues_pronto:
        return _provisioning_failure(
            validated,
            managed,
            "ocr.validacao_portugues_falhou",
            "O artefato foi gravado, mas tesseract --list-langs não confirmou o idioma por.",
        )
    return validated


def parse_available_languages(output: str) -> frozenset[str]:
    """Extraia os identificadores retornados por ``tesseract --list-langs``."""
    languages = frozenset(
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.strip().lower().startswith("list of available languages")
    )
    if not languages:
        raise ValueError("Nenhum idioma disponível no Tesseract")
    return languages


def select_ocr_languages(
    requested: tuple[str, ...] | None,
    available: frozenset[str],
) -> tuple[str, ...]:
    """Selecione ``por+eng`` nessa ordem quando ambos estiverem disponíveis."""
    if requested is not None:
        if any(language not in available for language in requested):
            raise ValueError("Idioma solicitado não está disponível")
        return requested
    selected = tuple(language for language in _PREFERRED_LANGUAGES if language in available)
    if not selected:
        raise ValueError("Nenhum idioma preferencial está disponível")
    return selected


def tesseract_subprocess_environment(
    tessdata_directory: Path | None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Crie um ambiente filho; nunca publique ``TESSDATA_PREFIX`` no processo do app."""
    values = os.environ if environment is None else environment
    child = dict(values)
    if tessdata_directory is not None:
        child[TESSDATA_PREFIX_ENVIRONMENT_VARIABLE] = str(tessdata_directory)
    return child


def tessdata_directory_from_language_output(
    output: str,
    *,
    configured: Path | None,
    executable: Path,
) -> Path:
    """Localize o diretório efetivo anunciado pelo Tesseract."""
    if configured is not None:
        return configured.resolve(strict=True)
    for line in output.splitlines():
        if not line.strip().lower().startswith("list of available languages"):
            continue
        if match := _QUOTED_DIRECTORY_PATTERN.search(line):
            candidate = Path(match.group(1)).expanduser()
            if candidate.is_dir():
                return candidate.resolve()
    fallback = executable.parent / "tessdata"
    if fallback.is_dir():
        return fallback.resolve()
    raise ValueError("Diretório tessdata não identificado")


def _discover_executable(
    environment: Mapping[str, str],
) -> tuple[Path | None, DiagnosticoRuntimeOcr | None]:
    configured = environment.get(TESSERACT_PATH_ENVIRONMENT_VARIABLE)
    if configured:
        selected = Path(configured).expanduser()
        if selected.is_file():
            return selected.resolve(), None
        return None, DiagnosticoRuntimeOcr(
            codigo="ocr.caminho_tesseract_invalido",
            mensagem="ZENY_TESSERACT_PATH não aponta para um executável existente.",
            remediacao=_executable_remediation(),
        )

    found = shutil.which("tesseract", path=environment.get("PATH"))
    candidates = (*((Path(found),) if found else ()), *_DEFAULT_WINDOWS_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(), None
    return None, DiagnosticoRuntimeOcr(
        codigo="ocr.tesseract_ausente",
        mensagem="O executável Tesseract não foi encontrado; o OCR em português está desativado.",
        remediacao=_executable_remediation(),
    )


def _try_inspect_languages(
    executable: Path,
    tessdata_directory: Path | None,
    environment: Mapping[str, str],
) -> tuple[_LanguageInspection | None, DiagnosticoRuntimeOcr | None]:
    try:
        completed = subprocess.run(
            (str(executable), "--list-langs"),
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_CAPABILITY_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=tesseract_subprocess_environment(tessdata_directory, environment),
        )
        output = str(completed.stdout or "")
        languages = parse_available_languages(output)
        directory = tessdata_directory_from_language_output(
            output,
            configured=tessdata_directory,
            executable=executable,
        )
        return _LanguageInspection(languages, directory), None
    except subprocess.TimeoutExpired:
        diagnostic = DiagnosticoRuntimeOcr(
            codigo="ocr.consulta_idiomas_timeout",
            mensagem=(
                "tesseract --list-langs excedeu o tempo limite; o OCR em português está desativado."
            ),
            remediacao=_executable_remediation(),
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        diagnostic = DiagnosticoRuntimeOcr(
            codigo="ocr.consulta_idiomas_falhou",
            mensagem=(
                "tesseract --list-langs não pôde validar os idiomas instalados; "
                "o OCR em português está desativado."
            ),
            remediacao=_executable_remediation(),
        )
    return None, diagnostic


def _successful_runtime(executable: Path, inspection: _LanguageInspection) -> RuntimeTesseract:
    return RuntimeTesseract(
        executavel=executable,
        diretorio_tessdata=inspection.tessdata_directory,
        idiomas_disponiveis=tuple(sorted(inspection.languages)),
        idiomas_selecionados=select_ocr_languages(None, inspection.languages),
    )


def _available_tuple(inspection: _LanguageInspection | None) -> tuple[str, ...]:
    return tuple(sorted(inspection.languages)) if inspection is not None else ()


def _copy_installed_english(current: RuntimeTesseract, managed: Path) -> OSError | None:
    if "eng" not in current.idiomas_disponiveis or current.diretorio_tessdata is None:
        return None
    source = current.diretorio_tessdata / "eng.traineddata"
    target = managed / "eng.traineddata"
    try:
        if source.resolve(strict=True) == target.resolve(strict=False):
            return None
        if target.is_file() and _file_sha256(target) == _file_sha256(source):
            return None
        _atomic_copy(source, target)
    except OSError as error:
        return error
    return None


def _atomic_copy(source: Path, target: Path) -> None:
    with NamedTemporaryFile(
        mode="wb",
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        shutil.copyfile(source, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def _download_verified_portuguese(target: Path) -> DiagnosticoRuntimeOcr | None:
    with NamedTemporaryFile(
        mode="wb",
        prefix=".por.traineddata.",
        suffix=".download",
        dir=target.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        try:
            _download_to(PORTUGUESE_TRAINEDDATA_URL, temporary_path)
        except (OSError, URLError):
            return DiagnosticoRuntimeOcr(
                codigo="ocr.download_portugues_falhou",
                mensagem=(
                    "Não foi possível baixar o por.traineddata oficial; "
                    "o OCR em português não está pronto."
                ),
                remediacao=_offline_remediation(),
            )
        if _file_sha256(temporary_path) != PORTUGUESE_TRAINEDDATA_SHA256:
            return _checksum_diagnostic()
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return None


def _download_to(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "ZenyProjectHandler/0.1 tessdata provisioner"})
    with (
        urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response,
        destination.open("wb") as stream,
    ):
        shutil.copyfileobj(response, stream)


def _matches_portuguese_checksum(path: Path) -> bool:
    try:
        return path.is_file() and _file_sha256(path) == PORTUGUESE_TRAINEDDATA_SHA256
    except OSError:
        return False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _provisioning_failure(
    current: RuntimeTesseract,
    managed: Path,
    code: str,
    message: str,
    *,
    remediation: str | None = None,
) -> RuntimeTesseract:
    return RuntimeTesseract(
        executavel=current.executavel,
        diretorio_tessdata=managed,
        idiomas_disponiveis=current.idiomas_disponiveis,
        diagnostico=DiagnosticoRuntimeOcr(
            codigo=code,
            mensagem=f"{message} O OCR em português não foi declarado pronto.",
            remediacao=remediation or _provisioning_remediation(),
        ),
    )


def _checksum_diagnostic() -> DiagnosticoRuntimeOcr:
    return DiagnosticoRuntimeOcr(
        codigo="ocr.checksum_portugues_invalido",
        mensagem=(
            "O SHA-256 de por.traineddata não corresponde à revisão oficial fixada; "
            "o arquivo foi rejeitado e o OCR em português está desativado."
        ),
        remediacao=(
            "Remova somente o por.traineddata inválido da pasta de OCR do aplicativo e execute "
            "setup.bat novamente; o hash esperado está documentado no README."
        ),
    )


def _executable_remediation() -> str:
    return (
        "Execute setup.bat novamente. Se necessário, instale Tesseract 5 com "
        "'winget install --id UB-Mannheim.TesseractOCR --exact' ou defina "
        "ZENY_TESSERACT_PATH para uma instalação autorizada."
    )


def _provisioning_remediation() -> str:
    return (
        "Execute setup.bat com acesso à rede para provisionar e validar por.traineddata na pasta "
        "gravável do aplicativo; use ZENY_TESSDATA_DIR para escolher outra pasta gravável."
    )


def _offline_remediation() -> str:
    return (
        f"Conecte-se à rede e execute setup.bat novamente ou baixe por.traineddata da revisão "
        f"{TESSDATA_FAST_REVISION}, confira o SHA-256 {PORTUGUESE_TRAINEDDATA_SHA256} e coloque-o "
        "na pasta definida por ZENY_TESSDATA_DIR antes de repetir o setup."
    )
