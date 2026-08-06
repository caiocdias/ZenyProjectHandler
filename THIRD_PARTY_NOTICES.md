# Avisos de componentes de terceiros

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
