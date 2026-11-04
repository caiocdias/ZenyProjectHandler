# Task 4 testador: VERMELHO

Arquivo novo: tests/unit/test_drawing_model_cache_adversarial.py (99 testes; 88 verdes, 11 vermelhos por bugs de producao).
Suite inteira: 11 failed, 4085 passed (409s). ruff check/format, mypy (447 arquivos) e complexity gate limpos.

Cobertura: ida e volta de modelo sintetico completo (Decimal 0.10/1E+3, bool/None, sinais duplicados, subcaminhos aninhados e vazios, arcos, circulos, de_anotacao, floats); chave (sha, versao, leitor); 40 corrupcoes estruturais; conteudos degenerados, truncado, nao UTF-8; extras ignorados; diretorio inexistente/arquivo no lugar; chaves invalidas; atomicidade (falha na troca preserva entrada, falha ao escrever temporario, sem .tmp); concorrencia; obter_modelo_desenho (espia de extracao: 1 extracao, versao do modelo/leitor reextraem, copia do PDF reaproveita, corrompido regrava, falha de gravacao real, qualquer *_falhou em qualquer pagina nao grava e reextrai depois).

## Bugs (vermelhos)
1. `_sinal` usa `Decimal(str(...))`: `{"decimal":"abc"}` levanta decimal.InvalidOperation (ArithmeticError, fora do except de `obter`), que propaga em vez de retornar None. Teste: [sinal_decimal_invalido]. `obter_modelo_desenho` mascara (captura Exception), mas o contrato de `obter` ("corrompido -> None") e violado.
2. Decodificacao coage tipos em vez de validar (`str(None)` -> "None", `bool("false")` -> True, `int(1.9)`, `int(True)`, `tuple("abc")`): JSON adulterado/corrompido vira modelo silenciosamente errado. Testes: test_tipos_errados_nao_sao_coagidos_silenciosamente[10 casos]. Severidade baixa (cache so e escrito por nos), mas nao-detecao de corrupcao semantica; se o time aceitar a leniencia, estes testes devem ser removidos pelo desenvolvedor, nao enfraquecidos.

## Observacoes
- Concorrencia no Windows: salvar simultaneo da mesma chave pode levantar PermissionError e leitor ve None durante a troca; tratado como falha de cache tolerada (teste aceita isso e exige nunca modelo parcial/misturado e arquivo final valido).
- Testes existentes do dev: nenhum errado. Falta registro de execucao vermelha (dev escreveu implementacao antes).
