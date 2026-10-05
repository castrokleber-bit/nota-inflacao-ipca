"""Coleta os dados determinísticos que servem de insumo à leitura por IA.

    python -m analise.coletar IPCA 202608
    python -m analise.coletar IPCA 202608 --atualizar   # nova versão (núcleos do BCB)

Grava em analise/saida/<indicador>_<AAAAMM>/:
    dados.json      → ResultadoInflacao serializado (mesmo formato das fixtures)
    nota.txt        → nota determinística do montador (insumo, não é publicada)
    historico.json  → variação dos subitens nos 3 meses anteriores e no mesmo
                      mês do ano anterior, para dar contexto aos movimentos

e imprime os rankings de impacto que orientam a pesquisa das causas.

Com --atualizar, arquiva a versão atual (analise/versoes.py) antes de coletar
de novo, para a nova versão só acrescentar os dados que o BCB publicou depois.
"""
import json
import sys
from pathlib import Path

from fontes.bcb import enriquecer
from fontes.ibge import buscar_resultado, buscar_variacoes
from fontes.modelo import serializar
from nucleo.impacto import calcular_impacto
from nucleo.montador import compor_nota
from analise.versoes import CAMPOS_TARDIOS, arquivar, tem_dados_tardios

SAIDA = Path(__file__).parent / "saida"


def pasta_do_caso(indicador: str, mes_ref: str) -> Path:
    return SAIDA / f"{indicador.lower().replace('-', '')}_{mes_ref}"


def _mes_menos(mes_ref: str, n: int) -> str:
    total = int(mes_ref[:4]) * 12 + int(mes_ref[4:]) - 1 - n
    return f"{total // 12}{total % 12 + 1:02d}"


def main(indicador: str, mes_ref: str, atualizar: bool = False) -> None:
    pasta = pasta_do_caso(indicador, mes_ref)
    pasta.mkdir(parents=True, exist_ok=True)
    if atualizar and not tem_dados_tardios(indicador):
        sys.exit(f"{indicador} não tem atualização: não há dado do BCB publicado depois do IBGE")
    tem_analise = (pasta / "analise.json").exists()
    if atualizar and not tem_analise:
        sys.exit("nada para atualizar: não há analise.json neste caso")
    if not atualizar and tem_analise:
        sys.exit("este caso já tem analise.json: use --atualizar para gerar nova versão")

    r = buscar_resultado(indicador, mes_ref)
    enriquecer(r)

    if atualizar:
        # Só abre versão nova se o BCB publicou algo que faltava; senão nada muda.
        antes = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
        agora = serializar(r)
        chegaram = [k for k in CAMPOS_TARDIOS if antes.get(k) is None and agora.get(k) is not None]
        if not chegaram:
            faltam = [k for k in CAMPOS_TARDIOS if agora.get(k) is None]
            sys.exit(f"nenhum dado novo do BCB ainda (faltam: {', '.join(faltam)}); nada foi alterado")
        print(f"chegaram: {', '.join(chegaram)} · versão {arquivar(pasta)} arquivada")

    nota = compor_nota(r)
    (pasta / "nota.txt").write_text(nota, encoding="utf-8", newline="\n")
    (pasta / "dados.json").write_text(
        json.dumps(serializar(r), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # Histórico só para contexto; um mês que falhe fica de fora, sem aproximação.
    historico = {}
    for n in (1, 2, 3, 12):
        mes = _mes_menos(mes_ref, n)
        try:
            historico[mes] = buscar_variacoes(indicador, mes)
        except Exception as e:  # noqa: BLE001
            print(f"aviso: histórico de {mes} indisponível ({e})", file=sys.stderr)
    (pasta / "historico.json").write_text(
        json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    itens = [
        (i.nome, i.variacao, calcular_impacto(i.variacao, i.peso))
        for i in r.subitens
        if i.variacao is not None and i.peso
    ]
    itens.sort(key=lambda x: x[2])
    meses_h = sorted(historico)

    def linha(nome, var, imp):
        hist = " ".join(
            f"{m[4:]}/{m[2:4]}:{historico[m][nome]:6.2f}" if nome in historico[m] else f"{m[4:]}/{m[2:4]}:   n/d"
            for m in meses_h
        )
        return f"{nome[:45]:45s} var {var:7.2f} imp {imp:6.3f} | {hist}"

    print(nota)
    print("\n--- maiores impactos positivos ---")
    for x in itens[::-1][:15]:
        print(linha(*x))
    print("--- maiores impactos negativos ---")
    for x in itens[:15]:
        print(linha(*x))
    print(f"\narquivos em {pasta}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--atualizar" in sys.argv[3:])
