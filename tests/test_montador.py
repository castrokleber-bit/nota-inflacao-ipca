"""
Gate G5 — saída do montador deve ser idêntica às notas golden
(caracter a caracter, UTF-8).

Notas golden em tests/golden/ representam o texto correto para
IPCA abr/2026 e IPCA-15 mai/2026. Qualquer mudança no montador
que altere o texto exige atualização explícita das notas golden.
"""
import difflib
from pathlib import Path

import pytest

from fontes.modelo import ItemInflacao, ResultadoInflacao
from nucleo.montador import compor_nota

GOLDEN_DIR = Path(__file__).parent / "golden"


def _golden(nome: str) -> str:
    return (GOLDEN_DIR / nome).read_text(encoding="utf-8")


def _diff(obtido: str, esperado: str) -> str:
    """Gera diff legivel entre dois textos para mensagem de falha."""
    linhas_o = obtido.splitlines(keepends=True)
    linhas_e = esperado.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(linhas_e, linhas_o, fromfile="golden", tofile="obtido")
    )


# ---------------------------------------------------------------------------
# Testes de integracao (chamam APIs reais)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_gate_g5_ipca_abril2026():
    """Gate G5 — IPCA abr/2026: texto identico ao golden."""
    from fontes.ibge import buscar_resultado
    from fontes.bcb import enriquecer

    esperado = _golden("ipca_abril2026.txt")
    r = buscar_resultado("IPCA", "202604")
    enriquecer(r)
    obtido = compor_nota(r)
    assert obtido == esperado, "\n" + _diff(obtido, esperado)


@pytest.mark.integration
def test_gate_g5_ipca15_maio2026():
    """Gate G5 — IPCA-15 mai/2026: texto identico ao golden."""
    from fontes.ibge import buscar_resultado
    from fontes.bcb import enriquecer

    esperado = _golden("ipca15_maio2026.txt")
    r = buscar_resultado("IPCA-15", "202605")
    enriquecer(r)
    obtido = compor_nota(r)
    assert obtido == esperado, "\n" + _diff(obtido, esperado)


# ---------------------------------------------------------------------------
# Testes unitarios (sem API — validam logica do montador)
# ---------------------------------------------------------------------------

def _resultado_simples(
    indicador: str = "IPCA",
    mes_ref: str = "202604",
    mes_ant: str = "202603",
    var: float = 0.67,
    var_ant: float = 0.88,
    acum: float = 4.39,
    acum_ant: float = 4.14,
    difusao: float = 65.25,
    difusao_anterior: float = 67.37,
    nucleo_12m: float = 4.39,
    nucleo_ant: float = 4.44,
    grupos=None,
    subitens=None,
) -> ResultadoInflacao:
    if grupos is None:
        grupos = [
            ItemInflacao(7170, "1.Alimentação e bebidas",   1, var,  21.45, "fixture"),
            ItemInflacao(7660, "6.Saúde e cuidados pessoais", 1, 1.16, 13.60, "fixture"),
            ItemInflacao(7445, "2.Habitação",               1, 0.63, 15.20, "fixture"),
        ]
        grupos.sort(key=lambda x: x.impacto, reverse=True)
    if subitens is None:
        subitens = [ItemInflacao(999, "gasolina", 4, 1.86, 5.28, "fixture")]
    return ResultadoInflacao(
        indicador=indicador, mes_ref=mes_ref, mes_ant=mes_ant,
        variacao_mensal=var, variacao_mensal_anterior=var_ant,
        acum_12m=acum, acum_12m_anterior=acum_ant,
        grupos=grupos, subitens=subitens,
        difusao=difusao, difusao_anterior=difusao_anterior,
        nucleo_12m=nucleo_12m, nucleo_12m_anterior=nucleo_ant,
    )


def test_sem_nucleo_nao_aparece_bloco():
    """Quando nucleo_12m e None, o bloco de nucleo nao e incluido."""
    r = _resultado_simples(nucleo_12m=None, nucleo_ant=None)
    nota = compor_nota(r)
    assert "\U0001f4c9" not in nota  # 📉 nao aparece
    assert "núcleo" not in nota


def test_sem_nucleo_nota_completa():
    """Nota sem nucleo ainda tem titulo, resultado, explicacao, acumulado, difusao."""
    r = _resultado_simples(nucleo_12m=None, nucleo_ant=None)
    nota = compor_nota(r)
    assert "*IPCA ABRIL/2026*" in nota
    assert "*alta de 0,67%*" in nota
    assert "*4,39%*" in nota          # acumulado
    assert "65,3%" in nota            # difusao


