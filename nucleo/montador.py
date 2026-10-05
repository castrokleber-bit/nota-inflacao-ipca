"""
Montador da nota de inflação — determinístico, sem IA.

Cada bloco_*() retorna str. compor_nota() monta o texto completo.
Nenhum token do texto é gerado por IA; cada campo rastreia a um
valor retornado pela API (ResultadoInflacao).
"""
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from fontes.modelo import ItemInflacao, ResultadoInflacao
from nucleo.impacto import grupos_relevantes, grupos_queda, top_subitem, top_subitem_queda


# ---------------------------------------------------------------------------
# Configuração de montagem (parametrizável; não hard-coded no texto)
# ---------------------------------------------------------------------------

@dataclass
class ConfigNota:
    top_n_grupos: int = 3
    threshold_grupos: float = 0.05   # p.p. mínimo para citar um grupo (alta)
    top_n_queda: int = 1
    threshold_queda: float = 0.05    # p.p. mínimo para citar deflação
    emoji_titulo: str = "\U0001f6a8"      # 🚨
    emoji_resultado: str = "\U0001f6a9"   # 🚩
    emoji_explicacao: str = "\U0001f534"  # 🔴
    emoji_acumulado: str = "\U0001f4c8"   # 📈
    emoji_nucleo: str = "\U0001f4c9"      # 📉
    emoji_difusao: str = "\U0001f4ca"     # 📊
    emoji_queda: str = "\U0001f7e2"       # 🟢 — usado nos parágrafos de deflação


# ---------------------------------------------------------------------------
# Tabelas e auxiliares de formatação
# ---------------------------------------------------------------------------

_MESES_ACENTUADOS = {
    "01": "janeiro", "02": "fevereiro", "03": "março",   "04": "abril",
    "05": "maio",    "06": "junho",     "07": "julho",   "08": "agosto",
    "09": "setembro","10": "outubro",   "11": "novembro","12": "dezembro",
}

# Exceções à regra de terminação de _artigo_de, pela primeira palavra inteira
# (sem acento). Comparação exata: o antigo teste por prefixo fazia "maca"
# capturar "macarrão" e publicava "da macarrão".
_ARTIGO_EXCECOES: dict[str, str] = {
    # femininos que não terminam em -a/-ção/-são/-dade/-gem
    "alface": "f", "ave": "f", "carne": "f", "couve": "f", "creche": "f",
    "gripe": "f", "higiene": "f", "internet": "f", "lingerie": "f",
    "maionese": "f", "manicure": "f", "mao": "f", "tv": "f",
    # masculinos terminados em -a
    "cha": "m", "cinema": "m", "dentista": "m", "fisioterapeuta": "m",
    "fuba": "m", "sutia": "m",
    # singulares terminados em -s (não são plural)
    "gas": "m", "lapis": "m", "onibus": "m", "tenis": "m",
}


def _fmt(v: float, decimais: int = 2) -> str:
    """Formata float com vírgula decimal e arredondamento HALF_UP."""
    factor = 10 ** decimais
    arredondado = math.floor(abs(v) * factor + 0.5) / factor
    if v < 0:
        arredondado = -arredondado
    return f"{arredondado:.{decimais}f}".replace(".", ",")


def _mes(mes_ref: str) -> str:
    """'202604' -> 'abril'"""
    return _MESES_ACENTUADOS[mes_ref[4:6]]


def _ano(mes_ref: str) -> str:
    return mes_ref[:4]


def _strip(nome: str) -> str:
    """'1.Alimentação e bebidas' -> 'Alimentação e bebidas'"""
    if nome and nome[0].isdigit():
        partes = nome.split(".", 1)
        if len(partes) == 2:
            return partes[1].strip()
    return nome


def _artigo_de(nome: str) -> str:
    """Heuristica de genero/numero para 'da(s)' / 'do(s)' antes do nome do item.
    O nucleo semantico do nome (que define genero/numero) e a primeira
    palavra, nao a ultima — ex.: "alimentação no domicílio" (fem.) ou
    "tubérculos, raízes e legumes" (masc. plural)."""
    nl = unicodedata.normalize("NFD", nome.lower())
    nl_ascii = "".join(c for c in nl if unicodedata.category(c) != "Mn")
    primeira = re.split(r"[ ,(]", nl_ascii.strip(), maxsplit=1)[0]
    if primeira in _ARTIGO_EXCECOES:
        return "da" if _ARTIGO_EXCECOES[primeira] == "f" else "do"
    plural = primeira.endswith("s") and len(primeira) > 2
    singular = primeira[:-1] if plural else primeira
    if singular in _ARTIGO_EXCECOES:
        feminino = _ARTIGO_EXCECOES[singular] == "f"
    else:
        feminino = singular.endswith(("a", "cao", "sao", "dade", "gem"))
    if feminino:
        return "das" if plural else "da"
    return "dos" if plural else "do"


