/* Seleção de impactos — par de nucleo/impacto.py.
 *
 * Nota sobre ordenação: Array.prototype.sort é estável desde o ES2019, assim
 * como o sort do Python. Empates de impacto preservam a ordem de entrada nos
 * dois, então a seleção de destaques é a mesma — desde que a ordem original
 * venha da resposta da API, que ibge.js preserva com Map.
 */
import { arredondar } from "./numeros.js";

/** impacto em p.p. = peso × variação / 100, arredondado a 4 casas. */
export function calcularImpacto(variacao, peso) {
  return arredondar((peso * variacao) / 100, 4);
}

/**
 * Até topN grupos com impacto positivo de pelo menos threshold p.p.
 * Só alta: um grupo em queda aqui seria anunciado como "destaque" no
 * parágrafo de alta e citado de novo no de deflação (gruposQueda).
 */
export function gruposRelevantes(grupos, topN = 3, threshold = 0.05) {
  return grupos.slice(0, topN).filter((g) => g.impacto >= threshold);
}

/** Item de maior impacto positivo no nível pedido, ou null. Entrada já ordenada desc. */
export function topSubitem(subitens, nivel = 4) {
  return subitens.find((s) => s.nivel === nivel && s.impacto > 0) ?? null;
}

/** Até topN grupos com maior deflação, do mais negativo ao menos negativo. */
export function gruposQueda(grupos, topN = 1, threshold = 0.05) {
  return grupos
    .filter((g) => g.impacto <= -threshold)
    .sort((a, b) => a.impacto - b.impacto)
    .slice(0, topN);
}

/** Item de maior deflação no nível pedido, ou null. */
export function topSubitemQueda(subitens, nivel = 4, threshold = 0.05) {
  const candidatos = subitens.filter(
    (s) => s.nivel === nivel && s.impacto <= -threshold,
  );
  if (candidatos.length === 0) return null;
  // Comparação estrita: empate devolve o primeiro, como o min() do Python.
  return candidatos.reduce((menor, s) => (s.impacto < menor.impacto ? s : menor));
}

/** Parcela de subitens (nivel >= nivelMin) com variação positiva, em %. */
export function calcularDifusao(subitens, nivelMin = 4) {
  const candidatos = subitens.filter((s) => s.nivel >= nivelMin);
  if (candidatos.length === 0) return null;
  const positivos = candidatos.filter((s) => s.variacao > 0).length;
  return arredondar((positivos / candidatos.length) * 100, 2);
}
