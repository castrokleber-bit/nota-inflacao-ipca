---
name: nota-ipca
description: Gera a nota do IPCA ou IPCA-15 com leitura por IA (dados oficiais + causas + implicações), confere cada número e publica no link fixo do artifact. Três etapas — preparar (véspera), fechar (9h, meta ~9h15) e atualizar (quando o BCB publica os núcleos).
argument-hint: [preparar|atualizar] <IPCA|IPCA-15> <AAAAMM>
---

# /nota-ipca — nota com leitura por IA

Argumentos (`$ARGUMENTS`):

| Uso | Quando | O que faz |
|---|---|---|
| `/nota-ipca preparar IPCA 202609` | véspera ou antes das 9h | pesquisa o que já se sabe e rascunha o contexto |
| `/nota-ipca IPCA 202609` | 9h, logo após o IBGE | **fecha**: coleta, redige, verifica, publica (meta ~9h15) |
| `/nota-ipca atualizar IPCA 202609` | quando o BCB publica os núcleos | nova versão que **só acrescenta** os dados novos |

Se faltar indicador ou mês, pergunte. Não chute o mês.

**IPCA-15 — diferenças.** O fluxo é o mesmo (`preparar` e fechar), com três
diferenças:
- **Não há núcleos:** o BCB não os publica para o IPCA-15. Os obrigatórios
  são variação mensal, acumulado em 12 meses e difusão.
- **A difusão sai às 9h:** é calculada dos subitens do IBGE. Por isso **não
  existe etapa `atualizar`**, e o comando recusa se for chamado.
- **A difusão não tem valor anterior** na coleta: não compare com o mês
  anterior sem uma fonte que traga o número.

Na preparação do IPCA-15, a prévia é o IPCA do mês anterior.

Esta camada vive em `analise/` e **não toca no site**. A nota do site continua
determinística (CLAUDE.md, seções 2 e 5). Aqui os dados determinísticos são
insumo; o texto é redigido por você e só é publicado se `verificar.py` passar.

## Regras que valem em todas as etapas

**Data de corte.** Escreva como se fosse o dia da divulgação. Só entram
fontes publicadas até essa data, inclusive.

**Regra do trecho.** Toda afirmação vem de uma página que você abriu com
WebFetch. Guarde o trecho que a sustenta e a data de publicação. O resumo do
WebSearch não é fonte: no protótipo ele trocou a queda da energia no IPCA
(7,63%) pela do IPCA-15 (6,25%). Causa sem fonte **não entra**: descreva só o
dado.

**Nada é enviado.** O artifact é o único destino. Circular é decisão do
usuário.

## Etapa `preparar` (véspera)

Objetivo: às 9h, só confrontar o dado com o que já foi pesquisado.

1. Descubra e confirme a data de divulgação no calendário do IBGE.
2. Pesquise e guarde, com trecho e data:
   - a prévia do mês: o IPCA-15 do mesmo mês, para o IPCA, ou o IPCA
     anterior, para o IPCA-15. Anote o que puxou o índice e as explicações do
     IBGE;
   - o que já se sabe do mês: reajustes de tarifas, bandeira tarifária,
     impostos, preços da Petrobras, bônus e créditos pontuais, safra;
   - a projeção do mercado para o mês e para 12 meses, se já houver;
   - o contexto de política: Selic, data do próximo Copom, Focus mais
     recente (IPCA do ano, Selic de fim de ano), meta e teto;
   - o que é relevante para a indústria: custo de energia e insumos, crédito,
     atividade.
3. Grave `analise/saida/<caso>/preparacao.json`, com o mesmo formato de
   fontes do `analise.json`, para ser reaproveitado direto:

```json
{
  "data_divulgacao": "AAAA-MM-DD",
  "fatos": [{"tema": "energia", "texto": "...", "fonte": "id", "trecho": "..."}],
  "rascunho_final": "🧭 *O que o resultado sinaliza*: ... (sem os números do mês)",
  "fontes": {"id": {"nome": "...", "data": "AAAA-MM-DD", "url": "https://..."}}
}
```

O `<caso>` é `ipca_AAAAMM` ou `ipca15_AAAAMM`.

## Etapa fechar (9h) — a corrida

Meta: publicado por volta das 9h15. Seja econômico: nada de pesquisa que a
preparação já cobriu.

1. `python -m analise.coletar <IND> <AAAAMM>`
   - Se a API ainda não tiver o mês, espere um minuto e rode de novo.
   - No IPCA, em geral **os núcleos (e às vezes a difusão) ainda não saíram**,
     porque o BCB os calcula depois do IBGE. É o esperado: a nota das 9h sai
     sem eles. No IPCA-15 nada fica pendente.
2. Confronte os maiores impactos com o `preparacao.json`. Pesquise na hora só
   os movimentos relevantes que a preparação não explicou. Prefira o release
   do IBGE na Agência de Notícias, que sai às 9h.