def _direcao(v: float, alta: str = "alta", queda: str = "queda") -> str:
    return alta if v >= 0 else queda


def _unidades(v: float, decimais: int = 2) -> int:
    """O número como é exibido, em unidades da última casa: 4,39 -> 439.
    Toda comparação que vira texto usa isto, e não o float cru — senão
    4,391 contra 4,389 publica "4,39%, acima dos 4,39%"."""
    return int(_fmt(v, decimais).replace(",", ""))


def _movimento(v: float, alta: str = "alta", queda: str = "queda") -> str:
    """'alta de 0,67%' / 'queda de 0,32%' / 'estabilidade (0,00%)'.
    A palavra já diz o sentido, então o número sai sem sinal: nada de
    "queda de -0,32%"."""
    if _unidades(v) == 0:
        return "estabilidade (0,00%)"
    return f"{_direcao(v, alta, queda)} de {_fmt(abs(v))}%"


def _comparacao(atual: float, anterior: float, decimais: int = 2) -> str:
    """'acima' / 'abaixo' / 'igual', comparando os números como são exibidos."""
    a, b = _unidades(atual, decimais), _unidades(anterior, decimais)
    if a == b:
        return "igual"
    return "acima" if a > b else "abaixo"


def _em_linha_ou_relativo(v: float, ref: float, tol: float = 0.05) -> str:
    dif = _unidades(v) - _unidades(ref)
    if abs(dif) <= _unidades(tol):
        return "em linha com"
    return "acima de" if dif > 0 else "abaixo de"


def _pp_longo(v: float) -> str:
    """'0,29 ponto percentual (p.p.)' — para o primeiro grupo."""
    txt = _fmt(v)
    if abs(v) > 1:
        return f"{txt} pontos percentuais (p.p.)"
    return f"{txt} ponto percentual (p.p.)"


def _pp(v: float) -> str:
    """'0,16 p.p.' — versao curta para grupos subsequentes."""
    return f"{_fmt(v)} p.p."


# ---------------------------------------------------------------------------
# Variação de frases por trimestre — evita repetição entre divulgações
#
# Regra de indexação: _idx_var(mes_ref) → 0=Q1, 1=Q2, 2=Q3, 3=Q4.
# Índice 1 (Q2: abr-jun) = frases originais, preservando os golden files
# de IPCA abr/2026 e IPCA-15 mai/2026 sem alteração.
# ---------------------------------------------------------------------------

def _idx_var(mes_ref: str) -> int:
    """Retorna índice 0-3 com base no trimestre de mes_ref (AAAAMM)."""
    return (int(mes_ref[4:6]) - 1) // 3 % 4


# Variante cujas frases de queda não pressupõem um parágrafo de alta antes
# ("Entre os subgrupos, a queda..."): usada quando nenhum grupo subiu.
_IDX_NEUTRO = 2


# Abertura do parágrafo de alta (grupos de inflação — 1º grupo)
_ABR_ALTA = [
    "O desempenho do {ind} em {mes} foi marcado pela *{dir} do grupo {nome}*",  # Q1
    "O resultado de {mes} *reflete a {dir} do grupo {nome}*",                    # Q2
    "Em {mes}, destaca-se a *{dir} do grupo {nome}*",                            # Q3
    "*A {dir} do grupo {nome}* foi o principal fator do {ind} de {mes}",         # Q4
]

# Conector para o 2º grupo (singular)
_CON_SG = [
    "Na sequência, merece atenção o grupo",   # Q1
    "Em seguida, destaca-se o grupo",          # Q2
    "Também se destaca o grupo",               # Q3
    "Outro destaque é o grupo",                # Q4
]

