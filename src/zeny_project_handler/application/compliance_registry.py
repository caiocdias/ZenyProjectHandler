"""Caso de uso do registro configurável e imutável de regras de conformidade."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.domain.compliance import (
    CondicaoConformidade,
    DisponibilidadeProvedorFato,
    NumeroRegraConformidade,
    OperadorCondicao,
    RegistroRegrasConformidade,
    RegraConformidade,
    RevisaoRegistroConformidade,
)
from zeny_project_handler.domain.compliance_facts import (
    fato_conformidade_por_chave,
    validar_semantica_registro,
)
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .errors import RegistroConformidadeError

CATALOGO_REGRAS_FILE_NAME = "catalogo-regras-conformidade.md"
_LEGACY_BUNDLED_VERSION = "cemig-normas-distribuicao-2025.3"
_SAFE_BUNDLED_VERSION = "cemig-normas-distribuicao-2025.4"
_SPAN_RULE_ID = "nd31.vao.urbano-compacto-isolado"
_SPAN_SAFEGUARD_FACT = "vao.aplicabilidade_excecao_45_60_resolvida"


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoImportacaoRegras:
    registro: RegistroRegrasConformidade
    avisos: tuple[str, ...]
    novos_ids: tuple[str, ...]
    substituidos_ids: tuple[str, ...]
    inalterados_ids: tuple[str, ...]
    omitidos_preservados_ids: tuple[str, ...]

    @property
    def total_importado(self) -> int:
        return len(self.registro.regras)

    def texto_confirmacao(self) -> str:
        lines = [
            f"Versão informada: {self.registro.versao}",
            f"Regras no arquivo: {self.total_importado}",
            f"Novas: {len(self.novos_ids)}",
            f"IDs existentes substituídos: {len(self.substituidos_ids)}",
            f"Inalteradas: {len(self.inalterados_ids)}",
            f"IDs atuais omitidos e preservados: {len(self.omitidos_preservados_ids)}",
        ]
        if self.avisos:
            lines.extend(("", "Avisos:", *(f"• {item}" for item in self.avisos)))
        lines.extend(("", "Confirmar a criação de uma nova revisão ativa?"))
        return "\n".join(lines)


class ServicoRegistroRegrasConformidade:
    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        diretorio_dados: Path,
        relogio: Callable[[], datetime] | None = None,
        gerador_id: Callable[[], UUID] | None = None,
        seed: RegistroRegrasConformidade | None = None,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._data_directory = diretorio_dados.expanduser().resolve()
        self._clock = relogio or (lambda: datetime.now(UTC))
        self._id_generator = gerador_id or uuid4
        if seed is not None:
            validar_semantica_registro(seed)
        self._seed = seed

    @property
    def caminho_catalogo(self) -> Path:
        return self._data_directory / CATALOGO_REGRAS_FILE_NAME

    def inicializar(
        self,
        seed: RegistroRegrasConformidade,
    ) -> RevisaoRegistroConformidade:
        validar_semantica_registro(seed)
        self._seed = seed
        with self._unit_of_work() as work:
            current = work.registros_conformidade.obter_ativa()
        if current is None:
            return self._persistir(seed)
        migrated_registry = _migrate_legacy_bundled_span_rule(current.registro, seed)
        if migrated_registry is not None:
            return self._persistir(migrated_registry)
        if not self.caminho_catalogo.is_file():
            self._regenerar_catalogo_atual()
        return current

    def obter_revisao_ativa(self) -> RevisaoRegistroConformidade:
        revision = self.obter_revisao_ativa_opcional()
        if revision is None:
            raise RegistroConformidadeError("Registro de regras ainda não foi inicializado")
        return revision

    def obter_revisao_ativa_opcional(self) -> RevisaoRegistroConformidade | None:
        with self._unit_of_work() as work:
            return work.registros_conformidade.obter_ativa()

    def reconciliar_apos_restauracao(
        self,
        registro_preservado: RegistroRegrasConformidade | None,
    ) -> RevisaoRegistroConformidade | None:
        """Preserve IDs locais ausentes sem sobrescrever o conteúdo restaurado."""
        if registro_preservado is not None:
            validar_semantica_registro(registro_preservado)
        restored = self.obter_revisao_ativa_opcional()
        if restored is None:
            if registro_preservado is None:
                return None
            return self._persistir(registro_preservado)
        restored_registry = restored.registro
        if self._seed is not None:
            migrated = _migrate_legacy_bundled_span_rule(restored_registry, self._seed)
            if migrated is not None:
                restored_registry = migrated
        preserved_rules = registro_preservado.regras if registro_preservado is not None else ()
        restored_ids = {item.id for item in restored_registry.regras}
        missing = tuple(item for item in preserved_rules if item.id not in restored_ids)
        if not missing and restored_registry is restored.registro:
            self.republicar_catalogo_ativo()
            return restored
        reconciled = replace(
            restored_registry,
            regras=(*restored_registry.regras, *missing),
        )
        return self._persistir(reconciled)

    def republicar_catalogo_ativo(self) -> None:
        """Sincronize a projeção Markdown com a revisão ativa persistida."""
        self._regenerar_catalogo_atual()

    def listar_historico(self) -> tuple[RevisaoRegistroConformidade, ...]:
        with self._unit_of_work() as work:
            return work.registros_conformidade.listar_revisoes()

    def listar_numeros(self) -> tuple[NumeroRegraConformidade, ...]:
        with self._unit_of_work() as work:
            return work.registros_conformidade.listar_numeros()

    def preparar_importacao(
        self,
        registro: RegistroRegrasConformidade,
        *,
        avisos: tuple[str, ...] | None = None,
    ) -> ResumoImportacaoRegras:
        semantic_warnings = validar_semantica_registro(registro)
        current = self.obter_revisao_ativa().registro
        current_by_id = {item.id: item for item in current.regras}
        imported_ids = {item.id for item in registro.regras}
        new: list[str] = []
        replaced_ids: list[str] = []
        unchanged: list[str] = []
        for rule in registro.regras:
            existing = current_by_id.get(rule.id)
            if existing is None:
                new.append(rule.id)
            elif existing == rule:
                unchanged.append(rule.id)
            else:
                replaced_ids.append(rule.id)
        return ResumoImportacaoRegras(
            registro=registro,
            avisos=semantic_warnings if avisos is None else avisos,
            novos_ids=tuple(new),
            substituidos_ids=tuple(replaced_ids),
            inalterados_ids=tuple(unchanged),
            omitidos_preservados_ids=tuple(
                item.id for item in current.regras if item.id not in imported_ids
            ),
        )

    def importar(self, resumo: ResumoImportacaoRegras) -> RevisaoRegistroConformidade:
        validar_semantica_registro(resumo.registro)
        current = self.obter_revisao_ativa().registro
        imported_by_id = {item.id: item for item in resumo.registro.regras}
        merged = tuple(imported_by_id.pop(item.id, item) for item in current.regras)
        merged = (*merged, *(item for item in resumo.registro.regras if item.id in imported_by_id))
        registry = RegistroRegrasConformidade(
            id=resumo.registro.id,
            versao=resumo.registro.versao,
            versao_schema=resumo.registro.versao_schema,
            regras=merged,
        )
        return self._persistir(registry)

    def exportar(self, destination: Path) -> Path:
        registry = self.obter_revisao_ativa().registro
        content = json.dumps(registry.para_dict(), ensure_ascii=False, indent=2) + "\n"
        return _write_atomic_text(destination, content)

    def _persistir(self, registry: RegistroRegrasConformidade) -> RevisaoRegistroConformidade:
        validar_semantica_registro(registry)
        now = self._clock()
        revision = RevisaoRegistroConformidade(
            id=self._id_generator(),
            registro=registry,
            assinatura=registry.assinatura(),
            json_canonico=registry.json_canonico(),
            criada_em=now,
            ativa=True,
        )
        try:
            with self._unit_of_work() as work:
                numbers = work.registros_conformidade.reservar_numeros(
                    tuple(item.id for item in registry.regras),
                    atribuido_em=now,
                )
                persisted = work.registros_conformidade.salvar_ativa(revision)
                history = work.registros_conformidade.listar_revisoes()
                _write_atomic_text(
                    self.caminho_catalogo,
                    renderizar_catalogo_markdown(persisted, numbers, history),
                )
                work.commit()
                return persisted
        except OSError as error:
            raise RegistroConformidadeError(
                "Não foi possível publicar o catálogo local de regras"
            ) from error

    def _regenerar_catalogo_atual(self) -> None:
        try:
            with self._unit_of_work() as work:
                active = work.registros_conformidade.obter_ativa()
                if active is None:
                    return
                content = renderizar_catalogo_markdown(
                    active,
                    work.registros_conformidade.listar_numeros(),
                    work.registros_conformidade.listar_revisoes(),
                )
            _write_atomic_text(self.caminho_catalogo, content)
        except OSError as error:
            raise RegistroConformidadeError(
                "Não foi possível regenerar o catálogo local de regras"
            ) from error


def _migrate_legacy_bundled_span_rule(
    current: RegistroRegrasConformidade,
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade | None:
    """Upgrade only an unchanged bundled Rule 6, preserving custom rules and edits."""
    if seed.versao != _SAFE_BUNDLED_VERSION:
        return None
    replacement = next((item for item in seed.regras if item.id == _SPAN_RULE_ID), None)
    if replacement is None:
        return None
    safeguards = tuple(
        item for item in replacement.aplicabilidade if item.chave_fato == _SPAN_SAFEGUARD_FACT
    )
    if len(safeguards) != 1:
        return None
    legacy_rule = replace(
        replacement,
        aplicabilidade=tuple(
            item for item in replacement.aplicabilidade if item.chave_fato != _SPAN_SAFEGUARD_FACT
        ),
    )
    existing = next((item for item in current.regras if item.id == _SPAN_RULE_ID), None)
    if existing != legacy_rule:
        return None
    version = (
        seed.versao
        if current.versao == _LEGACY_BUNDLED_VERSION
        else f"{current.versao}+seguranca-vao-2025.4"
    )
    return replace(
        current,
        versao=version,
        regras=tuple(replacement if item.id == _SPAN_RULE_ID else item for item in current.regras),
    )


def renderizar_catalogo_markdown(
    active: RevisaoRegistroConformidade,
    numbers: tuple[NumeroRegraConformidade, ...],
    history: tuple[RevisaoRegistroConformidade, ...],
) -> str:
    current = {item.id: item for item in active.registro.regras}
    last_known: dict[str, RegraConformidade] = {}
    for revision in history:
        for rule in revision.registro.regras:
            last_known[rule.id] = rule
    last_known.update(current)
    active_count = sum(item.ativa for item in current.values())
    lines = [
        "# Catálogo local de regras de conformidade",
        "",
        f"- Revisão ativa: `{active.id}`",
        f"- Versão informada: `{_markdown(active.registro.versao)}`",
        f"- Assinatura SHA-256: `{active.assinatura}`",
        f"- Gerada em: `{active.criada_em.isoformat()}`",
        f"- Regras ativas: {active_count}",
        f"- Regras inativas: {len(current) - active_count}",
        "",
        "Os números são permanentes por ID técnico e nunca são reutilizados. Importações "
        "que omitam IDs da revisão ativa preservam essas regras.",
        "",
        "## Resumo",
        "",
        "| Número | ID técnico | Título | Estado |",
        "|---|---|---|---|",
    ]
    for number in numbers:
        rule = last_known[number.regra_id]
        lines.append(
            f"| Regra {number.numero} | `{_markdown(rule.id)}` | "
            f"{_markdown(rule.titulo)} | {_rule_state(current.get(rule.id))} |"
        )
    lines.extend(("", "## Processo de análise de cada regra", ""))
    for number in numbers:
        rule = last_known[number.regra_id]
        lines.extend(_render_rule(number.numero, rule, current.get(rule.id)))
    return "\n".join(lines).rstrip() + "\n"


def _render_rule(
    number: int,
    historical: RegraConformidade,
    current: RegraConformidade | None,
) -> list[str]:
    rule = current or historical
    facts = sorted(
        {item.chave_fato for item in (*rule.aplicabilidade, *rule.excecoes, *rule.requisitos)}
    )
    planned = [
        item
        for key in facts
        if (item := fato_conformidade_por_chave(key)) is not None
        and item.disponibilidade is DisponibilidadeProvedorFato.PLANEJADO
    ]
    availability = (
        "AGUARDA_FATO (" + ", ".join(item.chave for item in planned) + ")"
        if planned
        else "OPERACIONAL"
    )
    when = _conditions_text(rule.aplicabilidade, empty="aplica-se sem condição adicional")
    unless = _conditions_text(rule.excecoes, empty="nenhuma exceção declarada")
    must = _conditions_text(rule.requisitos, empty="nenhum requisito")
    source = f"{rule.fonte.documento}, revisão {rule.fonte.revisao}, item {rule.fonte.item}"
    if rule.fonte.pagina is not None:
        source += f", página {rule.fonte.pagina}"
    if rule.fonte.url:
        source += f", URL: {_markdown(rule.fonte.url)}"
    return [
        f"### Regra {number} - {_markdown(rule.titulo)}",
        "",
        f"- **ID técnico:** `{_markdown(rule.id)}`",
        f"- **Estado:** {_rule_state(current)}",
        f"- **Automação:** {availability}",
        f"- **Descrição:** {_markdown(rule.descricao)}",
        f"- **Processo de análise:** a Regra {number} consiste em avaliar `{_markdown(rule.id)}` "
        f"no escopo {rule.escopo.value}. Primeiro, o analisador verifica when: {when}. Depois, "
        f"confirma unless: {unless}. Se a regra continuar aplicável, verifica must: {must}.",
        f"- **Fatos observados:** {', '.join(f'`{_markdown(item)}`' for item in facts)}.",
        "- **Resultado:** requisito conhecido e atendido resulta em CONFORME; contradição resulta "
        "em possível DIVERGÊNCIA; fato necessário ausente resulta em NÃO AVALIÁVEL.",
        f"- **Fonte registrada:** {_markdown(source)}.",
        "",
    ]


def _conditions_text(
    conditions: tuple[CondicaoConformidade, ...],
    *,
    empty: str,
) -> str:
    return "; ".join(_condition_text(item) for item in conditions) if conditions else empty


def _condition_text(condition: CondicaoConformidade) -> str:
    operator = {
        OperadorCondicao.EXISTE: "deve existir",
        OperadorCondicao.AUSENTE: "deve estar ausente",
        OperadorCondicao.IGUAL: "deve ser igual a",
        OperadorCondicao.DIFERENTE: "deve ser diferente de",
        OperadorCondicao.MENOR: "deve ser menor que",
        OperadorCondicao.MENOR_OU_IGUAL: "deve ser menor ou igual a",
        OperadorCondicao.MAIOR: "deve ser maior que",
        OperadorCondicao.MAIOR_OU_IGUAL: "deve ser maior ou igual a",
        OperadorCondicao.EM: "deve pertencer a",
        OperadorCondicao.NAO_EM: "não deve pertencer a",
        OperadorCondicao.CONTEM: "deve conter",
    }[condition.operador]
    values = ", ".join(_markdown(str(item)) for item in condition.valores_esperados)
    suffix = f" {values}" if values else ""
    return f"`{_markdown(condition.chave_fato)}` {operator}{suffix}"


def _rule_state(rule: RegraConformidade | None) -> str:
    if rule is None:
        return "AUSENTE EM REVISÃO LEGADA"
    return "ATIVA" if rule.ativa else "INATIVA"


def _markdown(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _write_atomic_text(destination: Path, content: str) -> Path:
    target = destination.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with sibling_temporary_file(target) as temporary:
        with temporary.open("wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    return target
