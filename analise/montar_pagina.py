"""Monta a página do artifact.

    python -m analise.montar_pagina IPCA 202608

Lê de analise/saida/<caso>/: analise.json (texto único, já aprovado por
verificar.py), dados.json e nota.txt (nota determinística, só para
conferência). Grava pagina.html na mesma pasta.

Assinatura: se existir analise/assinatura.local.txt, suas linhas fecham a
nota. O arquivo fica fora do git (ver .gitignore): o repositório e o site
não carregam marca institucional.
"""
import json
import re
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

from analise.versoes import tem_dados_tardios
from nucleo.montador import _fmt as fmt  # mesmo arredondamento HALF_UP da nota

ASSINATURA = Path(__file__).parent / "assinatura.local.txt"


def ler_assinatura() -> str | None:
    if not ASSINATURA.exists():
        return None
    texto = ASSINATURA.read_text(encoding="utf-8").strip()
    return texto or None


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def negrito(t):
    """Converte o *negrito* do WhatsApp em <strong>, depois de escapar o HTML."""
    return re.sub(r"\*([^*]+)\*", r"<strong>\1</strong>", escape(t))


def url_segura(url: str) -> str:
    """Só http(s): a URL vem de texto redigido por IA, e um `javascript:` no
    href rodaria ao clicar, mesmo escapado."""
    return url if re.match(r"https?://", url, re.IGNORECASE) else "#"


def pendentes(dados: dict) -> list[str]:
    """Dados do BCB que ainda não saíram (núcleos e difusão vêm depois do IBGE).
    No IPCA-15 não há o que esperar: núcleo não existe e a difusão sai com o IBGE."""
    if not tem_dados_tardios(dados["indicador"]):
        return []
    faltam = []
    if dados.get("nucleo_12m") is None:
        faltam.append("média dos núcleos")
    if dados.get("difusao") is None:
        faltam.append("índice de difusão")
    return faltam