# Conector para 2º e 3º grupos (plural)
_CON_PL = [
    "Na sequência, merecem atenção os grupos",   # Q1
    "Em seguida, destacam-se os grupos",          # Q2
    "Também se destacam os grupos",               # Q3
    "Outros destaques incluem os grupos",         # Q4
]

# Parágrafo do subgrupo de maior impacto positivo (nivel 2)
_SUBGRUPO_ALTA = [
    "No nível de subgrupos, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",                    # Q1
    "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), subgrupo de maior impacto no índice do mês.",  # Q2
    "Entre os subgrupos, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto do período.",      # Q3
    "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o subgrupo de maior impacto no mês.",           # Q4
]

# Parágrafo do subgrupo de maior deflação (nivel 2)
_SUBGRUPO_QUEDA = [
    "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária entre os subgrupos.",     # Q1
    "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), subgrupo de maior deflação no índice do mês.",      # Q2
    "Entre os subgrupos, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção sobre o índice.",                       # Q3
    "Como principal fator desinflacionário entre os subgrupos, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice.",     # Q4
]

# Parágrafo do item de maior impacto positivo (nivel 3)
_ITEM_ALTA = [
    "No nível de itens, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",               # Q1
    "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), item de maior impacto no índice do mês.",  # Q2
    "Entre os itens, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto do período.", # Q3
    "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o item de maior impacto no mês.",      # Q4
]

# Parágrafo do item de maior deflação (nivel 3)
_ITEM_QUEDA = [
    "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária entre os itens.",    # Q1
    "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), item de maior deflação no índice do mês.",     # Q2
    "Entre os itens, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção sobre o índice.",                      # Q3
    "Como principal fator desinflacionário entre os itens, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice.",    # Q4
]

# Parágrafo do subitem de maior impacto positivo (nivel 4)
_SUB_ALTA = [
    "No nível de subitens, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",              # Q1
    "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), subitem de maior impacto individual no índice do mês.",  # Q2
    "Entre os subitens, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto individual do período.",             # Q3
    "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o subitem de maior impacto individual no mês.",                  # Q4
]

# Abertura do parágrafo de queda — 1 grupo
_ABR_QUEDA_1 = [
    "Na direção oposta, o grupo *{nome}* recuou",                                           # Q1
    "Em sentido contrário, destaca-se a queda do grupo *{nome}*",                           # Q2
    "Como fator de contenção, o grupo *{nome}* registrou deflação",                         # Q3
    "Atuando como contraponto, o grupo *{nome}* pressionou o índice para baixo",            # Q4
]

# Parágrafo de queda — 2 grupos (texto completo, inclui os números)
_ABR_QUEDA_2 = [
    "Na direção oposta, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) pressionaram o índice para baixo.",                      # Q1
    "Em sentido contrário, destacam-se as quedas dos grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}), que contribuíram para reduzir o índice do mês.",  # Q2
    "Como fatores de contenção, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) exerceram pressão deflacionária sobre o índice.",                   # Q3
    "Em contraponto, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) contribuíram para reduzir o índice do mês.",                                   # Q4
]

# Parágrafo do subitem de maior deflação
_SUB_QUEDA = [
    "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária individual do período.",           # Q1
    "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), subitem de maior deflação individual no índice do mês.",     # Q2
    "Entre os subitens, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção individual sobre o índice.",                      # Q3
    "Como principal fator desinflacionário individual, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice do mês.",               # Q4
]


# ---------------------------------------------------------------------------
# Blocos individuais
# ---------------------------------------------------------------------------

def bloco_titulo(r: ResultadoInflacao, cfg: ConfigNota) -> str:
    mes = _mes(r.mes_ref).upper()
    return f"{cfg.emoji_titulo} *{r.indicador} {mes}/{_ano(r.mes_ref)}*"


def _mesmo_mes_ano_anterior(mes_ref: str) -> str:
    """'202605' -> '202505'"""
    return f"{int(mes_ref[:4]) - 1}{mes_ref[4:]}"


