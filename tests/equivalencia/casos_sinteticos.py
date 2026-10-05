"""
Gera casos sintéticos para o gate de equivalência Python ⇄ JavaScript.

    python tests/equivalencia/casos_sinteticos.py

As duas fixtures reais cobrem só o caminho feliz. Um port quebra nos cantos:
arredondamento de borda, heurística de gênero do artigo, ordem de desempate,
ramos em que um dado está ausente, variação de frase por trimestre. Cada caso
aqui existe para forçar um desses cantos.

Grava no mesmo formato de dump_python.py, em tests/equivalencia/fixtures/, e
o gate.mjs os consome automaticamente — ele varre todos os .json da pasta.
Não faz rede: os números são fabricados de propósito.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fontes.modelo import ItemInflacao, ResultadoInflacao  # noqa: E402
from nucleo.montador import compor_nota  # noqa: E402
from fontes.modelo import serializar  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def item(cat, nome, nivel, variacao, peso):
    return ItemInflacao(cat, nome, nivel, variacao, peso, "sintetico")


def resultado(**kw):
    base = dict(
        indicador="IPCA",
        mes_ref="202604",
        mes_ant="202603",
        variacao_mensal=0.67,
        variacao_mensal_anterior=0.88,
        acum_12m=4.39,
        acum_12m_anterior=4.14,
        grupos=[],
        subitens=[],
    )
    base.update(kw)
    grupos = sorted(base["grupos"], key=lambda x: x.impacto, reverse=True)
    subitens = sorted(base["subitens"], key=lambda x: x.impacto, reverse=True)
    base["grupos"] = grupos
    base["subitens"] = subitens
    return ResultadoInflacao(**base)


# Nomes escolhidos para cobrir a heurística de _artigo_de: feminino da lista,
# terminações -cao/-dade/-gem, plural, masculino, e primeira palavra que
# discorda da última ("alimentação no domicílio", "tubérculos, raízes...").
NOMES = [
    (1101, "1101.alimentação no domicílio", 2),
    (1102, "1102.tubérculos, raízes e legumes", 3),
    (1103, "1103.gasolina", 4),
    (1104, "1104.energia elétrica residencial", 4),
    (1105, "1105.passagem aérea", 4),
    (1106, "1106.cursos, leitura e papelaria", 2),
    (1107, "1107.aparelhos eletroeletrônicos", 3),
    (1108, "1108.mobilidade urbana", 2),
]

CASOS = {}

# 1. Todos os níveis com alta e queda simultâneas, nomes variados.
CASOS["sint_niveis_mistos"] = resultado(
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45),
        item(7445, "2.Habitação", 1, -0.63, 15.20),
        item(7660, "6.Saúde e cuidados pessoais", 1, 1.16, 13.60),
    ],
    subitens=[item(c, n, nv, v, p) for (c, n, nv), v, p in zip(
        NOMES,
        [1.64, 15.49, 1.86, -4.00, -14.45, 0.90, -2.10, 3.30],
        [10.5, 0.8, 5.28, 3.9, 0.76, 4.2, 1.9, 2.5],
    )],
)

# 2. Núcleo presente, mês anterior ausente — ramo que fabricava número.
CASOS["sint_nucleo_sem_anterior"] = resultado(
    nucleo_12m=4.38, nucleo_12m_anterior=None,
    difusao=65.25, difusao_anterior=None,
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 3. Nenhum dado do BCB: sem núcleo, sem difusão — a linha de fonte muda.
CASOS["sint_sem_dados_bcb"] = resultado(
    nucleo_12m=None, difusao=None,
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 4. Arredondamento de borda: impactos que caem exatamente na terceira casa e
#    valores que expõem o erro de ponto flutuante embutido em _fmt.
CASOS["sint_arredondamento"] = resultado(
    variacao_mensal=0.105,
    variacao_mensal_anterior=0.085,
    acum_12m=4.3896,
    acum_12m_anterior=4.3849,
    difusao=65.25,
    difusao_anterior=67.35,
    nucleo_12m=4.3850,
    nucleo_12m_anterior=4.3950,
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 1.005, 21.45),
        item(7445, "2.Habitação", 1, 0.655, 15.20),
        item(7660, "6.Saúde e cuidados pessoais", 1, 0.335, 13.60),
    ],
    subitens=[item(1103, "1103.gasolina", 4, 1.865, 5.285)],
)

# 5. Deflação generalizada: variação mensal negativa e dois grupos em queda.
CASOS["sint_deflacao"] = resultado(
    variacao_mensal=-0.32,
    variacao_mensal_anterior=-0.15,
    variacao_mesmo_mes_ano_anterior=-0.08,
    acum_12m=3.10,
    acum_12m_anterior=3.55,
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, -1.34, 21.45),
        item(7445, "2.Habitação", 1, -0.90, 15.20),
        item(7660, "6.Saúde e cuidados pessoais", 1, 0.20, 13.60),
    ],
    subitens=[
        item(1103, "1103.gasolina", 4, -3.20, 5.28),
        item(1101, "1101.alimentação no domicílio", 2, -1.80, 10.5),
        item(1102, "1102.tubérculos, raízes e legumes", 3, -6.40, 0.8),
    ],
)

# 6. Um só grupo relevante: sem conector singular nem plural.
CASOS["sint_um_grupo"] = resultado(
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45),
        item(7445, "2.Habitação", 1, 0.01, 15.20),  # abaixo do threshold
    ],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 7. Dois grupos relevantes: conector singular.
CASOS["sint_dois_grupos"] = resultado(
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45),
        item(7445, "2.Habitação", 1, 0.63, 15.20),
    ],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 8-11. Um caso por trimestre — cobre as quatro variações de frase.
for _nome, _mes_ref, _mes_ant in [
    ("sint_q1", "202602", "202601"),
    ("sint_q2", "202605", "202604"),
    ("sint_q3", "202608", "202607"),
    ("sint_q4", "202611", "202610"),
]:
    CASOS[_nome] = resultado(
        mes_ref=_mes_ref, mes_ant=_mes_ant,
        variacao_mesmo_mes_ano_anterior=0.43,
        grupos=[
            item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45),
            item(7445, "2.Habitação", 1, -0.70, 15.20),
            item(7660, "6.Saúde e cuidados pessoais", 1, 1.16, 13.60),
        ],
        subitens=[
            item(1101, "1101.alimentação no domicílio", 2, 1.64, 10.5),
            item(1102, "1102.tubérculos, raízes e legumes", 3, 15.49, 0.8),
            item(1103, "1103.gasolina", 4, 1.86, 5.28),
            item(1105, "1105.passagem aérea", 4, -14.45, 0.76),
            item(1106, "1106.cursos, leitura e papelaria", 2, -2.30, 4.2),
            item(1107, "1107.aparelhos eletroeletrônicos", 3, -3.10, 1.9),
        ],
    )

# 12. IPCA-15: nunca leva núcleo; difusão sem mês anterior.
CASOS["sint_ipca15"] = resultado(
    indicador="IPCA-15", mes_ref="202605", mes_ant="202604",
    nucleo_12m=None, difusao=65.12, difusao_anterior=None,
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 1.38, 21.45),
        item(7445, "2.Habitação", 1, 1.03, 15.20),
    ],
    subitens=[item(1101, "1101.alimentação no domicílio", 2, 1.73, 10.5)],
)

# 13. Projeção Focus presente, nos três relativos possíveis.
for _nome, _proj in [
    ("sint_focus_em_linha", 0.67),
    ("sint_focus_acima", 0.40),
    ("sint_focus_abaixo", 0.95),
]:
    CASOS[_nome] = resultado(
        projecao_focus=_proj,
        grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
        subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
    )

# 14. Empate exato de impacto entre subitens: a ordem de entrada decide, e
#     Python e JS precisam desempatar igual (sort estável nos dois).
CASOS["sint_empate_impacto"] = resultado(
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[
        item(2001, "2001.primeiro empatado", 4, 2.00, 5.00),
        item(2002, "2002.segundo empatado", 4, 2.00, 5.00),
        item(2003, "2003.terceiro empatado", 4, 1.00, 10.00),
    ],
)

# 15. Variação que arredonda a zero e comparações que empatam no número
#     exibido (4,391 x 4,389; 65,32 x 65,28): "estabilidade" e "igual",
#     nunca "4,39%, acima dos 4,39%".
CASOS["sint_estabilidade"] = resultado(
    variacao_mensal=0.001,
    variacao_mensal_anterior=-0.004,
    variacao_mesmo_mes_ano_anterior=0.0,
    acum_12m=4.391,
    acum_12m_anterior=4.389,
    nucleo_12m=4.3801,
    nucleo_12m_anterior=4.3799,
    difusao=65.32,
    difusao_anterior=65.28,
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 16. Focus exatamente 0,05 p.p. abaixo: em float, 0,67 - 0,62 dá
#     0,05000000000000004 e caía em "acima de".
CASOS["sint_focus_borda"] = resultado(
    projecao_focus=0.62,
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[item(1103, "1103.gasolina", 4, 1.86, 5.28)],
)

# 17. Exceções do artigo: singular em -s, masculino em -a, feminino em -e e
#     prefixo enganoso ("maca" em "macarrão").
CASOS["sint_artigos"] = resultado(
    grupos=[item(7170, "1.Alimentação e bebidas", 1, 1.34, 21.45)],
    subitens=[
        item(3001, "31.Higiene pessoal", 2, 1.20, 3.00),
        item(3002, "3101.Macarrão", 3, 4.00, 1.50),
        item(3003, "3101001.Gás de botijão", 4, 3.00, 1.10),
        item(3004, "32.Aves e ovos", 2, -2.00, 3.00),
        item(3005, "3201.Cinema, teatro e concertos", 3, -5.00, 1.20),
        item(3006, "3201001.Ônibus urbano", 4, -4.00, 2.00),
    ],
)

# 18. Nenhum grupo passa o limite, nem em alta nem em queda: os parágrafos
#     de queda dos subitens ficam, sem conector de contraste.
CASOS["sint_queda_sem_grupo"] = resultado(
    variacao_mensal=-0.02,
    grupos=[
        item(7170, "1.Alimentação e bebidas", 1, 0.10, 21.45),
        item(7445, "2.Habitação", 1, -0.20, 15.20),
    ],
    subitens=[item(1103, "1103.gasolina", 4, -2.00, 5.28)],
)


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for nome, r in CASOS.items():
        nota = compor_nota(r)
        (FIXTURES / f"{nome}.json").write_text(
            json.dumps(serializar(r), ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n",
        )
        (FIXTURES / f"{nome}.nota.txt").write_text(
            nota, encoding="utf-8", newline="\n",
        )
    print(f"{len(CASOS)} casos sinteticos gravados em {FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
