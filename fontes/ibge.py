"""
Fetcher IBGE — tabelas SIDRA 7060 (IPCA) e 7062 (IPCA-15).

IDs de variáveis e categorias verificados nos metadados em jun/2026.
Não alterar sem re-verificar em:
  https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados
"""
import re
import httpx

from .modelo import ItemInflacao, ResultadoInflacao

_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Variáveis por indicador — IDs verificados nos metadados em jun/2026
_CONF: dict[str, dict] = {
    "IPCA": {
        "tabela": 7060,
        "var_mensal": 63,
        "var_acum12m": 2265,
        "var_peso": 66,
    },
    "IPCA-15": {
        "tabela": 7062,
        "var_mensal": 355,
        "var_acum12m": 1120,
        "var_peso": 357,
    },
}

# Classificação 315 — IDs verificados nos metadados em jun/2026
_CAT_GERAL = 7169
_CATS_GRUPO = [7170, 7445, 7486, 7558, 7625, 7660, 7712, 7766, 7786]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _mes_anterior(mes: str) -> str:
    ano, m = int(mes[:4]), int(mes[4:])
    return f"{ano - 1}12" if m == 1 else f"{ano}{m - 1:02d}"


def _mesmo_mes_ano_anterior(mes: str) -> str:
    return f"{int(mes[:4]) - 1}{mes[4:]}"


def _nivel_from_nome(nome: str) -> int:
    """
    Infere o nível hierárquico pelo comprimento do prefixo numérico no nome.
    Padrão IBGE:
      sem prefixo  → 0 (Índice geral)
      1 dígito     → 1 (grupo)
      2 dígitos    → 2 (subgrupo)
      4 dígitos    → 3 (item)
      7 dígitos    → 4 (subitem)
    """
    m = re.match(r"^(\d+)\.", nome)
    if not m:
        return 0
    n = len(m.group(1))
    if n == 1:
        return 1
    if n == 2:
        return 2
    if n == 4:
        return 3
    if n == 7:
        return 4
    return -1


def _parse_float(s) -> float | None:
    if s is None or str(s).strip() in ("...", "-", ""):
        return None
    try:
        return float(str(s).replace(",", "."))
    except (ValueError, TypeError):
        return None




def _fetch(
    tabela: int,
    periodos: list[str],
    variaveis: list[int],
    cats,
) -> dict[str, dict[int, dict[int, tuple[str, float]]]]:
    """
    Chama a API de Agregados para um ou mais períodos de uma vez e retorna
    {periodo: {var_id: {cat_id: (nome, valor)}}}.
    cats: lista de ints ou a string literal "all".
    Categorias sem dado disponível ("...") são omitidas do resultado.
    """
    vars_str = "|".join(str(v) for v in variaveis)
    cats_str = cats if cats == "all" else ",".join(str(c) for c in cats)
    url = (
        f"{_BASE}/{tabela}/periodos/{'|'.join(periodos)}/variaveis/{vars_str}"
        f"?localidades=N1[all]&classificacao=315[{cats_str}]"
    )
    resp = httpx.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    result: dict[str, dict[int, dict[int, tuple[str, float]]]] = {
        p: {} for p in periodos
    }
    for bloco in data:
        var_id = int(bloco["id"])
        for p in periodos:
            result[p][var_id] = {}
        for entrada in bloco.get("resultados", []):
            cat_d = entrada["classificacoes"][0]["categoria"]
            cat_id = int(next(iter(cat_d)))
            cat_nome = next(iter(cat_d.values()))
            series = entrada.get("series", [])
            if not series:
                continue
            for p in periodos:
                val = _parse_float(series[0]["serie"].get(p))
                if val is not None:
                    result[p][var_id][cat_id] = (cat_nome, val)
    return result


