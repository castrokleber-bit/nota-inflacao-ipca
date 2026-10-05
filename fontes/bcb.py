"""
Fetcher Banco Central — SGS séries temporais.

IDs verificados em jun/2026. Alterar somente após re-verificar na API:
  https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados

Combinação para média dos núcleos (MS+EX0+DP+EX3+P55):
  Atualizado jun/2026: 5 séries — 4466, 11427, 16122, 27839, 28750.
  Requer nova validação contra referência conhecida antes de marcar como estável.

Difusão IPCA-15:
  Não existe série SGS própria (verificado jun/2026).
  Calculada a partir dos subitens da tabela IBGE 7062 (parcela com var > 0).
  Validada: 65,12% (mai/2026) vs. 65,1% publicado — dif 0,02 p.p.

Requisições: uma por série, cobrindo de uma vez todos os meses que a nota usa
(13 meses para os núcleos, 2 para a difusão). São 6 no IPCA, sempre em série:
o SGS derruba parte de uma rajada.
"""
import httpx
from typing import Optional

from nucleo.impacto import calcular_difusao

from .modelo import ResultadoInflacao

_BASE_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados"

# Difusão IPCA — série verificada em jun/2026
_SGS_DIFUSAO_IPCA = 21379

# Núcleos IPCA — variação mensal (%) — IDs verificados em jun/2026
_NUCLEOS: dict[str, int] = {
    "MS":  4466,    # Médias aparadas com suavização
    "EX0": 11427,   # Por exclusão — EX0
    "DP":  16122,   # Dupla ponderação
    "EX3": 27839,   # Exclusão EX3
    "P55": 28750,   # Preços livres — P55
}

# Conjunto para média: MS+EX0+DP+EX3+P55 — atualizado jun/2026
_CONJUNTO_MEDIA: tuple[str, ...] = ("MS", "EX0", "DP", "EX3", "P55")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _mes_menos(mes_ref: str, n: int) -> str:
    """'202604', 11 -> '202505'"""
    total = int(mes_ref[:4]) * 12 + int(mes_ref[4:]) - 1 - n
    return f"{total // 12}{total % 12 + 1:02d}"


def _sgs_fetch(codigo: int, ini: str, fim: str) -> list[dict]:
    """
    Busca registros da série SGS no intervalo de datas (dd/mm/aaaa).
    Retorna [] silenciosamente em caso de erro, série sem dados ou resposta
    fora do formato esperado (lista de registros).
    """
    url = _BASE_SGS.format(codigo)
    try:
        resp = httpx.get(
            url,
            params={"formato": "json", "dataInicial": ini, "dataFinal": fim},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        dados = resp.json()
    except Exception:
        return []
    return dados if isinstance(dados, list) else []


def _parse_float(s) -> Optional[float]:
    try:
        return float(str(s).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _serie_mensal(codigo: int, mes_ini: str, mes_fim: str) -> dict[str, Optional[float]]:
    """
    Valores mensais da série entre mes_ini e mes_fim (AAAAMM), por mês.
    Cada valor fica sob o mês que o próprio registro declara no campo `data`:
    um registro de outro mês nunca é tomado pelo mês pedido. Mês ausente
    simplesmente não aparece no dicionário.
    """
    ini = f"01/{mes_ini[4:]}/{mes_ini[:4]}"
    fim = f"01/{mes_fim[4:]}/{mes_fim[:4]}"
    serie: dict[str, Optional[float]] = {}
    for d in _sgs_fetch(codigo, ini, fim):
        data = str(d.get("data", "")) if isinstance(d, dict) else ""
        if len(data) != 10:
            continue
        mes = data[6:10] + data[3:5]
        if mes_ini <= mes <= mes_fim:
            serie[mes] = _parse_float(d.get("valor"))
    return serie


def _acum12m(serie: dict[str, Optional[float]], mes_ref: str) -> Optional[float]:
    """
    Compõe o acumulado em 12 meses (composto) encerrado em mes_ref.
    Retorna None se faltar qualquer um dos 12 meses.
    """
    prod = 1.0
    for n in range(11, -1, -1):
        val = serie.get(_mes_menos(mes_ref, n))
        if val is None:
            return None
        prod *= 1 + val / 100
    return round((prod - 1) * 100, 4)


def _medias_nucleos_12m(meses: list[str]) -> dict[str, Optional[float]]:
    """
    Média dos acumulados em 12m dos núcleos para cada mês pedido, com uma só
    requisição por série (cobre do mês mais antigo − 11 ao mais recente).

    Tudo-ou-nada por mês: se QUALQUER série não fechar os 12 meses, a média
    daquele mês é None. Uma média parcial é pior que a ausência do dado: com
    4 de 5 séries o número publicado desloca em até 0,09 p.p. (ex.: 12m até
    mar/2026 = 4,39% com as 5 séries, 4,44% sem a DP) sem qualquer sinal de
    erro. O bloco de núcleo é opcional na nota — omiti-lo é seguro,
    publicá-lo errado não é.
    """
    ini, fim = _mes_menos(min(meses), 11), max(meses)
    series = [_serie_mensal(_NUCLEOS[nome], ini, fim) for nome in _CONJUNTO_MEDIA]
    medias: dict[str, Optional[float]] = {}
    for mes in meses:
        vals = [_acum12m(s, mes) for s in series]
        if any(v is None for v in vals):
            medias[mes] = None
        else:
            medias[mes] = round(sum(vals) / len(vals), 4)
    return medias


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def media_nucleos_12m(mes_ref: str) -> Optional[float]:
    """Média aritmética dos acumulados em 12m de MS+EX0+DP+EX3+P55 (ou None)."""
    return _medias_nucleos_12m([mes_ref])[mes_ref]


def enriquecer(resultado: ResultadoInflacao) -> None:
    """
    Preenche difusao, difusao_anterior, nucleo_12m e nucleo_12m_anterior
    no ResultadoInflacao fornecido. Falhas são silenciosas (campos ficam None).

    IPCA:
      difusao / difusao_anterior → SGS 21379
      nucleo_12m / nucleo_12m_anterior → média MS+EX0+DP+EX3+P55 em 12m

    IPCA-15:
      difusao → calculada dos subitens (nivel 4) já presentes em resultado
      difusao_anterior → None (requer fetch extra do IBGE; não implementado)
      nucleo_12m → None (BCB não publica núcleo do IPCA-15)
    """
    if resultado.indicador == "IPCA":
        ref, ant = resultado.mes_ref, resultado.mes_ant
        difusao = _serie_mensal(_SGS_DIFUSAO_IPCA, ant, ref)
        resultado.difusao = difusao.get(ref)
        resultado.difusao_anterior = difusao.get(ant)
        nucleos = _medias_nucleos_12m([ref, ant])
        resultado.nucleo_12m = nucleos[ref]
        resultado.nucleo_12m_anterior = nucleos[ant]
    else:
        resultado.difusao = calcular_difusao(resultado.subitens, nivel_min=4)
        resultado.difusao_anterior = None
        resultado.nucleo_12m = None
        resultado.nucleo_12m_anterior = None
