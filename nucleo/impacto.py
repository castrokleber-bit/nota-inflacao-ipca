"""
Cálculo e seleção de impactos em p.p. para a nota de inflação.

A fórmula é determinística: impacto (p.p.) = peso_mensal × variação / 100.
A propriedade ItemInflacao.impacto já aplica a fórmula; este módulo fornece
as funções de filtragem usadas pelo montador.
"""
from fontes.modelo import ItemInflacao


def calcular_impacto(variacao: float, peso: float) -> float:
    """impacto em p.p. = peso × variação / 100, arredondado a 4 casas."""
    return round(peso * variacao / 100, 4)


def grupos_relevantes(
    grupos: list[ItemInflacao],
    top_n: int = 3,
    threshold: float = 0.05,
) -> list[ItemInflacao]:
    """
    Retorna até top_n grupos com impacto positivo de pelo menos threshold p.p.
    A entrada deve estar ordenada por impacto desc (padrão de ibge.buscar_resultado).

    Só alta: um grupo em queda aqui seria anunciado como "destaque" no
    parágrafo de alta e citado de novo no de deflação (grupos_queda).
    """
    return [g for g in grupos[:top_n] if g.impacto >= threshold]


def top_subitem(
    subitens: list[ItemInflacao],
    nivel: int = 4,
) -> ItemInflacao | None:
    """
    Retorna o item de maior impacto positivo no nível solicitado, ou None.
    nivel: 2 = subgrupo, 3 = item, 4 = subitem.
    """
    candidatos = [s for s in subitens if s.nivel == nivel and s.impacto > 0]
    return candidatos[0] if candidatos else None


def grupos_queda(
    grupos: list[ItemInflacao],
    top_n: int = 1,
    threshold: float = 0.05,
) -> list[ItemInflacao]:
    """
    Retorna até top_n grupos com maior deflação (impacto <= -threshold p.p.),
    ordenados do mais negativo ao menos negativo.
    A entrada deve estar ordenada por impacto desc (padrão de ibge.buscar_resultado).
    """
    queda = [g for g in grupos if g.impacto <= -threshold]
    queda.sort(key=lambda x: x.impacto)  # mais negativo primeiro
    return queda[:top_n]


def top_subitem_queda(
    subitens: list[ItemInflacao],
    nivel: int = 4,
    threshold: float = 0.05,
) -> ItemInflacao | None:
    """
    Retorna o subitem de maior deflação (impacto <= -threshold) no nível solicitado.
    """
    candidatos = [s for s in subitens if s.nivel == nivel and s.impacto <= -threshold]
    if not candidatos:
        return None
    return min(candidatos, key=lambda x: x.impacto)


def calcular_difusao(
    subitens: list[ItemInflacao],
    nivel_min: int = 4,
) -> float | None:
    """
    Parcela de subitens (nivel >= nivel_min) com variação positiva no mês, em %.
    Usado pelo montador e para difusão do IPCA-15 (sem série SGS própria).
    """
    candidatos = [s for s in subitens if s.nivel >= nivel_min]
    if not candidatos:
        return None
    positivos = sum(1 for s in candidatos if s.variacao > 0)
    return round(positivos / len(candidatos) * 100, 2)