def bloco_resultado(r: ResultadoInflacao, cfg: ConfigNota) -> str:
    mes_ano_ant = _mesmo_mes_ano_anterior(r.mes_ref)

    # Comparação com mês anterior
    comp_anterior = (
        f"após {_movimento(r.variacao_mensal_anterior, 'avanço', 'recuo')} "
        f"em {_mes(r.mes_ant)}"
    )

    # Comparação com mesmo mês do ano anterior (quando disponível)
    if r.variacao_mesmo_mes_ano_anterior is not None:
        comp_ano_ant = (
            f"e {_movimento(r.variacao_mesmo_mes_ano_anterior)} "
            f"em {_mes(mes_ano_ant)} de {_ano(mes_ano_ant)}"
        )
        comparacoes = f"{comp_anterior} {comp_ano_ant}."
    else:
        comparacoes = f"{comp_anterior}."

    texto = (
        f"{cfg.emoji_resultado} O {r.indicador} registrou "
        f"*{_movimento(r.variacao_mensal)}* "
        f"em {_mes(r.mes_ref)} de {_ano(r.mes_ref)}, "
        f"{comparacoes}"
    )

    if r.projecao_focus is not None:
        rel_foc = _em_linha_ou_relativo(r.variacao_mensal, r.projecao_focus)
        texto += (
            f" O resultado ficou {rel_foc} a projeção da Pesquisa Focus "
            f"do Banco Central ({_fmt(r.projecao_focus)}%)."
        )

    return texto


def bloco_explicacao(r: ResultadoInflacao, cfg: ConfigNota) -> str:
    """Paragrafos dos grupos + subitens de destaque; pode conter \\n\\n interno.
    Ordem: inflação (grupos → subitem) → deflação (grupos → subitem).
    Frases variam por trimestre para evitar repetição entre divulgações.

    Sem grupo em alta relevante (mês de deflação), a queda abre a explicação
    com as frases de destaque principal, e os parágrafos de queda seguintes
    perdem o conector de contraste ("Em sentido contrário"), que não teria a
    que se opor."""
    idx = _idx_var(r.mes_ref)
    grupos = grupos_relevantes(
        r.grupos, top_n=cfg.top_n_grupos, threshold=cfg.threshold_grupos
    )
    gqs = grupos_queda(r.grupos, top_n=cfg.top_n_queda, threshold=cfg.threshold_queda)
    partes: list[str] = []

    if grupos:
        partes.append(_paragrafo_grupos(r, grupos, cfg.emoji_explicacao, idx))
        partes += _paragrafos_alta(r, cfg, idx)
        if gqs:
            partes.append(_paragrafo_queda_contraste(gqs, cfg, idx))
        idx_queda = idx
    else:
        if gqs:
            partes.append(_paragrafo_grupos(r, gqs, cfg.emoji_queda, idx))
        idx_queda = _IDX_NEUTRO

    partes += _paragrafos_queda(r, cfg, idx_queda)
    return "\n\n".join(partes)


def _paragrafo_grupos(
    r: ResultadoInflacao, grupos: list[ItemInflacao], emoji: str, idx: int
) -> str:
    """Abertura da explicação: o grupo principal e até dois seguintes."""
    g1 = grupos[0]
    g1n = _strip(g1.nome)
    dir_g1 = _direcao(g1.variacao)

    abertura = _ABR_ALTA[idx].format(
        ind=r.indicador, mes=_mes(r.mes_ref), dir=dir_g1, nome=g1n
    )
    texto = (
        f"{emoji} {abertura}, "
        f"com variação de {_fmt(g1.variacao)}% e impacto de "
        f"{_pp_longo(g1.impacto)} no índice do mês."
    )

    if len(grupos) == 2:
        g2 = grupos[1]
        g2n = _strip(g2.nome)
        texto += (
            f" {_CON_SG[idx]} {g2n}, "
            f"com variação de {_fmt(g2.variacao)}% "
            f"e impacto de {_pp(g2.impacto)}"
        )
    elif len(grupos) >= 3:
        g2, g3 = grupos[1], grupos[2]
        g2n = _strip(g2.nome)
        g3n = _strip(g3.nome)
        texto += (
            f" {_CON_PL[idx]} {g2n}, "
            f"com variação de {_fmt(g2.variacao)}% "
            f"e impacto de {_pp(g2.impacto)}, "
            f"e {g3n}, "
            f"com variação de {_fmt(g3.variacao)}% "
            f"e impacto de {_pp(g3.impacto)}"
        )
    return texto


