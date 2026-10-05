"""
Captura, a partir das APIs reais, os dados de entrada e a nota que o Python
produz — para que o gate em Node compare o JS contra exatamente o mesmo input.

Roda sob demanda (não faz parte do pytest), porque depende de rede:

    python tests/equivalencia/dump_python.py

Grava em tests/equivalencia/fixtures/:
    <caso>.json      → ResultadoInflacao serializado (entrada do montador)
    <caso>.nota.txt  → nota produzida pelo montador Python (saída esperada)

O par (entrada, saída) congela o comportamento do Python num instante. O gate
JS consome os dois: reconstrói o objeto do .json e exige que sua nota seja
idêntica ao .nota.txt, byte a byte. Assim uma divergência de port aparece
isolada de revisões de série que o BCB faça depois.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fontes.ibge import buscar_resultado  # noqa: E402
from fontes.bcb import enriquecer  # noqa: E402
from nucleo.montador import compor_nota  # noqa: E402
from fontes.modelo import serializar  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

CASOS = [
    ("ipca_202604", "IPCA", "202604"),
    ("ipca15_202605", "IPCA-15", "202605"),
]


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for nome, indicador, mes in CASOS:
        print(f"buscando {indicador} {mes} ...", flush=True)
        r = buscar_resultado(indicador, mes)
        enriquecer(r)
        nota = compor_nota(r)

        # newline="\n" é obrigatório: sem ele o Python traduz \n para \r\n no
        # Windows e o arquivo deixa de ser byte a byte igual à nota em memória.
        # O gate em Node lê os bytes crus, e o CI do GitHub roda em Linux (LF),
        # então gravar CRLF faria o mesmo teste passar aqui e falhar lá.
        (FIXTURES / f"{nome}.json").write_text(
            json.dumps(serializar(r), ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        (FIXTURES / f"{nome}.nota.txt").write_text(
            nota, encoding="utf-8", newline="\n"
        )

        alerta = "" if r.nucleo_12m is not None or indicador != "IPCA" else \
            "   [aviso] nucleo_12m veio None — alguma serie do SGS falhou"
        print(f"  ok: {len(r.grupos)} grupos, {len(r.subitens)} subitens{alerta}")
    print(f"\nfixtures em {FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
