# E03 — Observações de símbolos e registro de métodos

Contrato interno aditivo do [roadmap](roadmap-analise-simbologia.md). A etapa
preserva o detector vetorial legado e seu score bruto `Decimal("0.88")`.
Não introduz fusão, catálogo, promoção de ativos ou alteração do DTO público.

## Fronteiras e decisões

As entidades novas ficam em `domain/symbols.py`, separadas das propostas
patrimoniais de `domain/analysis.py`. Classes e subtipos são identificadores
abertos: estai, convenção informativa e símbolo desconhecido podem ser
observados sem criar `Cabo`, `Equipamento` ou uma categoria arbitrária.
Classe desconhecida permanece explícita; não é ausência de observação.

Uma observação identifica a saída de um método sobre uma entrada/configuração.
Sua identidade determinística não identifica um ativo físico. Hipóteses apenas
registram vínculos explícitos; a associação automática fica para E12. Não há
quórum, interseção obrigatória ou operação que remova um candidato pelo silêncio
de outro método.

Cobertura registra documento, hash, página, camada, região, classes avaliadas
e estado. Fora de domínio, indisponibilidade, abstenção, falha e não detecção
têm significados distintos. Nenhum desses estados demonstra ausência física.
Motivos de abstenção e falha pertencem à cobertura, sem inventar candidatos.
Regiões de cobertura usam o envelope retangular dos pontos informados.
`ResultadoMetodoSimbolos.completo` indica término das coberturas declaradas
(concluído, não detecção ou fora de domínio); não mede cobertura do inventário,
acurácia ou presença/ausência física. Falha parcial conserva observações e
mantém `completo=False`. Cancelamento/orquestração ficam para E15.

Assinaturas conservam versão, família algorítmica, capacidades, configuração,
referência, modelo/template e fontes compartilhadas. Variantes de DPI ou
threshold são relacionadas pela família/origem. Fontes declaradas diferentes
não provam independência estatística; concordância não vira probabilidade.

## Geometria e compatibilidade

A camada de análise (`base` ou anotação) é distinta da camada gráfica OCG
de cada primitiva. O legado observa a base; nomes OCG são preservados quando
disponíveis, sem atribuir uma camada única a primitives de camadas distintas.

Geometria original e normalizada são guardadas separadamente, com sistema de
coordenadas e transformação inversa. A normalização legada pode recortar
coordenadas fora da página: isso deve ser sinalizado, nunca apresentado como
transformação sem perda. Pontos e polilinhas degeneradas do baseline também
permanecem intactos; corrigir suas caixas pertence à E04.

O adapter é uma entrada interna opt-in, sem alteração do pipeline público.
O codec JSON existente registra os tipos novos explicitamente e conserva
Decimal, enums e tuplas. Não há migração de banco ou mudança do cache legado.
A integração persistente com jobs/composição fica para as etapas posteriores.

O corte `confianca_minima` em `category_analyzers.py` foi inspecionado: novos
scores brutos não são enviados a ele nesta etapa. Calibração é responsabilidade
de E12; adaptação do consumidor, de E13.

## Validação e evidências

Entrada por página, em `adapters/analysis/legacy_symbols.py`:

```python
resultado = observar_simbolos_legados(
    page,
    documento_id=documento_id,
    documento_sha256=sha256_da_fonte,
    pagina_numero=numero_base_1,
)
payload = dumps_domain(resultado)
restaurado = loads_domain(payload, ResultadoMetodoSimbolos)
```

`perfil_simbolos_legados()` fornece as capacidades fixas efetivamente usadas.
O registro `RegistroMetodosSimbolos` consulta métodos por assinatura e rejeita
duplicatas da mesma configuração. `MetodoSimbolosPort` estabelece a fronteira
documental para futuros adapters; o helper legado por página não implementa
orquestração de jobs.

| Tipo interno | Responsabilidade |
|---|---|
| `FonteObservacaoSimbolo` | Documento, SHA-256, página, camada de análise e objeto PDF. |
| `GeometriaObservacaoSimbolo` | Pontos originais/normalizados, tipo, inversa e limitação de normalização. |
| `PrimitivaObservadaSimbolo` | Índice da extração, camada OCG e pontos originais. |
| `AlternativaClasseSimbolo` | Classe/subtipo abertos e score bruto opcional. |
| `PerfilMetodoSimbolos` | Capacidades, versão, referências, configuração e fontes correlacionadas. |
| `CoberturaMetodoSimbolos` | Região/classe avaliada, estado e motivo. |
| `ObservacaoSimbolo` | Evidência independente, alternativas e identidade determinística. |
| `ResultadoMetodoSimbolos` | Perfil, coberturas e observações preservadas, inclusive em falha parcial. |
| `HipoteseSimbolo` | Vínculo explícito entre IDs, sem inferir identidade física. |

Os comandos, checkpoints, delegações e resultados finais estão no handoff E03
do roadmap. Os artefatos privados de integração e inspeção ficam somente em
`tmp/e03-simbologia/`. O baseline público E02 e a reserva sintética permanecem
preservados. Os PDFs de exemplo são dados de desenvolvimento, sem alegação
de teste cego ou homologação de campo.