def _paragrafos_alta(r: ResultadoInflacao, cfg: ConfigNota, idx: int) -> list[str]:
    """Subgrupo, item e subitem de maior impacto positivo."""
    partes = []

    # --- INFLAÇÃO: subgrupo de maior impacto (nivel 2) ---
    subgrupo = top_subitem(r.subitens, nivel=2)
    if subgrupo is not None:
        sgn = _strip(subgrupo.nome).lower()
        art_sg = _artigo_de(sgn)
        dir_sg = _direcao(subgrupo.variacao)
        partes.append(
            f"{cfg.emoji_explicacao} "
            + _SUBGRUPO_ALTA[idx].format(
                dir=dir_sg, art=art_sg, nome=sgn,
                var=_fmt(subgrupo.variacao), imp=_pp(subgrupo.impacto),
            )
        )

    # --- INFLAÇÃO: item de maior impacto (nivel 3) ---
    item = top_subitem(r.subitens, nivel=3)
    if item is not None:
        itn = _strip(item.nome).lower()
        art_it = _artigo_de(itn)
        dir_it = _direcao(item.variacao)
        partes.append(
            f"{cfg.emoji_explicacao} "
            + _ITEM_ALTA[idx].format(
                dir=dir_it, art=art_it, nome=itn,
                var=_fmt(item.variacao), imp=_pp(item.impacto),
            )
        )

    # --- INFLAÇÃO: subitem de maior impacto positivo (nivel 4) ---
    subitem = top_subitem(r.subitens, nivel=4)
    if subitem is not None:
        sn = _strip(subitem.nome).lower()
        art = _artigo_de(sn)
        dir_sub = _direcao(subitem.variacao)
        partes.append(
            f"{cfg.emoji_explicacao} "
            + _SUB_ALTA[idx].format(
                dir=dir_sub, art=art, nome=sn,
                var=_fmt(subitem.variacao), imp=_pp(subitem.impacto),
            )
        )

    return partes


def _paragrafo_queda_contraste(
    gqs: list[ItemInflacao], cfg: ConfigNota, idx: int
) -> str:
    """Grupos em queda, em contraste com o parágrafo de alta que os precede."""
    if len(gqs) == 1:
        gq = gqs[0]
        abertura_q = _ABR_QUEDA_1[idx].format(nome=_strip(gq.nome))
        return (
            f"{cfg.emoji_queda} {abertura_q}, "
            f"com variação de {_fmt(gq.variacao)}% e impacto de "
            f"{_pp(gq.impacto)} no índice do mês."
        )
    gq1, gq2 = gqs[0], gqs[1]
    return (
        f"{cfg.emoji_queda} "
        + _ABR_QUEDA_2[idx].format(
            n1=_strip(gq1.nome), v1=_fmt(gq1.variacao), i1=_pp(gq1.impacto),
            n2=_strip(gq2.nome), v2=_fmt(gq2.variacao), i2=_pp(gq2.impacto),
        )
    )


def _paragrafos_queda(r: ResultadoInflacao, cfg: ConfigNota, idx: int) -> list[str]:
    """Subgrupo, item e subitem de maior deflação."""
    partes = []

    # --- DEFLAÇÃO: subgrupo de maior queda (nivel 2) ---
    subgrupo_q = top_subitem_queda(r.subitens, nivel=2, threshold=cfg.threshold_queda)
    if subgrupo_q is not None:
        sqgn = _strip(subgrupo_q.nome).lower()
        art_sqg = _artigo_de(sqgn)
        partes.append(
            f"{cfg.emoji_queda} "
            + _SUBGRUPO_QUEDA[idx].format(
                art=art_sqg, nome=sqgn,
                var=_fmt(subgrupo_q.variacao), imp=_pp(subgrupo_q.impacto),
            )
        )

    # --- DEFLAÇÃO: item de maior queda (nivel 3) ---
    item_q = top_subitem_queda(r.subitens, nivel=3, threshold=cfg.threshold_queda)
    if item_q is not None:
        iqn = _strip(item_q.nome).lower()
        art_iq = _artigo_de(iqn)
        partes.append(
            f"{cfg.emoji_queda} "
            + _ITEM_QUEDA[idx].format(
                art=art_iq, nome=iqn,
                var=_fmt(item_q.variacao), imp=_pp(item_q.impacto),
            )
        )

    # --- DEFLAÇÃO: subitem de maior queda (nivel 4) ---
    subitem_q = top_subitem_queda(r.subitens, nivel=4, threshold=cfg.threshold_queda)
    if subitem_q is not None:
        sqn = _strip(subitem_q.nome).lower()
        art_q = _artigo_de(sqn)
        partes.append(
            f"{cfg.emoji_queda} "
            + _SUB_QUEDA[idx].format(
                art=art_q, nome=sqn,
                var=_fmt(subitem_q.variacao), imp=_pp(subitem_q.impacto),
            )
        )

    return partes


