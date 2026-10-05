"""Testes da barreira entre a redação da IA e a publicação (analise/)."""
import copy
import json
from pathlib import Path

import pytest

from analise.montar_pagina import montar
from analise.verificar import verificar

FIX = Path(__file__).parent / "equivalencia" / "fixtures"
DADOS = json.loads((FIX / "ipca_202604.json").read_text(encoding="utf-8"))
NOTA = (FIX / "ipca_202604.nota.txt").read_text(encoding="utf-8")

ANALISE = {
    "data_divulgacao": "2026-05-12",
    "titulo": "🚨 *IPCA ABRIL/2026*",
    "paragrafos": [
        {
            "texto": "🚩 O IPCA subiu *0,67%* em abril, puxado pela gasolina (1,86%), "
                     "após reajuste de 5% nas refinarias.",
            "fontes": [{"id": "fonte_a", "trecho": "reajuste de 5% nas refinarias"}],
        },
        {"texto": "📈 Em 12 meses, *4,39%*.", "fontes": []},
        {"texto": "📉 Média dos núcleos em *4,38%*.", "fontes": []},
        {"texto": "📊 Difusão de *65,3%*.", "fontes": []},
    ],
    "fontes": {"fonte_a": {"nome": "Fonte A", "data": "2026-05-12", "url": "https://exemplo.org/a"}},
}


def _falhas(analise, historico=None):
    return verificar(DADOS, NOTA, historico or {}, analise)


def test_texto_valido_passa():
    assert _falhas(ANALISE) == []


def test_numero_sem_origem_falha():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["texto"] += " O diesel subiu 3,21%."
    assert _falhas(a) == ["parágrafo 1: número sem origem (3,21)"]


def test_numero_de_fonte_so_vale_no_paragrafo_que_a_cita():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][1]["texto"] += " Refinarias: 5%."
    assert _falhas(a) == ["parágrafo 2: número sem origem (5)"]


def test_historico_da_api_conta_como_origem():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["texto"] += " Em março, 2,47%."
    assert _falhas(a) != []
    assert _falhas(a, {"202603": {"5104001.Gasolina": 2.47}}) == []


@pytest.mark.parametrize("par, valor, nome", [
    (0, "*0,67%*", "variação mensal"),
    (1, "*4,39%*", "acumulado 12m"),
    (2, "*4,38%*", "média dos núcleos"),
    (3, "*65,3%*", "difusão"),
])
def test_obrigatorio_ausente_falha(par, valor, nome):
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][par]["texto"] = a["paragrafos"][par]["texto"].replace(valor, "")
    assert any(f.startswith(f"obrigatório ausente: {nome}") for f in _falhas(a))


def test_obrigatorio_que_a_api_nao_devolveu_nao_e_exigido():
    dados = dict(DADOS, nucleo_12m=None)
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][2]["texto"] = "📉 Sem núcleo."
    assert verificar(dados, NOTA, {}, a) == []


def test_fonte_posterior_a_divulgacao_falha():
    a = copy.deepcopy(ANALISE)
    a["fontes"]["fonte_a"]["data"] = "2026-05-13"
    assert _falhas(a) == ["parágrafo 1: fonte fonte_a (2026-05-13) é posterior à divulgação"]


def test_fonte_sem_cadastro_falha():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["fontes"][0]["id"] = "fantasma"
    assert "parágrafo 1: fonte sem cadastro (fantasma)" in _falhas(a)


def test_datas_no_texto_nao_contam_como_numero():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][1]["texto"] += " Copom em 17/06, vigência desde 1º de maio."
    assert _falhas(a) == []


def test_pagina_sem_assinatura_nao_tem_bloco_de_assinatura():
    html = montar(DADOS, NOTA, ANALISE)
    assert 'class="assinatura"' not in html


def test_assinatura_fecha_o_texto_copiavel():
    html = montar(DADOS, NOTA, ANALISE, "Linha 1\nLinha 2")
    assert html.index('<p class="assinatura">Linha 1<br>Linha 2</p>') > html.index("Difusão de")
    assert "65,3%*.\n\nLinha 1\nLinha 2</pre>" in html


# ── Versões: a das 9h sai sem núcleos; a posterior só acrescenta ──────────
from datetime import datetime  # noqa: E402

from analise.versoes import verificar_acrescimo  # noqa: E402

DADOS_V1 = dict(DADOS, nucleo_12m=None, nucleo_12m_anterior=None)
ANALISE_V1 = copy.deepcopy(ANALISE)
del ANALISE_V1["paragrafos"][2]  # sem o parágrafo dos núcleos