3. Redija `analise/saida/<caso>/analise.json` (formato abaixo).
4. `python -m analise.verificar <IND> <AAAAMM>`. Se falhar, corrija o texto,
   nunca o verificador.
5. `python -m analise.montar_pagina <IND> <AAAAMM>`
6. Publique no **link fixo** (seção Publicar).
7. Reporte (seção Reportar).

## Etapa `atualizar` (núcleos do BCB, só IPCA)

1. `python -m analise.coletar <IND> <AAAAMM> --atualizar`
   - Se o BCB ainda não publicou nada novo, o comando avisa e não altera
     nada. Diga ao usuário e pare.
   - Se publicou, a versão atual é arquivada (`analise.vN.json` etc.) e os
     dados são coletados de novo.
2. Edite `analise.json` **só acrescentando** o parágrafo do dado que chegou:
   - `📉` para a média dos núcleos, com o valor anterior e a leitura do
     movimento;
   - `📊` para a difusão, se também faltava.
   
   Insira o parágrafo na posição natural: depois do acumulado em 12 meses,
   núcleos antes da difusão. **Não mude nenhuma outra linha**, nem o
   parágrafo final, nem vírgulas. Fontes novas podem ser acrescentadas; as
   antigas ficam intactas.
3. `python -m analise.verificar <IND> <AAAAMM>`. Além das regras de sempre,
   ele confere contra a versão anterior:
   - o texto antigo está intacto e na mesma ordem;
   - os dados do IBGE não mudaram;
   - cada parágrafo novo traz um dado que acabou de chegar.
4. `python -m analise.montar_pagina <IND> <AAAAMM>`, publique no link fixo e
   reporte.

## Formato de `analise.json`

```json
{
  "data_divulgacao": "AAAA-MM-DD",
  "titulo": "🚨 *IPCA AGOSTO/2026*",
  "paragrafos": [
    {"texto": "🚩 ...", "fontes": [{"id": "infomoney", "trecho": "..."}]}
  ],
  "fontes": {
    "infomoney": {"nome": "InfoMoney, citando o release do IBGE", "data": "AAAA-MM-DD", "url": "https://..."}
  }
}
```

Regras do texto:
- **Um texto só**, no estilo WhatsApp da nota determinística: emoji no início
  do parágrafo, `*negrito*` nos destaques. Cada movimento aparece **uma vez**,
  já com a causa: "a energia caiu 7,63% com a incorporação do Bônus de
  Itaipu". A nota determinística é insumo; não repita os blocos dela.
- **Obrigatórios quando disponíveis:** variação mensal, acumulado em 12 meses,
  média dos núcleos (só IPCA) e difusão, com o valor anterior quando houver e
  uma leitura do movimento. O que o BCB ainda não publicou fica de fora, sem aproximação e
  sem menção no texto. A página avisa do dado pendente fora do texto
  copiável.
- **Ordem:**
  1. resultado do mês, com a expectativa do mercado se houver fonte;
  2. principais quedas e altas, com as causas;
  3. acumulado em 12 meses;
  4. núcleos;
  5. difusão;
  6. `🧭 *O que o resultado sinaliza*`.
- **Parágrafo final:** leitura qualificada das implicações macroeconômicas, de
  política econômica (Selic, Copom, Focus) e para a indústria. Pode ter
  opinião, mas cada dado tem fonte. Escreva-o de modo que continue válido
  quando os núcleos chegarem, porque ele não pode ser editado na atualização.
- Se nenhuma fonte explica um movimento, descreva só o dado. O histórico do
  `coletar` dá contexto factual, por exemplo "depois de altas de 7,12% em
  junho e 11,67% em julho".
- Nenhum nome de entidade como autora ou assinatura no texto. A assinatura
  entra pelo montador, a partir de `analise/assinatura.local.txt`.
- `trecho`: o texto copiado da página. Números de uma fonte só valem no
  parágrafo que a cita.
- Números da própria API (nota, grupos, subitens, histórico) não precisam de
  fonte. Use o formato da nota: vírgula decimal, duas casas (difusão com uma).

## Publicar

A página vai sempre para o mesmo link, que o usuário compartilhou com o
colega. O link está em `analise/artifact.local.txt`, fora do git.

- Se o arquivo existe: publique com a ferramenta Artifact, `file_path` =
  `analise/saida/<caso>/pagina.html` e `url` = o conteúdo do arquivo. Não
  passe `icon`. Se a publicação exigir ler o artifact antes, leia e publique
  de novo.
- Se não existe: publique sem `url`, com `icon` = `chart`, e grave a URL
  devolvida no arquivo. Avise o usuário que o link é novo.

## Reportar

Responda curto:
- o link e o horário da publicação;
- os dados que ainda faltam do BCB, se for o caso, lembrando de rodar
  `/nota-ipca atualizar …` quando saírem;
- o que o usuário precisa revisar:
  - afirmações que são leitura sua, e não de uma fonte (sobretudo no
    parágrafo final);
  - causas sem fonte, que ficaram só como dado;
  - fontes fracas ou secundárias.
