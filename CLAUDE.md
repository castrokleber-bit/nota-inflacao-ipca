# CLAUDE.md — Nota de Inflação (IPCA / IPCA-15)

> Este arquivo é lido automaticamente pelo Claude Code. Ele define o que o
> projeto é, como construí-lo e — sobretudo — o que **não** fazer.

## 1. O que este projeto é

Página estática que, na divulgação do IPCA ou do IPCA-15, busca os resultados
via API (IBGE e Banco Central) e monta a nota de WhatsApp pronta para cópia.

Projeto pessoal, de uso não institucional. **Não há vínculo com nenhuma
entidade, e nenhuma marca, sigla ou assinatura institucional deve voltar ao
código, aos documentos ou ao texto da nota.** A nota **não tem assinatura**:
termina no último bloco de conteúdo. O crédito do autor fica no rodapé da
página, fora do texto que vai para o WhatsApp.

Única exceção: a nota da camada de IA (`analise/`, seção 2) pode fechar com
uma assinatura, que vive só em `analise/assinatura.local.txt`, fora do git.
O texto da assinatura nunca entra em arquivo versionado.

O objetivo é velocidade: a nota é descritiva e padronizada. Não é um produto
analítico.

## 2. Princípio de arquitetura inegociável: a fronteira determinística

- **A NOTA é determinística.** É montada por funções puras a partir dos dados
  estruturados das APIs. **Nenhuma parte do texto da nota é gerada por IA.**
  Cada número no texto rastreia diretamente a um campo devolvido pela API.
- **A camada de IA fica fora do site.** Mora em `analise/` e roda pelo comando
  `/nota-ipca` no Claude Code (`.claude/skills/nota-ipca/SKILL.md`). Usa os
  dados determinísticos como insumo, e a IA redige um texto único que junta
  números e causas. O resultado sai como artifact **privado** do Claude, com
  selo de redação por IA, e nunca é enviado automaticamente. Não vai para o
  site: a página é estática e uma chave de API não pode viver nela.
- **A IA não inventa número.** `analise/verificar.py` barra a publicação se
  um número do texto não vier da API ou do trecho de uma fonte citada, se
  faltar um obrigatório (variação mensal, 12 meses, núcleos, difusão) ou se
  uma fonte for posterior à divulgação. Se ele falhar, corrige-se o texto,
  nunca o verificador. `analise/` reusa `_fmt` e `calcular_impacto` do
  núcleo, para que o verificador exija o número exatamente como a nota o
  formata.
- **Versões do mesmo dia só acrescentam.** A nota das 9h sai sem os núcleos
  (o BCB os publica depois do IBGE). A versão posterior mantém o texto
  anterior intacto e só acrescenta o dado novo; `analise/versoes.py` confere
  isso contra a versão arquivada.

Por quê: a nota carrega números oficiais. Alucinação aqui publica um número
falso como fato.

## 3. A regra que decorre disso: dado ausente some, não vira aproximação

Quando uma fonte não responde, o bloco correspondente **sai da nota**. Nunca
se substitui um valor ausente por outro parecido. Dois bugs reais já nasceram
de violar isso, e ambos publicavam número errado sem qualquer sinal de erro:

- `media_nucleos_12m` calculava a média com as séries que respondessem. Com 4
  de 5, o número deslocava até 0,09 p.p. Hoje é tudo-ou-nada.
- `bloco_nucleo` caía para o valor do mês corrente quando faltava o anterior,
  gerando "ficou em 4,38%, ligeiramente abaixo dos 4,38%". Hoje, sem o mês
  anterior, a frase comparativa simplesmente não é escrita.

Há teste de regressão para os dois. Ao mexer em qualquer campo opcional
(`difusao`, `difusao_anterior`, `nucleo_12m`, `nucleo_12m_anterior`,
`projecao_focus`, `variacao_mesmo_mes_ano_anterior`), o ramo "ausente" precisa
omitir, nunca preencher.

## 4. Stack

- **Publicado:** HTML/CSS/JavaScript puro (`site/`), sem build, sem
  dependência, sem framework. ES modules nativos.
- **Referência:** Python 3.11+ com `httpx` (`fontes/`, `nucleo/`) — não vai
  para o site; existe para gerar as fixtures e validar o JavaScript.
- **Testes:** `pytest` (Python) e Node (gate de equivalência).

Manter dependências mínimas. Sem framework de template no montador de texto —
usar template literals/funções explícitas, para que cada bloco seja auditável.