def test_versao_das_9h_sem_nucleo_passa():
    assert verificar(DADOS_V1, NOTA, {}, ANALISE_V1) == []


def test_versao_com_nucleo_acrescentado_passa():
    assert verificar_acrescimo(DADOS_V1, ANALISE_V1, DADOS, ANALISE) == []


def test_alterar_texto_anterior_falha():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][1]["texto"] = "📈 Em 12 meses, a inflação ficou em *4,39%*."
    falhas = verificar_acrescimo(DADOS_V1, ANALISE_V1, DADOS, a)
    assert any("foi alterado ou removido" in f for f in falhas)


def test_remover_paragrafo_anterior_falha():
    a = copy.deepcopy(ANALISE)
    del a["paragrafos"][0]
    assert any("alterado ou removido" in f for f in verificar_acrescimo(DADOS_V1, ANALISE_V1, DADOS, a))


def test_paragrafo_novo_sem_dado_novo_falha():
    a = copy.deepcopy(ANALISE)
    a["paragrafos"].append({"texto": "🧭 Comentário extra de 0,67%.", "fontes": []})
    falhas = verificar_acrescimo(DADOS_V1, ANALISE_V1, DADOS, a)
    assert falhas == ["parágrafo 5 é novo mas não traz nenhum dado que acabou de chegar"]


def test_sem_dado_novo_do_bcb_falha():
    falhas = verificar_acrescimo(DADOS, ANALISE_V1, DADOS, ANALISE)
    assert "nenhum dado novo do BCB desde a versão anterior" in falhas


def test_dado_do_ibge_mudou_entre_versoes_falha():
    dados = dict(DADOS, acum_12m=4.40)
    falhas = verificar_acrescimo(DADOS_V1, ANALISE_V1, dados, ANALISE)
    assert any(f.startswith("dado do IBGE mudou entre versões: acum_12m") for f in falhas)


def test_fonte_anterior_removida_falha():
    a = copy.deepcopy(ANALISE)
    a["fontes"]["fonte_a"]["url"] = "https://exemplo.org/outra"
    assert "fonte fonte_a removida ou alterada" in verificar_acrescimo(DADOS_V1, ANALISE_V1, DADOS, a)


def test_pagina_avisa_dado_pendente_e_mostra_versao():
    html = montar(DADOS_V1, NOTA, ANALISE_V1, versao=1, gerado_em=datetime(2026, 5, 12, 9, 12))
    assert "Ainda não divulgado pelo BCB: média dos núcleos." in html
    assert "versão 1 · 12/05/2026 às 09:12" in html
    html2 = montar(DADOS, NOTA, ANALISE, versao=2)
    assert 'class="pendente"' not in html2
    assert "versão 2 ·" in html2


def test_ipca15_nao_espera_dado_do_bcb():
    from analise.montar_pagina import pendentes
    assert pendentes(dict(DADOS, indicador="IPCA-15", nucleo_12m=None, difusao=65.1)) == []
    assert pendentes(dict(DADOS, indicador="IPCA", nucleo_12m=None)) == ["média dos núcleos"]


def test_sinal_trocado_falha():
    """Regressao: o sinal era descartado, e "-0,67%" passava com a API em +0,67."""
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["texto"] = a["paragrafos"][0]["texto"].replace("0,67", "-0,67")
    assert any("-0,67" in f for f in verificar(DADOS, NOTA, {}, a))


def test_ano_fora_da_lista_antiga_nao_conta_como_numero():
    """Anos saiam de uma lista fixa (2024-2027); 2028 passaria a falhar."""
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["texto"] += " Maior alta desde 2028."
    assert verificar(DADOS, NOTA, {}, a) == []


def test_doze_solto_precisa_de_origem():
    """Só a janela "12 meses" é ignorada; um 12 qualquer precisa de origem."""
    a = copy.deepcopy(ANALISE)
    a["paragrafos"][0]["texto"] += " Subiu em 12 capitais."
    assert any("(12)" in f for f in verificar(DADOS, NOTA, {}, a))


def test_url_de_fonte_que_nao_e_http_e_neutralizada():
    a = copy.deepcopy(ANALISE)
    a["fontes"]["fonte_a"]["url"] = "javascript:alert(1)"
    a["paragrafos"][0]["fontes"] = [{"id": "fonte_a", "trecho": ""}]
    html = montar(DADOS, NOTA, a)
    assert "javascript:" not in html
    assert 'href="#"' in html
