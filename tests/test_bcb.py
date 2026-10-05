"""
Gates G3 e G4 — valida fontes BCB.

G3: difusao IPCA abr/2026 = 65,3% (SGS 21379)
    media nucleos 12m abr/2026 = 4,38% (±0,01 p.p.) — combo MS+EX0+EX3+DP

G4: difusao IPCA-15 mai/2026 = 65,1% (calculada dos subitens IBGE)
"""
import pytest
from fontes.bcb import media_nucleos_12m, enriquecer, _serie_mensal, _SGS_DIFUSAO_IPCA
from fontes.ibge import buscar_resultado
from nucleo.impacto import calcular_difusao


@pytest.mark.integration
def test_gate_g3_difusao_ipca_abril2026():
    """Difusão IPCA abr/2026 via SGS 21379 deve ser ~65,3%."""
    val = _serie_mensal(_SGS_DIFUSAO_IPCA, "202604", "202604").get("202604")
    print(f"\nDifusao IPCA abr/2026 (SGS 21379): {val}")
    assert val is not None, "Serie SGS 21379 nao retornou valor"
    assert val == pytest.approx(65.3, abs=0.1), (
        f"Difusao esperada ~65.3%, obtida {val}%"
    )


@pytest.mark.integration
def test_gate_g3_media_nucleos_abril2026():
    """Media dos nucleos 12m abr/2026 deve ser 4,38% (±0,01 p.p.)."""
    media = media_nucleos_12m("202604")
    print(f"\nMedia nucleos 12m abr/2026 (MS+EX0+EX3+DP): {media:.4f}%")
    assert media is not None, "Nenhum nucleo retornou valor"
    assert media == pytest.approx(4.38, abs=0.01), (
        f"Media esperada ~4.38%, obtida {media:.4f}%"
    )


@pytest.mark.integration
def test_gate_g4_difusao_ipca15_maio2026():
    """Difusao IPCA-15 mai/2026 calculada dos subitens IBGE deve ser ~65,1%."""
    r = buscar_resultado("IPCA-15", "202605")
    difusao = calcular_difusao(r.subitens, nivel_min=4)
    print(f"\nDifusao IPCA-15 mai/2026 (IBGE subitens nivel>=4): {difusao:.2f}%")
    assert difusao is not None
    assert difusao == pytest.approx(65.1, abs=0.1), (
        f"Difusao esperada ~65.1%, obtida {difusao:.2f}%"
    )


@pytest.mark.integration
def test_enriquecer_ipca_completo():
    """enriquecer() preenche todos os campos BCB do IPCA abr/2026."""
    r = buscar_resultado("IPCA", "202604")
    enriquecer(r)

    print(f"\nIPCA abr/2026 apos enriquecer():")
    print(f"  difusao:            {r.difusao}")
    print(f"  difusao_anterior:   {r.difusao_anterior}")
    print(f"  nucleo_12m:         {r.nucleo_12m:.4f}%" if r.nucleo_12m else "  nucleo_12m: None")
    print(f"  nucleo_12m_ant:     {r.nucleo_12m_anterior:.4f}%" if r.nucleo_12m_anterior else "  nucleo_12m_ant: None")

    assert r.difusao is not None
    assert r.difusao_anterior is not None
    assert r.nucleo_12m is not None
    assert r.nucleo_12m == pytest.approx(4.38, abs=0.01)


@pytest.mark.integration
def test_enriquecer_ipca15_difusao():
    """enriquecer() calcula difusao para IPCA-15; nucleo fica None."""
    r = buscar_resultado("IPCA-15", "202605")
    enriquecer(r)

    print(f"\nIPCA-15 mai/2026 apos enriquecer():")
    print(f"  difusao:   {r.difusao}")
    print(f"  nucleo:    {r.nucleo_12m}")

    assert r.difusao is not None
    assert r.difusao == pytest.approx(65.1, abs=0.1)
    assert r.nucleo_12m is None


@pytest.mark.integration
def test_enriquecer_mes_sem_dado_retorna_none():
    """Para mes futuro inexistente, enriquecer() deixa campos None sem excepcao."""
    r = buscar_resultado("IPCA", "202604")
    r.mes_ref = "209901"  # data no futuro distante
    r.mes_ant = "208912"
    enriquecer(r)  # nao deve levantar excecao
    # campos ficam None silenciosamente
    assert r.difusao is None
    assert r.nucleo_12m is None


