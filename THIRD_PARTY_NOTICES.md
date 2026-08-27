# Avisos de componentes de terceiros

## pyodbc

O runtime do servidor usa `pyodbc` como ponte DB-API 2.0 para o gerenciador ODBC do sistema.

- Projeto: `mkleehammer/pyodbc`
- Versão fixada: `5.3.0`
- Licença SPDX: `MIT-0`
- Origem: <https://github.com/mkleehammer/pyodbc/tree/5.3.0>
- Licença: <https://github.com/mkleehammer/pyodbc/blob/5.3.0/LICENSE.txt>

## Microsoft ODBC Driver 18 for SQL Server

A imagem do servidor instala o pacote oficial Debian `msodbcsql18` e aceita seus termos durante o
build não interativo. O driver é usado somente para consultar o cadastro externo configurado pelo
administrador.

- Fornecedor: Microsoft Corporation
- Pacote/versão fixados: `msodbcsql18` `18.6.2.1-1`
- Bootstrap do repositório: `packages-microsoft-prod` `1.1-debian12`, SHA-256
  `8434dcb8c346dc95fbd63dbece056c343704590b58b6a5c323d39acf52bf0b48`
- Licença: Microsoft SQL Server ODBC Driver End User License Agreement
- Origem: <https://packages.microsoft.com/debian/12/prod/pool/main/m/msodbcsql18/>
- Instalação e termos: <https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server>

## unixODBC

A imagem do servidor instala o gerenciador ODBC do Debian usado por `pyodbc` e pelo driver
Microsoft.

- Projeto: `unixODBC`
- Pacote/versão fixados: `unixodbc` `2.3.11-2+deb12u1`
- Licenças SPDX: `LGPL-2.1-or-later` (bibliotecas) e `GPL-2.0-or-later` (ferramentas)
- Origem Debian: <https://packages.debian.org/bookworm/unixodbc>
- Copyright/licenças Debian: <https://metadata.ftp-master.debian.org/changelogs/main/u/unixodbc/unixodbc_2.3.11-2+deb12u1_copyright>

## Tesseract `tessdata_fast` — português

O repositório não incorpora o binário `por.traineddata`. Durante o setup, o aplicativo pode baixar
uma cópia para a pasta de dados local do usuário e validá-la antes de uso.

- Projeto: `tesseract-ocr/tessdata_fast`
- Titulares e contribuidores: Tesseract OCR contributors
- Artefato: `por.traineddata`
- Release: `4.1.0`
- Revisão fixada: `65727574dfcd264acbb0c3e07860e4e9e9b22185`
- SHA-256: `c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`
- Licença SPDX: `Apache-2.0`

Origem imutável do artefato:
[`por.traineddata`](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/65727574dfcd264acbb0c3e07860e4e9e9b22185/por.traineddata).

Texto da licença aplicável na mesma revisão:
[`LICENSE`](https://github.com/tesseract-ocr/tessdata_fast/blob/65727574dfcd264acbb0c3e07860e4e9e9b22185/LICENSE).
A licença Apache 2.0 também está publicada pela Apache Software Foundation em
[`LICENSE-2.0`](https://www.apache.org/licenses/LICENSE-2.0).

O projeto não modifica o modelo. A cópia instalada pode ser removida conforme descrito no README e
é recriada a partir da origem e do checksum acima. `eng.traineddata`, quando já disponível na
instalação local do Tesseract, pode ser copiado para a mesma pasta gravável apenas para compor
`por+eng`; essa cópia não é baixada nem distribuída por este repositório.
