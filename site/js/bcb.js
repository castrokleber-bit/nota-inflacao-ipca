/* Fetcher Banco Central — séries temporais do SGS.
 * Par de fontes/bcb.py.
 *
 * IDs verificados em jun/2026. Alterar somente após re-verificar na API:
 *   https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados
 *
 * Difusão IPCA-15:
 *   Não existe série SGS própria (verificado jun/2026).
 *   Calculada a partir dos subitens da tabela IBGE 7062 (parcela com var > 0).
 *
 * Requisições: uma por série, cobrindo de uma vez todos os meses que a nota
 * usa (13 meses para os núcleos, 2 para a difusão). São 6 no IPCA.
 */
import { arredondar } from "./numeros.js";
import { calcularDifusao } from "./impacto.js";

const BASE_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados";

// Difusão IPCA — série verificada em jun/2026
const SGS_DIFUSAO_IPCA = 21379;

// Núcleos IPCA — variação mensal (%) — IDs verificados em jun/2026
const NUCLEOS = {
  MS: 4466, // Médias aparadas com suavização
  EX0: 11427, // Por exclusão — EX0
  DP: 16122, // Dupla ponderação
  EX3: 27839, // Exclusão EX3
  P55: 28750, // Preços livres — P55
};

// Conjunto para média: MS+EX0+DP+EX3+P55 — atualizado jun/2026
const CONJUNTO_MEDIA = ["MS", "EX0", "DP", "EX3", "P55"];

// ---------------------------------------------------------------------------
// Helpers internos
// ---------------------------------------------------------------------------

/** '202604', 11 -> '202505' */
function mesMenos(mesRef, n) {
  const total =
    parseInt(mesRef.slice(0, 4), 10) * 12 + parseInt(mesRef.slice(4), 10) - 1 - n;
  return `${Math.floor(total / 12)}${String((total % 12) + 1).padStart(2, "0")}`;
}

/**
 * Registros da série SGS no intervalo (dd/mm/aaaa). Devolve [] em caso de
 * erro, série sem dados ou resposta fora do formato esperado (lista).
 */
async function sgsFetch(codigo, ini, fim) {
  const url =
    BASE_SGS.replace("{}", String(codigo)) +
    `?formato=json&dataInicial=${encodeURIComponent(ini)}` +
    `&dataFinal=${encodeURIComponent(fim)}`;
  try {
    // Timeout espelha o httpx.get(timeout=30) do Python. Sem ele, uma serie
    // pendurada travaria a nota inteira; com ele, a falha vira [] e o bloco
    // correspondente some da nota — que e a politica do projeto.
    const resp = await fetch(url, { signal: AbortSignal.timeout(30000) });
    if (!resp.ok) return [];
    const dados = await resp.json();
    return Array.isArray(dados) ? dados : [];
  } catch {
    return [];
  }
}

function parseFloatBr(s) {
  if (s === null || s === undefined) return null;
  const v = Number(String(s).replace(",", "."));
  return Number.isNaN(v) ? null : v;
}

/**
 * Valores mensais da série entre mesIni e mesFim (AAAAMM), num Map por mês.
 * Cada valor fica sob o mês que o próprio registro declara no campo `data`:
 * um registro de outro mês nunca é tomado pelo mês pedido.
 */
async function serieMensal(codigo, mesIni, mesFim) {
  const ini = `01/${mesIni.slice(4)}/${mesIni.slice(0, 4)}`;
  const fim = `01/${mesFim.slice(4)}/${mesFim.slice(0, 4)}`;
  const serie = new Map();
  for (const d of await sgsFetch(codigo, ini, fim)) {
    const data = d && typeof d === "object" ? String(d.data ?? "") : "";
    if (data.length !== 10) continue;
    const mes = data.slice(6, 10) + data.slice(3, 5);
    if (mesIni <= mes && mes <= mesFim) serie.set(mes, parseFloatBr(d.valor));
  }
  return serie;
}

/** Acumulado em 12 meses (composto) encerrado em mesRef, ou null se faltar mês. */
function acum12m(serie, mesRef) {
  let prod = 1.0;
  for (let n = 11; n >= 0; n--) {
    const val = serie.get(mesMenos(mesRef, n));
    if (val === undefined || val === null) return null;
    prod *= 1 + val / 100;
  }
  return arredondar((prod - 1) * 100, 4);
}

/**
 * Média dos acumulados em 12m dos núcleos para cada mês pedido, com uma só
 * requisição por série. Tudo-ou-nada por mês: se QUALQUER série não fechar os
 * 12 meses, a média daquele mês é null. Uma média parcial é pior que a
 * ausência do dado: com 4 de 5 séries o número publicado desloca em até
 * 0,09 p.p. (ex.: 12m até mar/2026 = 4,39% com as 5 séries, 4,44% sem a DP)
 * sem qualquer sinal de erro.
 */
async function mediasNucleos12m(meses) {
  const ordenados = [...meses].sort();
  const ini = mesMenos(ordenados[0], 11);
  const fim = ordenados[ordenados.length - 1];
  // NÃO paralelizar com Promise.all. Já foi tentado: disparar as séries de
  // uma vez faz o SGS derrubar parte delas, e a nota sai sem o núcleo.
  const series = [];
  for (const nome of CONJUNTO_MEDIA) {
    series.push(await serieMensal(NUCLEOS[nome], ini, fim));
  }
  const medias = new Map();
  for (const mes of meses) {
    const vals = series.map((s) => acum12m(s, mes));
    if (vals.some((v) => v === null)) {
      medias.set(mes, null);
    } else {
      const soma = vals.reduce((a, b) => a + b, 0);
      medias.set(mes, arredondar(soma / vals.length, 4));
    }
  }
  return medias;
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/** Média aritmética dos acumulados em 12m de MS+EX0+DP+EX3+P55 (ou null). */
export async function mediaNucleos12m(mesRef) {
  return (await mediasNucleos12m([mesRef])).get(mesRef);
}

/**
 * Preenche difusao, difusao_anterior, nucleo_12m e nucleo_12m_anterior no
 * ResultadoInflacao fornecido. Falhas deixam os campos em null.
 *
 * IPCA:
 *   difusao / difusao_anterior → SGS 21379
 *   nucleo_12m / nucleo_12m_anterior → média MS+EX0+DP+EX3+P55 em 12m
 *
 * IPCA-15:
 *   difusao → calculada dos subitens (nivel 4) já presentes em resultado
 *   difusao_anterior → null (requer fetch extra do IBGE; não implementado)
 *   nucleo_12m → null (BCB não publica núcleo do IPCA-15)
 */
export async function enriquecer(resultado) {
  if (resultado.indicador === "IPCA") {
    // Em série, pelo mesmo motivo descrito em mediasNucleos12m: o SGS não
    // tolera a rajada e passa a devolver menos dados do que existe.
    const ref = resultado.mes_ref;
    const ant = resultado.mes_ant;
    const difusao = await serieMensal(SGS_DIFUSAO_IPCA, ant, ref);
    resultado.difusao = difusao.get(ref) ?? null;
    resultado.difusao_anterior = difusao.get(ant) ?? null;
    const nucleos = await mediasNucleos12m([ref, ant]);
    resultado.nucleo_12m = nucleos.get(ref);
    resultado.nucleo_12m_anterior = nucleos.get(ant);
  } else {
    resultado.difusao = calcularDifusao(resultado.subitens, 4);
    resultado.difusao_anterior = null;
    resultado.nucleo_12m = null;
    resultado.nucleo_12m_anterior = null;
  }
}
