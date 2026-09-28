"""Versões de uma mesma divulgação.

A versão das 9h costuma sair sem os núcleos (e às vezes sem a difusão), que o
BCB calcula depois do IBGE. Quando esses dados chegam, gera-se uma nova versão
que **só acrescenta** os dados novos: o texto anterior fica idêntico.

Antes de coletar de novo, a versão atual é arquivada como
analise.vN.json / dados.vN.json / nota.vN.txt, e o verificador compara a
versão nova com a última arquivada (ver `verificar_acrescimo`).
"""
import re
import shutil
from pathlib import Path

from nucleo.montador import _fmt

# Campos do IPCA que o BCB publica depois do IBGE: podem faltar na primeira
# versão. O IPCA-15 não tem nenhum: o BCB não publica núcleos do IPCA-15 e a
# difusão é calculada dos subitens do IBGE (fontes/bcb.py, `enriquecer`).
CAMPOS_TARDIOS = {
    "nucleo_12m": 2,
    "nucleo_12m_anterior": 2,
    "difusao": 1,
    "difusao_anterior": 1,
}


def tem_dados_tardios(indicador: str) -> bool:
    return indicador == "IPCA"


# Campos do IBGE: não podem mudar entre versões do mesmo dia.
CAMPOS_FIXOS = ("variacao_mensal", "variacao_mensal_anterior", "acum_12m", "acum_12m_anterior")

_ARQUIVO_V = re.compile(r"analise\.v(\d+)\.json$")


def versoes_arquivadas(pasta: Path) -> list[int]:
    return sorted(int(m.group(1)) for p in pasta.glob("analise.v*.json")
                  if (m := _ARQUIVO_V.search(p.name)))


def versao_atual(pasta: Path) -> int:
    """Número da versão em analise.json: arquivadas + 1."""
    return len(versoes_arquivadas(pasta)) + 1


def arquivar(pasta: Path) -> int:
    """Copia a versão atual para *.vN e devolve N. analise.json continua no lugar,
    para receber só o acréscimo."""
    n = versao_atual(pasta)
    for nome, sufixo in (("analise", ".json"), ("dados", ".json"), ("nota", ".txt")):
        shutil.copyfile(pasta / f"{nome}{sufixo}", pasta / f"{nome}.v{n}{sufixo}")
    return n


def _chave(p: dict) -> tuple:
    return (p["texto"], tuple((f["id"], f["trecho"]) for f in p["fontes"]))


def verificar_acrescimo(dados_ant: dict, an_ant: dict, dados: dict, an: dict) -> list[str]:
    """A versão nova só pode acrescentar parágrafos com dados que faltavam antes."""
    falhas = []
    for k in CAMPOS_FIXOS:
        if dados.get(k) != dados_ant.get(k):
            falhas.append(f"dado do IBGE mudou entre versões: {k} ({dados_ant.get(k)} → {dados.get(k)})")
    for k in ("titulo", "data_divulgacao"):
        if an[k] != an_ant[k]:
            falhas.append(f"{k} mudou entre versões")
    for fid, f in an_ant["fontes"].items():
        if an["fontes"].get(fid) != f:
            falhas.append(f"fonte {fid} removida ou alterada")

    # Os parágrafos anteriores têm de aparecer intactos e na mesma ordem.
    novos, i = [], 0
    anteriores = [_chave(p) for p in an_ant["paragrafos"]]
    for n_par, p in enumerate(an["paragrafos"], 1):
        if i < len(anteriores) and _chave(p) == anteriores[i]:
            i += 1
        else:
            novos.append((n_par, p))
    if i < len(anteriores):
        falhas.append(
            f"parágrafo {i + 1} da versão anterior foi alterado ou removido: "
            f"{an_ant['paragrafos'][i]['texto'][:60]}…"
        )
        return falhas

    chegaram = {
        _fmt(dados[k], c).lstrip("-")
        for k, c in CAMPOS_TARDIOS.items()
        if dados_ant.get(k) is None and dados.get(k) is not None
    }
    if not chegaram:
        falhas.append("nenhum dado novo do BCB desde a versão anterior")
    if not novos:
        falhas.append("nenhum parágrafo acrescentado")
    for n_par, p in novos:
        numeros = {x.lstrip("-") for x in re.findall(r"-?\d+(?:,\d+)?", p["texto"])}
        if not numeros & chegaram:
            falhas.append(f"parágrafo {n_par} é novo mas não traz nenhum dado que acabou de chegar")
    return falhas
