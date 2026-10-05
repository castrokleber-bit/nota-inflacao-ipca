# Nota de Inflação — IPCA / IPCA-15

Página que, na divulgação do IPCA ou do IPCA-15, busca os resultados nas APIs
públicas do IBGE e do Banco Central e monta a nota de WhatsApp pronta para
cópia.

Projeto pessoal, de uso não institucional.

**Acesse:** https://castrokleber-bit.github.io/nota-inflacao-ipca/

## Como funciona

A página é totalmente estática: não há servidor, back-end nem banco de dados.
O JavaScript no seu navegador chama direto as duas APIs — ambas liberam
requisição de origem cruzada (`Access-Control-Allow-Origin: *`) — e monta o
texto localmente. Nada é enviado a lugar nenhum; a nota só aparece na tela
para você copiar.

| Dado                   | Fonte                                          |
|------------------------|------------------------------------------------|
| Variação mensal, acumulado 12m, pesos, subitens | IBGE — SIDRA, tabela 7060 (IPCA) / 7062 (IPCA-15) |
| Difusão do IPCA        | BCB — SGS série 21379                          |
| Difusão do IPCA-15     | calculada dos subitens do IBGE (não há série própria) |
| Média dos núcleos (12m)| BCB — SGS 4466, 11427, 16122, 27839, 28750     |

## A regra que estrutura o projeto

**A nota é determinística.** É montada por funções puras a partir dos dados
estruturados das APIs; nenhuma parte do texto é gerada por IA. Cada número
rastreia a um campo devolvido por uma API, e a página mostra essa proveniência
num painel próprio.

O motivo é simples: a nota carrega números oficiais. Um número inventado ali é
pior do que a ausência do dado. Por isso, quando uma série não responde, o
bloco correspondente some da nota em vez de sair com valor aproximado.

## Verificação

O texto da nota tem duas implementações: a de referência em Python
(`fontes/`, `nucleo/`) e a que roda no navegador (`site/js/`). Elas precisam
produzir a **mesma nota, byte a byte** — é isso que o gate garante.

```bash
# gate de equivalência: Python vs JavaScript, sobre entradas idênticas
node tests/equivalencia/gate.mjs

# testes da implementação de referência
python -m pytest -q -m "not integration"
```

O gate roda sobre 18 casos: as duas notas de referência (IPCA abr/2026,
IPCA-15 mai/2026) mais 20 casos sintéticos que forçam os cantos onde um port
costuma divergir — arredondamento de borda, heurística de gênero do artigo,
desempate de impacto, deflação, as quatro variações de frase por trimestre e
os ramos em que falta um dado.

Ambos rodam no GitHub Actions a cada push, e **o site só é publicado se o gate
passar**.

### Gates que dependem de rede

```bash
# reproduz as notas de referência a partir das APIs reais
node tests/equivalencia/e2e.mjs
python -m pytest -q -m integration
```

Ficam fora da publicação de propósito: dependem de o IBGE e o BCB estarem no
ar. Rodam sozinhos uma vez por mês (`.github/workflows/e2e.yml`). Quando
falham, costuma ser por um destes dois motivos — vale distinguir qual:

1. o código quebrou; ou
2. o BCB revisou uma série de núcleo e as notas de referência ficaram
   desatualizadas.

### Regenerar as notas de referência

Só faça isso quando a divergência for revisão de série (motivo 2), nunca para
silenciar uma falha:

```bash
python tests/equivalencia/dump_python.py     # recaptura das APIs
python tests/equivalencia/casos_sinteticos.py # regenera os casos sintéticos
```

## Rodar localmente

Não é necessário para o uso normal — a página publicada é a mesma coisa. Útil
para testar uma alteração antes de publicar:

```bash
python -m http.server 8777 --directory site
# abre em http://127.0.0.1:8777
```

No Windows, `iniciar.bat` faz isso e já abre o navegador. Abrir o
`site/index.html` com duplo clique **não** funciona: o navegador bloqueia
módulos ES em `file://`.

## Estrutura

```
site/              página publicada (é o que vai para o GitHub Pages)
  js/montador.js     monta o texto da nota
  js/ibge.js         fetcher SIDRA
  js/bcb.js          fetcher SGS
  js/impacto.js      seleção de destaques por impacto
  js/numeros.js      arredondamento e formatação
fontes/, nucleo/   implementação de referência em Python
tests/
  golden/            notas de referência
  equivalencia/      gate Python ⇄ JavaScript
docs/              especificação, fontes de dados, identidade visual
```

## Publicação

`main` → GitHub Actions roda o gate → publica `site/` no GitHub Pages.

Antes do primeiro deploy é preciso, **uma única vez**, ir em
Settings → Pages → Source e escolher **GitHub Actions**. Esse passo não dá
para automatizar no workflow: criar o site pela API exige escopo
`administration: write`, que não está entre as permissões concedíveis ao
`GITHUB_TOKEN`.