def test_ipca15_sem_nucleo_sem_difusao_anterior():
    """IPCA-15: sem nucleo, sem difusao_anterior — nota valida sem erros."""
    r = _resultado_simples(
        indicador="IPCA-15",
        nucleo_12m=None, nucleo_ant=None,
        difusao=65.1, difusao_anterior=None,
    )
    nota = compor_nota(r)
    assert "*IPCA-15 ABRIL/2026*" in nota
    assert "núcleo" not in nota
    assert "65,1%" in nota
    # sem comparacao de difusao anterior
    assert "abaixo do registrado" not in nota
    assert "acima do registrado" not in nota


def test_formato_numerico_virgula():
    """Numeros devem usar virgula decimal (padrao pt-BR)."""
    r = _resultado_simples()
    nota = compor_nota(r)
    assert "0,67%" in nota
    assert "0.67%" not in nota


def test_rounding_half_up():
    """_fmt usa HALF_UP: 65,25 -> 65,3 (nao 65,2 banker's rounding)."""
    from nucleo.montador import _fmt
    assert _fmt(65.25, decimais=1) == "65,3"
    assert _fmt(0.085, decimais=2) == "0,09"
    assert _fmt(4.3896, decimais=2) == "4,39"


def test_dois_grupos_relevantes():
    """Com 2 grupos acima do threshold, usa forma singular 'destaca-se'."""
    grupos = [
        ItemInflacao(1, "1.Grupo A", 1, 2.0, 15.0, "x"),   # impacto 0.30
        ItemInflacao(2, "2.Grupo B", 1, 1.0, 10.0, "x"),   # impacto 0.10
    ]
    grupos.sort(key=lambda x: x.impacto, reverse=True)
    r = _resultado_simples(grupos=grupos, subitens=[])
    nota = compor_nota(r)
    assert "destaca-se o grupo Grupo B" in nota
    assert "destacam-se" not in nota


def test_tres_grupos_usa_plural():
    """Com 3 grupos, usa 'destacam-se os grupos'."""
    r = _resultado_simples()
    nota = compor_nota(r)
    assert "destacam-se os grupos" in nota


def test_projecao_focus_aparece_quando_presente():
    """Linha de projecao e incluida quando projecao_focus e informada."""
    r = _resultado_simples()
    r.projecao_focus = 0.70
    nota = compor_nota(r)
    assert "Pesquisa Focus" in nota
    assert "0,70%" in nota


def test_projecao_omitida_sem_dados():
    """Linha de projecao e omitida quando projecao_focus e None."""
    r = _resultado_simples()
    r.projecao_focus = None
    nota = compor_nota(r)
    assert "Focus" not in nota






def test_link_ibge_incluido():
    r = _resultado_simples()
    r.url_ibge = "https://ibge.gov.br/nota-exemplo"
    nota = compor_nota(r)
    assert "Notícia: https://ibge.gov.br/nota-exemplo" in nota


def test_link_ibge_omitido_quando_none():
    r = _resultado_simples()
    r.url_ibge = None
    nota = compor_nota(r)
    assert "Notícia:" not in nota


def test_artigo_gasolina():
    """'gasolina' e feminina — deve aparecer 'da gasolina'."""
    r = _resultado_simples(
        subitens=[ItemInflacao(1, "gasolina", 4, 1.86, 5.28, "x")]
    )
    nota = compor_nota(r)
    assert "da *gasolina*" in nota


def test_artigo_energia():
    """'energia elétrica residencial' e feminina — deve aparecer 'da energia'."""
    r = _resultado_simples(
        subitens=[ItemInflacao(1, "energia elétrica residencial", 4, 2.16, 3.93, "x")]
    )
    nota = compor_nota(r)
    assert "da *energia elétrica residencial*" in nota


def test_grupo_com_deflacao_aparece_na_nota():
    """Grupo com impacto <= -0,05 p.p. gera parágrafo 'Em sentido contrário'."""
    grupos = [
        ItemInflacao(1, "1.Alta A",  1,  2.0, 20.0, "fixture"),   # impacto  0.40
        ItemInflacao(2, "2.Queda B", 1, -1.5, 10.0, "fixture"),   # impacto -0.15
    ]
    grupos.sort(key=lambda x: x.impacto, reverse=True)
    r = _resultado_simples(grupos=grupos, subitens=[])
    nota = compor_nota(r)
    assert "Em sentido contrário" in nota
    assert "queda do grupo" in nota
    assert "Queda B" in nota
    assert "-1,50%" in nota
    assert "-0,15 p.p." in nota


def test_grupo_sem_deflacao_significativa_nao_aparece():
    """Grupo com impacto entre 0 e -0,05 p.p. não gera parágrafo de deflação."""
    grupos = [
        ItemInflacao(1, "1.Alta A",   1,  2.0, 20.0, "fixture"),  # impacto  0.40
        ItemInflacao(2, "2.Queda B",  1, -0.1,  5.0, "fixture"),  # impacto -0.005
    ]
    grupos.sort(key=lambda x: x.impacto, reverse=True)
    r = _resultado_simples(grupos=grupos, subitens=[])
    nota = compor_nota(r)
    assert "Em sentido contrário" not in nota


