# Zeny Project Handler — Cliente Windows

Este pacote contém somente a interface Windows e a comunicação HTTP. O banco, PDFs gerenciados,
análise, OCR, regras, backup e recuperação executam no servidor administrado separadamente.

O painel **Exportar** baixa arquivos finais, não cópias internas do projeto: PDF com as anotações
de conformidade, Resultados `.xlsx` (Elementos e Vãos), Documentação `.xlsx` e Conformidade `.xlsx`
(Conformidade e Regras). Escolha uma pasta local; o cliente só publica o arquivo depois de conferir
tamanho e SHA-256.

## Abrir e conectar

1. Extraia o ZIP inteiro para uma pasta gravável.
2. Execute `ZenyProjectHandler.exe`.
3. Informe a URL fornecida pelo administrador, por exemplo `http://servidor:8000`.
4. Informe a senha do servidor. A URL pode ser lembrada; a senha nunca é salva.

Se o servidor reiniciar ou a sessão for recusada, as ações remotas ficam bloqueadas. Use
**Conexão > Reconectar** e informe a senha novamente. Em HTTP puro, use o cliente somente numa LAN
confiável; fora desse limite, o administrador deve fornecer TLS ou VPN.

Preferências visuais ficam em `%LOCALAPPDATA%\ZenyProjectHandler\ui-state.ini`. Para remover o
cliente, feche-o e apague a pasta extraída. A pasta de preferências pode ser removida separadamente;
ela não contém projetos nem a senha.
