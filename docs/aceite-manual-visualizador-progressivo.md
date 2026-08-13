# Aceite manual — visualizador PDF progressivo

Use este roteiro somente com uma prancha grande autorizada, preferencialmente A0 ou A1, que contenha
texto pequeno conhecido e resultados de análise com overlays clicáveis. Não registre no relatório o
nome do arquivo, caminho absoluto, conteúdo, coordenadas ou imagens da prancha.

## Preparação

1. Use a configuração padrão: teto visual de 600 DPI, 8.000.000 pixels e 64 MiB por solicitação e
   cache de tiles de 128 MiB. Feche outras instâncias do aplicativo.
2. Abra o Gerenciador de Tarefas na coluna **Memória** e anote apenas a ordem de grandeza inicial do
   processo, sem capturas que exponham dados da prancha.
3. Tenha duas páginas disponíveis, overlays de análise conhecidos e ao menos um link de revisão cuja
   seleção possa ser confirmada no painel lateral.

## Execução

1. Abra a prancha e confirme que uma visão geral legível aparece antes do detalhe fino. Enquanto ela
   carrega, mova a janela e acione a navegação: os controles devem responder sem pausa perceptível.
2. Alterne rapidamente entre as duas páginas, gire e volte à primeira. A página/rotação antiga nunca
   deve reaparecer sobre a atual, nem mesmo por um instante após a nova prévia.
3. Na visão ajustada, confirme que não há cintilação ou área transparente. Amplie progressivamente uma
   região com texto pequeno. A prévia pode ficar suave por um breve momento, mas os tiles do viewport
   devem torná-lo nítido até o detalhe disponível de 600 DPI.
4. Arraste para quatro regiões distantes. O viewport corrente deve ganhar nitidez antes das regiões
   fora da tela. Não deve ocorrer varredura detalhada visível da folha inteira.
5. Em 0°, 90°, 180° e 270°, confira que overlays permanecem sobre os mesmos objetos. Clique no link de
   revisão em cada rotação e confirme a seleção correspondente no painel.
6. Se houver monitores com DPR diferentes, mova a janela entre eles e repita zoom/pan. Não deve haver
   tile deslocado, borrado de forma permanente ou resultado do DPR anterior sobre a janela atual.
7. Repita pan, zoom e rotações por pelo menos dois ciclos completos e observe memória. Ela pode oscilar
   com prévia, tile em execução e cena ativa, mas deve estabilizar com as evicções; não pode crescer de
   modo contínuo nem se aproximar do custo de um raster A0/A1 integral a 600 DPI.
8. Inicie um zoom que ainda esteja refinando a imagem e feche a janela. O processo deve encerrar sem
   aviso de `QThread`, travamento ou janela reaparecendo.

## Callouts de conformidade

Os testes públicos geram quatro folhas inteiramente sintéticas — A4 e A3, em retrato e paisagem — e
salvam capturas temporárias da cena. Para o aceite visual, confirme em cada formato:

1. caixa integralmente branca e contida na folha, com borda e texto vermelhos legíveis;
2. quebra de texto sem corte e proporção tipográfica equivalente entre os formatos;
3. uma ou mais linhas chegando ao alvo sintético, cada qual com ponta de seta aberta;
4. ausência de sobreposição quando existe uma posição candidata livre;
5. alinhamento do alvo depois de zoom, redimensionamento, tiles, rotações 0°/90°/180°/270° e troca
   de página;
6. coexistência com o sublinhado de elemento, sem mudança no PDF nem no cache raster.

Um achado sintético sem geometria deve continuar na lista como **Sem localização no PDF** e não pode
criar item na camada gráfica. Os controles de exibir/ocultar por achado não fazem parte deste aceite.

## Invalidação controlada

Em uma cópia temporária autorizada, abra o PDF, altere ou substitua o arquivo fora do aplicativo e
então provoque novo zoom/pan. O visualizador deve remover a imagem/cache e informar que a origem mudou;
não deve mostrar tiles da identidade anterior. Exclua a cópia temporária pelo procedimento autorizado.

## Registro do aceite

Registre apenas data, versão/commit, classe aproximada da prancha (A0/A1), escala de DPR testada e
`APROVADO` ou o passo que falhou. O aceite requer simultaneamente:

- visão geral rápida e interface responsiva;
- texto pequeno nítido ao ampliar, sem reduzir o teto visual;
- ausência de resultados antigos após página, rotação, zoom ou DPR;
- overlays alinhados e links clicáveis nas quatro rotações;
- callouts contidos, legíveis, ancorados e independentes dos links/tiles;
- memória estabilizada, sem crescimento proporcional ao raster integral de 600 DPI;
- invalidação da origem e fechamento limpos.