def test_subitem_com_deflacao_aparece_na_nota():
    """Subitem com impacto <= -0,05 p.p. gera parágrafo de maior deflação."""
    subitens = [
        ItemInflacao(1, "gasolina",  4,  2.0, 5.0, "fixture"),    # impacto  0.10
        ItemInflacao(2, "energia",   4, -2.0, 5.0, "fixture"),    # impacto -0.10
    ]
    r = _resultado_simples(subitens=subitens)
    nota = compor_nota(r)
    assert "maior deflação individual" in nota
    assert "energia" in nota
    assert "-2,00%" in nota


def test_deflacao_nao_aparece_em_ipca_normal():
    """No cenário padrão (todos positivos), não há parágrafo de deflação."""
    r = _resultado_simples()
    nota = compor_nota(r)
    assert "Em sentido contrário" not in nota
    assert "maior deflação" not in nota


def test_subgrupo_nivel2_aparece_na_nota():
    """Subitem de nivel 2 com impacto positivo gera parágrafo de subgrupo."""
    subitens = [
        ItemInflacao(1, "11.Alimentação no domicílio", 2, 2.0, 10.0, "fixture"),  # impacto 0.20
        ItemInflacao(2, "1101.Cereais e derivados",    3, 3.0,  5.0, "fixture"),  # impacto 0.15
        ItemInflacao(3, "1101001.Arroz",               4, 5.0,  2.0, "fixture"),  # impacto 0.10
    ]
    r = _resultado_simples(subitens=subitens)
    nota = compor_nota(r)
    assert "subgrupo de maior impacto" in nota
    assert "alimentação no domicílio" in nota
    assert "item de maior impacto" in nota
    assert "subitem de maior impacto" in nota


def test_item_nivel3_aparece_na_nota():
    """Item de nivel 3 com impacto positivo gera parágrafo de maior impacto."""
    subitens = [
        ItemInflacao(1, "1101.Cereais e derivados",  3, 3.0, 5.0, "fixture"),  # impacto 0.15
        ItemInflacao(2, "1101001.Arroz",              4, 5.0, 2.0, "fixture"),  # impacto 0.10
    ]
    r = _resultado_simples(subitens=subitens)
    nota = compor_nota(r)
    assert "item de maior impacto" in nota
    assert "cereais e derivados" in nota
    assert "subitem de maior impacto" in nota
    assert "arroz" in nota


def test_item_nivel3_queda_aparece_na_nota():
    """Item nivel 3 com deflação gera parágrafo de maior deflação entre itens."""
    grupos = [
        ItemInflacao(1, "1.Alta A", 1, 2.0, 20.0, "fixture"),
        ItemInflacao(2, "2.Queda B", 1, -2.0, 10.0, "fixture"),  # impacto -0.20
    ]
    grupos.sort(key=lambda x: x.impacto, reverse=True)
    subitens = [
        ItemInflacao(3, "1101.Cereais e derivados", 3, -3.0, 5.0, "fixture"),  # impacto -0.15
    ]
    r = _resultado_simples(grupos=grupos, subitens=subitens)
    nota = compor_nota(r)
    assert "item de maior deflação" in nota
    assert "cereais e derivados" in nota


def test_ordem_inflacao_antes_deflacao():
    """Parágrafos de alta aparecem antes dos parágrafos de queda na nota."""
    grupos = [
        ItemInflacao(1, "1.Alta A", 1, 2.0, 20.0, "fixture"),
        ItemInflacao(2, "2.Queda B", 1, -2.0, 10.0, "fixture"),
    ]
    grupos.sort(key=lambda x: x.impacto, reverse=True)
    subitens = [
        ItemInflacao(3, "gasolina", 4, 2.0, 5.0, "fixture"),    # alta subitem
        ItemInflacao(4, "energia", 4, -2.0, 5.0, "fixture"),    # queda subitem
    ]
    r = _resultado_simples(grupos=grupos, subitens=subitens)
    nota = compor_nota(r)
    pos_alta = nota.index("subitem de maior impacto")
    pos_queda = nota.index("subitem de maior deflação")
    assert pos_alta < pos_queda


def test_nucleo_sem_mes_anterior_nao_inventa_comparacao():
    """
    Regressao: com nucleo_12m_anterior=None a nota nao pode comparar o valor
    com ele mesmo. O fallback antigo produzia "ficou em X%, ligeiramente
    abaixo dos X%" — um numero fabricado para o mes anterior.
    """
    r = _resultado_simples(nucleo_12m=4.38, nucleo_ant=None)
    nota = compor_nota(r)
    assert "no acumulado em 12 meses até abril." in nota
    assert "ligeiramente" not in nota
    assert "no acumulado até março" not in nota


