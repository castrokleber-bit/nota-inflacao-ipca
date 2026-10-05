"""Barreira entre a redação da IA e a publicação.

    python -m analise.verificar IPCA 202608

Falha (exit 1) se:
1. um número do texto não aparece nos dados da API (nota, grupos, subitens,
   histórico) nem no trecho de uma fonte citada pelo próprio parágrafo;
2. faltar um dos números obrigatórios — variação mensal, acumulado 12m,
   média dos núcleos e difusão — quando a API os devolveu;
3. uma fonte citada não estiver cadastrada ou for posterior à divulgação;
4. havendo versão anterior do mesmo dia, o texto novo não for o anterior
   intacto mais parágrafos com os dados que o BCB acabou de publicar.
"""
import json
import re
import sys

from nucleo.impacto import calcular_impacto
from nucleo.montador import _fmt  # mesmo arredondamento HALF_UP da nota

NUM = re.compile(r"-?\d+(?:\.\d{3})*(?:,\d+)?")
# Datas, a janela "12 meses"/"12m" e anos não são dados: saem antes da busca.
DATA = re.compile(
    r"\b\d{1,2}/\d{2}(?:/\d{4})?\b|\b\d{1,2}º|\b12\s*(?:meses|m)\b|\b(?:19|20)\d{2}\b(?!,\d)"
)


def _sem_sinal(conj) -> set[str]:
    return {x.lstrip("-") for x in conj}


def _tem_origem(n: str, permitidos: set[str]) -> bool:
    """Número sem sinal casa pelo valor absoluto ("queda de 0,32%" vale para
    -0,32). Com sinal explícito, o sinal também tem de bater: "-0,32%" no
    texto quando a API deu +0,32 é número trocado, não redação."""
    if n.startswith("-"):
        return n in permitidos
    return n in _sem_sinal(permitidos)


def numeros_da_api(dados: dict, nota: str, historico: dict) -> set[str]:
    api = set(NUM.findall(DATA.sub("", nota)))
    for k in ("variacao_mensal", "variacao_mensal_anterior", "acum_12m", "acum_12m_anterior",
              "nucleo_12m", "nucleo_12m_anterior", "variacao_mesmo_mes_ano_anterior"):
        if dados.get(k) is not None:
            api.add(_fmt(dados[k]))
    for k in ("difusao", "difusao_anterior"):
        if dados.get(k) is not None:
            api.add(_fmt(dados[k], 1))
    for i in dados["grupos"] + dados["subitens"]:
        if i["variacao"] is None:
            continue
        api.add(_fmt(i["variacao"]))
        if i["peso"]:
            api.add(_fmt(calcular_impacto(i["variacao"], i["peso"])))
    for mes in historico.values():
        api |= {_fmt(v) for v in mes.values()}
    return api


def verificar(dados: dict, nota: str, historico: dict, analise: dict) -> list[str]:
    api = numeros_da_api(dados, nota, historico)
    falhas = []
    texto_total = analise["titulo"]
    for n_par, p in enumerate(analise["paragrafos"], 1):
        texto_total += "\n" + p["texto"]
        permitidos = set(api)
        for f in p["fontes"]:
            permitidos |= set(NUM.findall(f["trecho"]))
            fonte = analise["fontes"].get(f["id"])
            if fonte is None:
                falhas.append(f"parágrafo {n_par}: fonte sem cadastro ({f['id']})")
            elif fonte["data"] > analise["data_divulgacao"]:
                falhas.append(
                    f"parágrafo {n_par}: fonte {f['id']} ({fonte['data']}) é posterior à divulgação"
                )
        for n in NUM.findall(DATA.sub("", p["texto"])):
            if not _tem_origem(n, permitidos):
                falhas.append(f"parágrafo {n_par}: número sem origem ({n})")

    obrigatorios = {
        "variação mensal": (dados.get("variacao_mensal"), 2),
        "acumulado 12m": (dados.get("acum_12m"), 2),
        "média dos núcleos": (dados.get("nucleo_12m"), 2),
        "difusão": (dados.get("difusao"), 1),
    }
    presentes = _sem_sinal(NUM.findall(texto_total))
    for nome, (v, c) in obrigatorios.items():
        if v is not None and _fmt(v, c).lstrip("-") not in presentes:
            falhas.append(f"obrigatório ausente: {nome} ({_fmt(v, c)})")
    return falhas


def main(indicador: str, mes_ref: str) -> int:
    from analise.coletar import pasta_do_caso

    from analise.versoes import verificar_acrescimo, versoes_arquivadas

    pasta = pasta_do_caso(indicador, mes_ref)

    def ler(nome):
        return json.loads((pasta / nome).read_text(encoding="utf-8"))

    dados, analise = ler("dados.json"), ler("analise.json")
    falhas = verificar(
        dados, (pasta / "nota.txt").read_text(encoding="utf-8"), ler("historico.json"), analise
    )
    if anteriores := versoes_arquivadas(pasta):
        n = anteriores[-1]
        falhas += verificar_acrescimo(ler(f"dados.v{n}.json"), ler(f"analise.v{n}.json"), dados, analise)
    if falhas:
        print("FALHOU:")
        for x in falhas:
            print("  ", x)
        return 1
    print("OK: números com origem, obrigatórios presentes, fontes até a divulgação.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
