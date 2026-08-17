"""Primitivas comuns dos DTOs de transporte."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel

DecimalString = Annotated[
    str,
    Field(
        pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
        description="Número decimal codificado como texto para preservar precisão.",
    ),
]
NonEmptyString = Annotated[str, Field(min_length=1, max_length=500)]
FileName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        pattern=r"^[^/\\\x00]+$",
        description="Nome de exibição saneado, sem componentes de caminho.",
    ),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
UtcDateTime = AwareDatetime


class ContractModel(BaseModel):
    """Base estrita, imutável e sem comportamento de negócio."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )


class ContractRootModel(RootModel[UUID]):
    """Base dos identificadores UUID semanticamente distintos."""

    model_config = ConfigDict(frozen=True)


class CorrelationId(ContractRootModel):
    pass


class ProjectId(ContractRootModel):
    pass


class DocumentId(ContractRootModel):
    pass


class PageId(ContractRootModel):
    pass


class UploadId(ContractRootModel):
    pass


class ViewerSessionId(ContractRootModel):
    pass


class JobId(ContractRootModel):
    pass


class ReviewSessionId(ContractRootModel):
    pass


class ProposalId(ContractRootModel):
    pass


class ElementId(ContractRootModel):
    pass


class RelationId(ContractRootModel):
    pass


class RegionId(ContractRootModel):
    pass


class EvidenceId(ContractRootModel):
    pass


class ComplianceExecutionId(ContractRootModel):
    pass


class FindingId(ContractRootModel):
    pass


class CalloutId(ContractRootModel):
    pass


class RuleImportPreflightId(ContractRootModel):
    pass


class ProjectImportPreflightId(ContractRootModel):
    pass


class BackupPreflightId(ContractRootModel):
    pass


class BackupRestorePreflightId(ContractRootModel):
    pass


class DownloadId(ContractRootModel):
    pass


class PhotoId(ContractRootModel):
    pass