# ---------------------------------------------------------------------------
# Regressao: media dos nucleos e tudo-ou-nada (nao faz rede)
# ---------------------------------------------------------------------------

def _serie_fixa(mes_fim: str, valor: float, meses: int = 13) -> dict:
    from fontes.bcb import _mes_menos
    return {_mes_menos(mes_fim, n): valor for n in range(meses)}


def test_media_nucleos_retorna_none_se_uma_serie_falhar(monkeypatch):
    """
    Uma serie que nao responde nao pode virar media parcial.

    Com 4 das 5 series a media desloca ate 0,09 p.p. (12m ate mar/2026:
    4,39% com as 5, 4,44% sem a DP) e a nota sairia com o numero errado sem
    nenhum sinal de erro. O bloco de nucleo e opcional — omitir e seguro.
    """
    import fontes.bcb as bcb

    def falha_so_na_dp(codigo, ini, fim):
        return {} if codigo == bcb._NUCLEOS["DP"] else _serie_fixa(fim, 0.3)

    monkeypatch.setattr(bcb, "_serie_mensal", falha_so_na_dp)
    assert bcb.media_nucleos_12m("202604") is None


def test_media_nucleos_calcula_com_as_cinco_series(monkeypatch):
    """Com as 5 series presentes, a media e a aritmetica simples dos 12m."""
    import fontes.bcb as bcb

    mensal = {"MS": 0.30, "EX0": 0.40, "DP": 0.20, "EX3": 0.50, "P55": 0.35}
    por_codigo = {bcb._NUCLEOS[k]: v for k, v in mensal.items()}
    monkeypatch.setattr(bcb, "_serie_mensal", lambda c, i, f: _serie_fixa(f, por_codigo[c]))

    acum = [((1 + v / 100) ** 12 - 1) * 100 for v in mensal.values()]
    assert bcb.media_nucleos_12m("202604") == pytest.approx(sum(acum) / 5, abs=1e-4)


def test_nucleo_mes_corrente_ausente_mantem_anterior(monkeypatch):
    """
    Uma requisicao de 13 meses serve aos dois meses. Se o BCB ainda nao
    publicou o mes corrente, so ele vira None; o anterior continua.
    """
    import fontes.bcb as bcb

    def sem_mes_corrente(codigo, ini, fim):
        s = _serie_fixa(fim, 0.3)
        s.pop(fim)
        return s

    monkeypatch.setattr(bcb, "_serie_mensal", sem_mes_corrente)
    medias = bcb._medias_nucleos_12m(["202604", "202603"])
    assert medias["202604"] is None
    assert medias["202603"] is not None


def test_uma_requisicao_por_serie(monkeypatch):
    """IPCA: 1 requisicao de difusao + 1 por nucleo, cobrindo os 13 meses."""
    import fontes.bcb as bcb
    from fontes.modelo import ResultadoInflacao

    chamadas = []

    def falso(codigo, ini, fim):
        chamadas.append((codigo, ini, fim))
        return []

    monkeypatch.setattr(bcb, "_sgs_fetch", falso)
    r = ResultadoInflacao("IPCA", "202604", "202603", 0.67, 0.88, 4.39, 4.14, [], [])
    enriquecer(r)
    assert len(chamadas) == 6
    assert (bcb._NUCLEOS["MS"], "01/04/2025", "01/04/2026") in chamadas
    assert (bcb._SGS_DIFUSAO_IPCA, "01/03/2026", "01/04/2026") in chamadas


def test_registro_de_outro_mes_nao_e_aceito(monkeypatch):
    """O valor fica no mes que o registro declara, nunca no mes pedido."""
    import fontes.bcb as bcb

    monkeypatch.setattr(bcb, "_sgs_fetch", lambda c, i, f: [
        {"data": "01/02/2026", "valor": "61.0"},
        {"data": "01/03/2026", "valor": "67.4"},
    ])
    assert bcb._serie_mensal(21379, "202603", "202604") == {"202603": 67.4}


def test_resposta_fora_do_formato_vira_vazio(monkeypatch):
    """Um objeto JSON (em vez de lista) nao pode derrubar a nota."""
    import fontes.bcb as bcb

    class Resp:
        status_code = 200

        def json(self):
            return {"erro": "servico indisponivel"}

    monkeypatch.setattr(bcb.httpx, "get", lambda *a, **k: Resp())
    assert bcb._sgs_fetch(21379, "01/04/2026", "01/04/2026") == []