def montar(
    dados: dict,
    nota: str,
    an: dict,
    assinatura: str | None = None,
    versao: int = 1,
    gerado_em: datetime | None = None,
) -> str:
    mes_nome = MESES[int(dados["mes_ref"][4:]) - 1]
    ano = dados["mes_ref"][:4]
    d_div = date.fromisoformat(an["data_divulgacao"]).strftime("%d/%m/%Y")
    gerado_em = gerado_em or datetime.now()
    carimbo = f"versão {versao} · {gerado_em.strftime('%d/%m/%Y às %H:%M')}"
    faltam = pendentes(dados)
    aviso_pendente = (
        f'<p class="pendente">Ainda não divulgado pelo BCB: {" e ".join(faltam)}. '
        "Quando sair, esta nota ganha o dado novo neste mesmo link, sem mudar o resto do texto.</p>"
        if faltam else ""
    )

    # Numeração das fontes pela ordem da primeira citação.
    ordem = []
    for p in an["paragrafos"]:
        for f in p["fontes"]:
            if f["id"] not in ordem:
                ordem.append(f["id"])
    num = {fid: i + 1 for i, fid in enumerate(ordem)}

    def refs(fontes):
        ids = list(dict.fromkeys(f["id"] for f in fontes))
        return "".join(
            f'<a class="ref" href="#f{num[i]}" title="{escape(an["fontes"][i]["nome"])}">{num[i]}</a>'
            for i in ids
        )

    texto_html = f'<p class="titulo-nota">{negrito(an["titulo"])}</p>' + "".join(
        f'<p>{negrito(p["texto"])}{refs(p["fontes"])}</p>' for p in an["paragrafos"]
    )
    blocos_wa = [an["titulo"]] + [p["texto"] for p in an["paragrafos"]]
    if assinatura:
        texto_html += '<p class="assinatura">' + "<br>".join(
            escape(l) for l in assinatura.splitlines()
        ) + "</p>"
        blocos_wa.append(assinatura)
    texto_wa = "\n\n".join(blocos_wa)

    fontes_html = "".join(
        f'<li id="f{num[fid]}"><span class="fnum">{num[fid]}</span><span>'
        f'<a href="{escape(url_segura(an["fontes"][fid]["url"]))}" target="_blank" rel="noopener">'
        f'{escape(an["fontes"][fid]["nome"])}</a>'
        f' <span class="fdata">{date.fromisoformat(an["fontes"][fid]["data"]).strftime("%d/%m/%Y")}</span></span></li>'
        for fid in ordem
    )

    ipca = dados["indicador"] == "IPCA"
    tab = "7060" if ipca else "7062"
    prov = [
        ("Variação mensal", fmt(dados["variacao_mensal"]) + "%", f"IBGE SIDRA T{tab} V{'63' if ipca else '355'}"),
        ("Acumulado 12 meses", fmt(dados["acum_12m"]) + "%", f"IBGE SIDRA T{tab} V{'2265' if ipca else '1120'}"),
    ]
    if dados.get("nucleo_12m") is not None:
        prov.append(("Média dos núcleos 12m", fmt(dados["nucleo_12m"]) + "%", "BCB SGS 4466 · 11427 · 16122 · 27839 · 28750"))
    if dados.get("difusao") is not None:
        prov.append(("Difusão", fmt(dados["difusao"], 1) + "%", "BCB SGS 21379" if ipca else f"IBGE SIDRA T{tab} (calculada)"))
    prov_html = "".join(
        f"<tr><td>{c}</td><td class='num'>{v}</td><td class='fonte'>{f}</td></tr>" for c, v, f in prov
    )

    html = f"""<title>Nota de Inflação</title>
    <style>
    :root {{
      color-scheme: dark;
      --fundo: #0f172a;
      --superficie: #1e293b;
      --superficie-alta: #273449;
      --borda: #334155;
      --texto: #e2e8f0;
      --texto-suave: #94a3b8;
      --destaque: #2563eb;
      --destaque-hover: #1d4ed8;
      --destaque-claro: #60a5fa;
      --ok: #4ade80;
      --ia: #fbbf24;
      --ia-fundo: #3a2c0b;
      --raio: 10px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0 16px 64px;
      background: var(--fundo); color: var(--texto);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      font-size: 16px; line-height: 1.6;
    }}
    .pagina {{ max-width: 760px; margin: 0 auto; display: grid; gap: 20px; }}
    header {{ padding-block: 40px 0; }}
    .sobre {{ margin: 0; font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--texto-suave); }}
    h1 {{ margin: 4px 0 0; font-size: 1.9rem; font-weight: 650; letter-spacing: -.02em; text-wrap: balance; }}
    section {{ background: var(--superficie); border: 1px solid var(--borda); border-radius: var(--raio); padding: 24px; }}
    .sec-topo {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 16px; }}
    h2 {{ margin: 0; font-size: 1.15rem; font-weight: 650; }}
    .selo {{ font-size: .75rem; font-weight: 600; padding: 3px 10px; border-radius: 999px; color: var(--ia); background: var(--ia-fundo); white-space: nowrap; }}
    .texto {{ padding: 20px; background: var(--fundo); border: 1px solid var(--borda); border-radius: var(--raio); }}
    .texto p {{ margin: 0 0 14px; max-width: 68ch; }}
    .texto p:last-child {{ margin-bottom: 0; }}
    .carimbo {{ margin: 6px 0 0; font-size: .85rem; color: var(--texto-suave); font-variant-numeric: tabular-nums; }}
    .pendente {{ margin: 0; padding: 12px 16px; border-left: 3px solid var(--ia); background: var(--ia-fundo); border-radius: 0 var(--raio) var(--raio) 0; font-size: .92rem; }}
    .titulo-nota {{ font-size: 1.05rem; }}
    .texto .assinatura {{ margin-top: 20px; color: var(--texto-suave); font-size: .92rem; }}
    .aviso {{ margin: 14px 0 0; font-size: .85rem; color: var(--texto-suave); }}
    button {{
      font: inherit; font-size: .9rem; font-weight: 600; padding: 8px 16px; cursor: pointer;
      color: #fff; background: var(--destaque); border: 0; border-radius: var(--raio);
    }}
    button:hover {{ background: var(--destaque-hover); }}
    button:focus-visible, a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--destaque-claro); outline-offset: 2px; }}
    .botoes {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 16px; }}
    .ok {{ font-size: .85rem; color: var(--ok); }}
    a {{ color: var(--destaque-claro); }}
    a.ref {{
      display: inline-block; margin-left: 3px; min-width: 1.35em; padding: 0 4px; font-size: .7rem; font-weight: 600;
      line-height: 1.5; text-align: center; vertical-align: super; text-decoration: none;
      color: var(--destaque-claro); background: var(--superficie-alta); border-radius: 4px;
    }}
    h3 {{ margin: 24px 0 10px; font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .07em; color: var(--texto-suave); }}
    ol.fontes {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; font-size: .9rem; }}
    ol.fontes li {{ display: flex; gap: 10px; }}
    .fnum {{ flex: none; width: 1.6em; color: var(--texto-suave); font-variant-numeric: tabular-nums; }}
    .fdata {{ color: var(--texto-suave); font-variant-numeric: tabular-nums; }}
    ol.fontes a {{ overflow-wrap: anywhere; }}
    details {{ background: var(--superficie); border: 1px solid var(--borda); border-radius: var(--raio); padding: 16px 24px; }}
    summary {{ cursor: pointer; font-weight: 600; }}
    details p {{ font-size: .9rem; color: var(--texto-suave); }}
    .tabela {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
    th, td {{ text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--borda); vertical-align: top; }}
    th {{ font-weight: 600; color: var(--texto-suave); font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; }}
    td.num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
    td.fonte {{ color: var(--texto-suave); }}
    pre.nota {{
      margin: 12px 0 0; padding: 16px; background: var(--fundo); border: 1px solid var(--borda); border-radius: var(--raio);
      white-space: pre-wrap; word-wrap: break-word; font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
      font-variant-ligatures: none; font-size: .84rem; line-height: 1.5; max-height: 420px; overflow: auto;
    }}
    footer {{ font-size: .82rem; color: var(--texto-suave); }}
    footer p {{ margin: 0 0 6px; }}
    @media (max-width: 600px) {{ section, details {{ padding: 18px; }} .texto {{ padding: 16px; }} h1 {{ font-size: 1.6rem; }} }}
    </style>

    <div class="pagina">
    <header>
      <p class="sobre">{escape(dados['indicador'])} · divulgado em {d_div}</p>
      <h1>Inflação de {mes_nome} de {ano}</h1>
      <p class="carimbo">{carimbo}</p>
    </header>
    {aviso_pendente}

    <section aria-labelledby="t-nota">
      <div class="sec-topo">
        <h2 id="t-nota">Nota para WhatsApp</h2>
        <span class="selo">Dados oficiais + explicações por IA</span>
      </div>
      <div class="texto" id="texto">{texto_html}</div>
      <div class="botoes">
        <button type="button" id="copiar">Copiar nota</button>
        <span class="ok" id="ok" hidden>Copiada</span>
      </div>
      <pre class="nota" id="texto-wa" hidden>{escape(texto_wa)}</pre>
      <p class="aviso">Os números vêm do IBGE e do BCB, ou do trecho da fonte citada, e foram conferidos por script. As explicações foram redigidas por IA: revise antes de circular.</p>

      <h3>Fontes das explicações</h3>
      <ol class="fontes">{fontes_html}</ol>
    </section>

    <details>
      <summary>Base de dados usada na redação</summary>
      <p>Números obrigatórios e sua origem. Abaixo, a nota determinística do projeto, que serviu de insumo e não é publicada.</p>
      <div class="tabela"><table>
        <tr><th>Campo</th><th>Valor</th><th>Série</th></tr>
        {prov_html}
      </table></div>
      <pre class="nota">{escape(nota)}</pre>
    </details>

    <footer>
      <p>Redigido por IA (Claude) com base apenas no que estava publicado até {d_div}, dia da divulgação.</p>
    </footer>
    </div>

    <script>
    // Sem acesso à área de transferência, mostra e seleciona o texto para Ctrl+C.
    document.getElementById("copiar").addEventListener("click", () => {{
      const el = document.getElementById("texto-wa"), ok = document.getElementById("ok");
      const mostrar = (msg) => {{ ok.textContent = msg; ok.hidden = false; setTimeout(() => (ok.hidden = true), 3000); }};
      let p;
      try {{ p = navigator.clipboard.writeText(el.textContent); }} catch (e) {{ p = Promise.reject(e); }}
      p.then(() => mostrar("Copiada"), () => {{
        el.hidden = false;
        const sel = window.getSelection(), r = document.createRange();
        r.selectNodeContents(el); sel.removeAllRanges(); sel.addRange(r);
        mostrar("Texto selecionado: copie com Ctrl+C");
      }});
    }});
    </script>
    """
    return html


def main(indicador: str, mes_ref: str) -> None:
    from analise.coletar import pasta_do_caso

    from analise.versoes import versao_atual

    pasta = pasta_do_caso(indicador, mes_ref)
    html = montar(
        json.loads((pasta / "dados.json").read_text(encoding="utf-8")),
        (pasta / "nota.txt").read_text(encoding="utf-8"),
        json.loads((pasta / "analise.json").read_text(encoding="utf-8")),
        ler_assinatura(),
        versao=versao_atual(pasta),
    )
    (pasta / "pagina.html").write_text(html, encoding="utf-8", newline="\n")
    print(pasta / "pagina.html")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