## 5. Duas implementações, uma nota

`nucleo/montador.py` e `site/js/montador.js` são pares e **precisam produzir
saída idêntica byte a byte**. O mesmo vale para os pares
`impacto.py`/`impacto.js`, `ibge.py`/`ibge.js`, `bcb.py`/`bcb.js`,
`modelo.py`/`modelo.js`.

**Alterou um, altere o outro na mesma mudança e rode o gate.** Não existe
"depois eu sincronizo": o gate é o que impede o site de publicar uma nota
diferente da validada.

Armadilhas de port já resolvidas — não reintroduzir:

- `split(".", 1)` em Python é `maxsplit`; em JS é limite de resultados.
- `round()` do Python vs `toFixed()` do JS: equivalentes aqui porque empate
  exato não existe entre doubles nessas casas (ver comentário em `numeros.js`).
- `_fmt` carrega um erro de ponto flutuante de propósito (0,105 → 0,10). É
  porte literal; **não "consertar"** de um lado só.
- Ordem de iteração: `ibge.js` usa `Map`, não objeto — chave numérica em
  objeto JS é reordenada e muda o desempate de impacto.
- Fim de linha: fixtures e goldens são LF (ver `.gitattributes`). O Node lê
  bytes crus e o CI roda em Linux.

## 6. Comandos

```bash
# gate de equivalencia (offline) — a barreira central
node tests/equivalencia/gate.mjs

# testes da referencia Python (offline)
python -m pytest -q -m "not integration"

# gates que dependem de rede
node tests/equivalencia/e2e.mjs
python -m pytest -q -m integration

# rodar a pagina localmente
python -m http.server 8777 --directory site

# camada de IA (normalmente via /nota-ipca; saídas em analise/saida/, fora do git)
python -m analise.coletar IPCA 202608
python -m analise.coletar IPCA 202608 --atualizar   # nova versão quando o BCB publica os núcleos
python -m analise.verificar IPCA 202608
python -m analise.montar_pagina IPCA 202608
```

## 7. Regra de ouro: validação contra divulgação conhecida

Antes de considerar qualquer módulo pronto, ele tem de reproduzir as duas
notas de referência em `tests/golden/`:

- **IPCA abril/2026** (0,67%; acum. 12m 4,39%; núcleo 4,38%; difusão 65,3%)
- **IPCA-15 maio/2026** (0,62%; acum. 12m 4,64%; difusão 65,1%)

mais os 20 casos sintéticos de `tests/equivalencia/casos_sinteticos.py`.
**Não avançar sem fechar o gate.**

Se um gate de rede falhar, distinga a causa antes de agir: código quebrado ou
revisão de série pelo BCB. Só no segundo caso se regenera o golden.

## 8. Convenções (o que sempre fazer)

- **Não inventar códigos de API.** Todos os códigos (SIDRA, SGS) estão
  verificados em `docs/FONTES-DE-DADOS.md`. Se faltar, **confirmar nos
  metadados da fonte**, nunca chutar.
- **Núcleo é opcional.** A nota tem de funcionar com e sem ele.
- **Todo número exibido tem proveniência**, e a página mostra essa tabela.
- A proveniência dos números fica na tabela da interface, não no texto da
  nota. A nota não carrega linha de fonte nem assinatura.

## 9. O que NÃO fazer

- ❌ Gerar qualquer trecho da **nota do site** com IA. A camada de IA vive só
  em `analise/` (seção 2).
- ❌ Editorializar a nota do site (ela é descritiva).
- ❌ Publicar a nota da IA sem `analise/verificar.py` passar.
- ❌ Versionar o texto da assinatura, o link do artifact
  (`analise/artifact.local.txt`) ou as saídas de `analise/saida/`.
- ❌ Enviar/circular qualquer coisa automaticamente. A página só **exibe** o
  texto para cópia humana.
- ❌ Alterar dados numéricos sem fonte explícita da API.
- ❌ Preencher dado ausente com valor aproximado (ver seção 3).
- ❌ Mexer num montador sem mexer no par e rodar o gate (ver seção 5).
- ❌ Reintroduzir qualquer assinatura ou linha de fonte na nota do site (ver
  seção 1).

## 10. Identidade visual

Paleta neutra escura, especificada em `docs/IDENTIDADE-VISUAL.md` e definida
como variáveis CSS no `:root` de `site/style.css`. Sem logo, sem webfont.