def _itens(
    d: dict[int, dict[int, tuple[str, float]]],
    vm: int,
    vp: int,
    fonte: str,
) -> tuple[list[ItemInflacao], list[ItemInflacao]]:
    """
    Grupos (nível 1, na ordem de _CATS_GRUPO) e itens de nível >= 2 (na ordem
    da resposta), ambos ordenados por impacto desc. Só entra quem tem
    variação e peso.
    """
    por_var, por_peso = d.get(vm, {}), d.get(vp, {})

    grupos: list[ItemInflacao] = []
    for cat_id in _CATS_GRUPO:
        entry_vm = por_var.get(cat_id)
        entry_vp = por_peso.get(cat_id)
        if entry_vm and entry_vp:
            grupos.append(ItemInflacao(
                cat_id=cat_id,
                nome=entry_vm[0],
                nivel=1,
                variacao=entry_vm[1],
                peso=entry_vp[1],
                fonte=fonte,
            ))
    grupos.sort(key=lambda x: x.impacto, reverse=True)

    subitens: list[ItemInflacao] = []
    for cat_id, (cat_nome, variacao) in por_var.items():
        nivel = _nivel_from_nome(cat_nome)
        if nivel < 2:
            continue
        entry_vp = por_peso.get(cat_id)
        if entry_vp is None:
            continue
        subitens.append(ItemInflacao(
            cat_id=cat_id,
            nome=cat_nome,
            nivel=nivel,
            variacao=variacao,
            peso=entry_vp[1],
            fonte=fonte,
        ))
    subitens.sort(key=lambda x: x.impacto, reverse=True)
    return grupos, subitens


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def buscar_resultado(indicador: str, mes_ref: str) -> ResultadoInflacao:
    """
    Busca o resultado do IPCA ou IPCA-15 para o período informado (AAAAMM)
    e retorna um ResultadoInflacao com grupos e subitens ordenados por impacto.

    Três requisições: índice geral do mês e do anterior (uma só, dois
    períodos), mesmo mês do ano anterior (opcional, à parte porque pode não
    existir na tabela) e todas as categorias do mês, de onde saem grupos e
    subitens.

    difusao, nucleo e projeções ficam None; preenchidos por bcb.enriquecer().
    """
    conf = _CONF[indicador]
    tab = conf["tabela"]
    vm, va12, vp = conf["var_mensal"], conf["var_acum12m"], conf["var_peso"]
    mes_ant = _mes_anterior(mes_ref)
    fonte = f"IBGE SIDRA tabela {tab}"

    # 1. Índice geral — mês de referência e mês anterior
    d_geral = _fetch(tab, [mes_ant, mes_ref], [vm, va12], [_CAT_GERAL])
    d_cur, d_ant = d_geral[mes_ref], d_geral[mes_ant]
    variacao_mensal = d_cur[vm][_CAT_GERAL][1]
    acum_12m = d_cur[va12][_CAT_GERAL][1]
    variacao_mensal_anterior = d_ant[vm][_CAT_GERAL][1]
    acum_12m_anterior = d_ant[va12][_CAT_GERAL][1]

    # 2. Mesmo mês do ano anterior (comparação interanual no bloco_resultado)
    mes_ano_ant = _mesmo_mes_ano_anterior(mes_ref)
    try:
        d_ano_ant = _fetch(tab, [mes_ano_ant], [vm], [_CAT_GERAL])[mes_ano_ant]
        variacao_mesmo_mes_ano_anterior: float | None = d_ano_ant[vm][_CAT_GERAL][1]
    except Exception:
        variacao_mesmo_mes_ano_anterior = None

    # 3. Todas as categorias — variação + peso, mês de referência
    d_all = _fetch(tab, [mes_ref], [vm, vp], "all")[mes_ref]
    grupos, subitens = _itens(d_all, vm, vp, f"{fonte} var {vm},{vp} periodo {mes_ref}")

    return ResultadoInflacao(
        indicador=indicador,
        mes_ref=mes_ref,
        mes_ant=mes_ant,
        variacao_mensal=variacao_mensal,
        variacao_mensal_anterior=variacao_mensal_anterior,
        acum_12m=acum_12m,
        acum_12m_anterior=acum_12m_anterior,
        grupos=grupos,
        subitens=subitens,
        variacao_mesmo_mes_ano_anterior=variacao_mesmo_mes_ano_anterior,
        fonte_variacao=f"{fonte} var {vm} periodo {mes_ref}",
        fonte_acum=f"{fonte} var {va12} periodo {mes_ref}",
    )


def buscar_variacoes(indicador: str, mes: str) -> dict[str, float]:
    """
    {nome: variação} de grupos e itens de nível >= 2 num mês, com uma só
    requisição. Mesmo critério de buscar_resultado (só quem tem peso), para
    servir de histórico à camada de análise sem baixar o resultado inteiro.
    """
    conf = _CONF[indicador]
    tab, vm, vp = conf["tabela"], conf["var_mensal"], conf["var_peso"]
    d = _fetch(tab, [mes], [vm, vp], "all")[mes]
    grupos, subitens = _itens(d, vm, vp, "")
    return {i.nome: i.variacao for i in grupos + subitens}