def test_nucleo_com_mes_anterior_mantem_comparacao():
    """Havendo os dois valores, a frase comparativa continua igual."""
    r = _resultado_simples(nucleo_12m=4.38, nucleo_ant=4.39)
    nota = compor_nota(r)
    assert "ligeiramente abaixo dos 4,39% no acumulado até março." in nota


def test_nota_nao_tem_assinatura():
    """
    Regressao: a nota termina no conteudo, sem bloco de assinatura nem linha
    de fonte. A proveniencia dos numeros fica na tabela da interface, nao no
    texto que vai para o WhatsApp.
    """
    nota = compor_nota(_resultado_simples())
    ultimo_bloco = nota.split("\n\n")[-1]
    assert "_*" not in ultimo_bloco
    assert "Fonte:" not in nota
    assert "Kleber" not in nota
    # O ultimo bloco passa a ser o de difusao
    assert ultimo_bloco.startswith("\U0001f4ca")


def test_queda_sai_sem_sinal_negativo():
    """
    Regressao: "queda de -0,32%" e "recuo de -0,15%". A palavra ja da o
    sentido; o numero vem sem sinal.
    """
    r = _resultado_simples(var=-0.32, var_ant=-0.15)
    r.variacao_mesmo_mes_ano_anterior = -0.08
    nota = compor_nota(r)
    assert "*queda de 0,32%*" in nota
    assert "após recuo de 0,15% em março" in nota
    assert "queda de 0,08% em abril de 2025" in nota
    assert "de -0," not in nota.split("\n\n")[1]


def test_variacao_que_arredonda_a_zero_e_estabilidade():
    """Regressao: -0,004 virava "queda de -0,00%"."""
    nota = compor_nota(_resultado_simples(var=0.001, var_ant=-0.004))
    assert "*estabilidade (0,00%)*" in nota
    assert "após estabilidade (0,00%) em março" in nota


def test_comparacao_usa_numero_exibido():
    """
    Regressao (mesma classe da secao 3 do CLAUDE.md): a comparacao usava o
    float cru, e 4,391 x 4,389 publicava "4,39%, acima dos 4,39%".
    """
    r = _resultado_simples(acum=4.391, acum_ant=4.389, difusao=65.32, difusao_anterior=65.28)
    nota = compor_nota(r)
    assert "ficou em *4,39%*, igual aos 4,39%" in nota
    assert "ficou em *65,3%*, igual ao registrado em março (65,3%)" in nota


def test_grupo_em_queda_nao_vira_destaque_de_alta():
    """
    Regressao: o filtro por impacto absoluto punha um grupo em queda entre os
    "destaques" de alta, e o mesmo grupo voltava no paragrafo de deflacao.
    """
    grupos = [
        ItemInflacao(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45, "fixture"),
        ItemInflacao(7660, "6.Saúde e cuidados pessoais", 1, 0.10, 13.60, "fixture"),
        ItemInflacao(7445, "2.Habitação", 1, -0.70, 15.20, "fixture"),
    ]
    nota = compor_nota(_resultado_simples(grupos=grupos))
    assert nota.count("Habitação") == 1
    assert "destacam-se os grupos" not in nota


def test_mes_sem_grupo_em_alta_mantem_deflacao():
    """
    Regressao: sem grupo em alta relevante a explicacao inteira sumia, inclusive
    a deflacao; e o grupo que menos caiu era apresentado como o principal.
    """
    grupos = [
        ItemInflacao(7445, "2.Habitação", 1, -0.90, 15.20, "fixture"),
        ItemInflacao(7170, "1.Alimentação e bebidas", 1, -1.34, 21.45, "fixture"),
    ]
    subitens = [ItemInflacao(999, "1103001.gasolina", 4, -3.20, 5.28, "fixture")]
    nota = compor_nota(_resultado_simples(var=-0.32, grupos=grupos, subitens=subitens))
    assert "*reflete a queda do grupo Alimentação e bebidas*" in nota
    assert "Habitação" not in nota
    assert "Em sentido contrário" not in nota
    assert "queda da *gasolina*" in nota


@pytest.mark.parametrize("nome, artigo", [
    ("gás de botijão", "do"),
    ("macarrão", "do"),
    ("higiene pessoal", "da"),
    ("ônibus urbano", "do"),
    ("cinema, teatro e concertos", "do"),
    ("aves e ovos", "das"),
    ("tubérculos, raízes e legumes", "dos"),
    ("alimentação no domicílio", "da"),
    ("passagem aérea", "da"),
])
def test_artigo_excecoes(nome, artigo):
    from nucleo.montador import _artigo_de
    assert _artigo_de(nome) == artigo