def bloco_acumulado(r: ResultadoInflacao, cfg: ConfigNota) -> str:
    rel = {"acima": "acima dos", "abaixo": "abaixo dos", "igual": "igual aos"}[
        _comparacao(r.acum_12m, r.acum_12m_anterior)
    ]
    return (
        f"{cfg.emoji_acumulado} O *{r.indicador} acumulado em 12 meses* "
        f"até {_mes(r.mes_ref)} ficou em *{_fmt(r.acum_12m)}%*, "
        f"{rel} {_fmt(r.acum_12m_anterior)}% "
        f"registrados nos 12 meses encerrados em {_mes(r.mes_ant)}."
    )


def bloco_nucleo(r: ResultadoInflacao, cfg: ConfigNota) -> Optional[str]:
    """Apenas para IPCA e quando nucleo_12m nao e None."""
    if r.indicador != "IPCA" or r.nucleo_12m is None:
        return None

    base = (
        f"{cfg.emoji_nucleo} *A média dos núcleos de inflação*, "
        f"que suavizam os efeitos de itens mais voláteis, "
        f"ficou em *{_fmt(r.nucleo_12m)}%* no acumulado em 12 meses "
        f"até {_mes(r.mes_ref)}"
    )

    # Sem o mês anterior não há comparação a fazer. O fallback antigo usava o
    # próprio nucleo_12m no lugar do ausente, o que publicava a frase
    # "ficou em X%, ligeiramente abaixo dos X%" — um número inventado para o
    # mês anterior, afirmado como fato. Mesma política do bloco de difusão:
    # havendo só um dado, informa-se só ele.
    if r.nucleo_12m_anterior is None:
        return base + "."

    rel = {
        "acima": "ligeiramente acima dos",
        "abaixo": "ligeiramente abaixo dos",
        "igual": "igual aos",
    }[_comparacao(r.nucleo_12m, r.nucleo_12m_anterior)]
    return (
        f"{base}, {rel} "
        f"{_fmt(r.nucleo_12m_anterior)}% no acumulado até {_mes(r.mes_ant)}."
    )


def bloco_difusao(r: ResultadoInflacao, cfg: ConfigNota) -> Optional[str]:
    if r.difusao is None:
        return None
    dif = _fmt(r.difusao, decimais=1)
    if r.difusao_anterior is not None:
        rel = {"acima": "acima do", "abaixo": "abaixo do", "igual": "igual ao"}[
            _comparacao(r.difusao, r.difusao_anterior, decimais=1)
        ]
        ant = _fmt(r.difusao_anterior, decimais=1)
        return (
            f"{cfg.emoji_difusao} O *índice de difusão*, que mede a disseminação "
            f"das altas de preços entre os itens que compõem o {r.indicador}, "
            f"ficou em *{dif}%*, {rel} registrado em "
            f"{_mes(r.mes_ant)} ({ant}%)."
        )
    return (
        f"{cfg.emoji_difusao} O *índice de difusão*, que mede a disseminação "
        f"das altas de preços entre os itens que compõem o {r.indicador}, "
        f"ficou em *{dif}%*."
    )


def bloco_link(r: ResultadoInflacao) -> Optional[str]:
    if not r.url_ibge:
        return None
    return f"Notícia: {r.url_ibge}"


# ---------------------------------------------------------------------------
# Composição final
# ---------------------------------------------------------------------------

def compor_nota(
    r: ResultadoInflacao,
    cfg: Optional[ConfigNota] = None,
) -> str:
    """
    Monta o texto completo da nota de WhatsApp.
    Retorna string com blocos separados por linha em branco.
    Determinístico: nenhum token gerado por IA.
    """
    if cfg is None:
        cfg = ConfigNota()

    blocos = [
        bloco_titulo(r, cfg),
        bloco_resultado(r, cfg),
        bloco_explicacao(r, cfg),
        bloco_acumulado(r, cfg),
        bloco_nucleo(r, cfg),
        bloco_difusao(r, cfg),
        bloco_link(r),
    ]

    return "\n\n".join(b for b in blocos if b)
