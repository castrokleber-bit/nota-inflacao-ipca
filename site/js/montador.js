/* Montador da nota de inflação — determinístico, sem IA.
 * Par de nucleo/montador.py.
 *
 * Cada bloco* devolve string. comporNota() monta o texto completo.
 * Nenhum token do texto é gerado por IA; cada campo rastreia a um valor
 * devolvido pela API (ResultadoInflacao).
 */
import { fmt, preencher } from "./numeros.js";
import {
  gruposRelevantes,
  gruposQueda,
  topSubitem,
  topSubitemQueda,
} from "./impacto.js";

// ---------------------------------------------------------------------------
// Configuração de montagem (parametrizável; não hard-coded no texto)
// ---------------------------------------------------------------------------

export const CONFIG_PADRAO = {
  top_n_grupos: 3,
  threshold_grupos: 0.05, // p.p. mínimo para citar um grupo (alta)
  top_n_queda: 1,
  threshold_queda: 0.05, // p.p. mínimo para citar deflação
  emoji_titulo: "\u{1f6a8}", // 🚨
  emoji_resultado: "\u{1f6a9}", // 🚩
  emoji_explicacao: "\u{1f534}", // 🔴
  emoji_acumulado: "\u{1f4c8}", // 📈
  emoji_nucleo: "\u{1f4c9}", // 📉
  emoji_difusao: "\u{1f4ca}", // 📊
  emoji_queda: "\u{1f7e2}", // 🟢 — usado nos parágrafos de deflação
};

// ---------------------------------------------------------------------------
// Tabelas e auxiliares de formatação
// ---------------------------------------------------------------------------

const MESES_ACENTUADOS = {
  "01": "janeiro", "02": "fevereiro", "03": "março", "04": "abril",
  "05": "maio", "06": "junho", "07": "julho", "08": "agosto",
  "09": "setembro", "10": "outubro", "11": "novembro", "12": "dezembro",
};

// Exceções à regra de terminação de artigoDe, pela primeira palavra inteira
// (sem acento). Comparação exata: o antigo teste por prefixo fazia "maca"
// capturar "macarrão" e publicava "da macarrão".
const ARTIGO_EXCECOES = new Map([
  // femininos que não terminam em -a/-ção/-são/-dade/-gem
  ["alface", "f"], ["ave", "f"], ["carne", "f"], ["couve", "f"], ["creche", "f"],
  ["gripe", "f"], ["higiene", "f"], ["internet", "f"], ["lingerie", "f"],
  ["maionese", "f"], ["manicure", "f"], ["mao", "f"], ["tv", "f"],
  // masculinos terminados em -a
  ["cha", "m"], ["cinema", "m"], ["dentista", "m"], ["fisioterapeuta", "m"],
  ["fuba", "m"], ["sutia", "m"],
  // singulares terminados em -s (não são plural)
  ["gas", "m"], ["lapis", "m"], ["onibus", "m"], ["tenis", "m"],
]);

/** '202604' -> 'abril' */
function mes(mesRef) {
  return MESES_ACENTUADOS[mesRef.slice(4, 6)];
}

function ano(mesRef) {
  return mesRef.slice(0, 4);
}

/** '1.Alimentação e bebidas' -> 'Alimentação e bebidas' */
function stripNome(nome) {
  if (nome && /[0-9]/.test(nome[0])) {
    // split(".", 1) do Python é maxsplit, não limite de resultados como no JS.
    const i = nome.indexOf(".");
    if (i !== -1) return nome.slice(i + 1).trim();
  }
  return nome;
}

/**
 * Heurística de gênero/número para 'da(s)' / 'do(s)' antes do nome do item.
 * O núcleo semântico do nome (que define gênero/número) é a primeira palavra,
 * não a última — ex.: "alimentação no domicílio" (fem.) ou "tubérculos,
 * raízes e legumes" (masc. plural).
 */
function artigoDe(nome) {
  // \p{Mn} = marcas combinantes; equivale ao filtro de category(c) != "Mn".
  const nlAscii = nome.toLowerCase().normalize("NFD").replace(/\p{Mn}/gu, "");
  const primeira = nlAscii.trim().split(/[ ,(]/)[0];
  if (ARTIGO_EXCECOES.has(primeira)) {
    return ARTIGO_EXCECOES.get(primeira) === "f" ? "da" : "do";
  }
  const plural = primeira.endsWith("s") && primeira.length > 2;
  const singular = plural ? primeira.slice(0, -1) : primeira;
  const feminino = ARTIGO_EXCECOES.has(singular)
    ? ARTIGO_EXCECOES.get(singular) === "f"
    : ["a", "cao", "sao", "dade", "gem"].some((s) => singular.endsWith(s));
  if (feminino) return plural ? "das" : "da";
  return plural ? "dos" : "do";
}

function direcao(v, alta = "alta", queda = "queda") {
  return v >= 0 ? alta : queda;
}

/**
 * O número como é exibido, em unidades da última casa: 4,39 -> 439.
 * Toda comparação que vira texto usa isto, e não o float cru — senão
 * 4,391 contra 4,389 publica "4,39%, acima dos 4,39%".
 */
function unidades(v, decimais = 2) {
  return parseInt(fmt(v, decimais).replace(",", ""), 10);
}

/**
 * 'alta de 0,67%' / 'queda de 0,32%' / 'estabilidade (0,00%)'.
 * A palavra já diz o sentido, então o número sai sem sinal: nada de
 * "queda de -0,32%".
 */
function movimento(v, alta = "alta", queda = "queda") {
  if (unidades(v) === 0) return "estabilidade (0,00%)";
  return `${direcao(v, alta, queda)} de ${fmt(Math.abs(v))}%`;
}

/** 'acima' / 'abaixo' / 'igual', comparando os números como são exibidos. */
function comparacao(atual, anterior, decimais = 2) {
  const a = unidades(atual, decimais);
  const b = unidades(anterior, decimais);
  if (a === b) return "igual";
  return a > b ? "acima" : "abaixo";
}

function emLinhaOuRelativo(v, ref, tol = 0.05) {
  const dif = unidades(v) - unidades(ref);
  if (Math.abs(dif) <= unidades(tol)) return "em linha com";
  return dif > 0 ? "acima de" : "abaixo de";
}

/** '0,29 ponto percentual (p.p.)' — para o primeiro grupo. */
function ppLongo(v) {
  const txt = fmt(v);
  if (Math.abs(v) > 1) return `${txt} pontos percentuais (p.p.)`;
  return `${txt} ponto percentual (p.p.)`;
}

/** '0,16 p.p.' — versão curta para grupos subsequentes. */
function pp(v) {
  return `${fmt(v)} p.p.`;
}

// ---------------------------------------------------------------------------
// Variação de frases por trimestre — evita repetição entre divulgações
//
// Regra de indexação: idxVar(mesRef) → 0=Q1, 1=Q2, 2=Q3, 3=Q4.
// Índice 1 (Q2: abr-jun) = frases originais, preservando os golden files
// de IPCA abr/2026 e IPCA-15 mai/2026 sem alteração.
// ---------------------------------------------------------------------------

function idxVar(mesRef) {
  return Math.floor((parseInt(mesRef.slice(4, 6), 10) - 1) / 3) % 4;
}

// Variante cujas frases de queda não pressupõem um parágrafo de alta antes
// ("Entre os subgrupos, a queda..."): usada quando nenhum grupo subiu.
const IDX_NEUTRO = 2;

// Abertura do parágrafo de alta (grupos de inflação — 1º grupo)
const ABR_ALTA = [
  "O desempenho do {ind} em {mes} foi marcado pela *{dir} do grupo {nome}*",
  "O resultado de {mes} *reflete a {dir} do grupo {nome}*",
  "Em {mes}, destaca-se a *{dir} do grupo {nome}*",
  "*A {dir} do grupo {nome}* foi o principal fator do {ind} de {mes}",
];

// Conector para o 2º grupo (singular)
const CON_SG = [
  "Na sequência, merece atenção o grupo",
  "Em seguida, destaca-se o grupo",
  "Também se destaca o grupo",
  "Outro destaque é o grupo",
];

// Conector para 2º e 3º grupos (plural)
const CON_PL = [
  "Na sequência, merecem atenção os grupos",
  "Em seguida, destacam-se os grupos",
  "Também se destacam os grupos",
  "Outros destaques incluem os grupos",
];

// Parágrafo do subgrupo de maior impacto positivo (nivel 2)
const SUBGRUPO_ALTA = [
  "No nível de subgrupos, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",
  "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), subgrupo de maior impacto no índice do mês.",
  "Entre os subgrupos, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto do período.",
  "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o subgrupo de maior impacto no mês.",
];

// Parágrafo do subgrupo de maior deflação (nivel 2)
const SUBGRUPO_QUEDA = [
  "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária entre os subgrupos.",
  "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), subgrupo de maior deflação no índice do mês.",
  "Entre os subgrupos, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção sobre o índice.",
  "Como principal fator desinflacionário entre os subgrupos, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice.",
];

// Parágrafo do item de maior impacto positivo (nivel 3)
const ITEM_ALTA = [
  "No nível de itens, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",
  "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), item de maior impacto no índice do mês.",
  "Entre os itens, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto do período.",
  "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o item de maior impacto no mês.",
];

// Parágrafo do item de maior deflação (nivel 3)
const ITEM_QUEDA = [
  "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária entre os itens.",
  "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), item de maior deflação no índice do mês.",
  "Entre os itens, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção sobre o índice.",
  "Como principal fator desinflacionário entre os itens, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice.",
];

// Parágrafo do subitem de maior impacto positivo (nivel 4)
const SUB_ALTA = [
  "No nível de subitens, o maior destaque é a {dir} {art} *{nome}* ({var}% e impacto de {imp}).",
  "Também merece destaque a {dir} {art} *{nome}* ({var}% e impacto de {imp}), subitem de maior impacto individual no índice do mês.",
  "Entre os subitens, a {dir} {art} *{nome}* ({var}% e impacto de {imp}) registra o maior impacto individual do período.",
  "A {dir} {art} *{nome}* ({var}% e impacto de {imp}) se destaca como o subitem de maior impacto individual no mês.",
];

// Abertura do parágrafo de queda — 1 grupo
const ABR_QUEDA_1 = [
  "Na direção oposta, o grupo *{nome}* recuou",
  "Em sentido contrário, destaca-se a queda do grupo *{nome}*",
  "Como fator de contenção, o grupo *{nome}* registrou deflação",
  "Atuando como contraponto, o grupo *{nome}* pressionou o índice para baixo",
];

// Parágrafo de queda — 2 grupos (texto completo, inclui os números)
const ABR_QUEDA_2 = [
  "Na direção oposta, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) pressionaram o índice para baixo.",
  "Em sentido contrário, destacam-se as quedas dos grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}), que contribuíram para reduzir o índice do mês.",
  "Como fatores de contenção, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) exerceram pressão deflacionária sobre o índice.",
  "Em contraponto, os grupos *{n1}* (variação de {v1}% e impacto de {i1}) e *{n2}* (variação de {v2}% e impacto de {i2}) contribuíram para reduzir o índice do mês.",
];

// Parágrafo do subitem de maior deflação
const SUB_QUEDA = [
  "Na direção oposta, a queda {art} *{nome}* ({var}% e impacto de {imp}) representa a maior pressão deflacionária individual do período.",
  "Em sentido contrário, destaca-se a queda {art} *{nome}* ({var}% e impacto de {imp}), subitem de maior deflação individual no índice do mês.",
  "Entre os subitens, a queda {art} *{nome}* ({var}% e impacto de {imp}) exerceu a maior contenção individual sobre o índice.",
  "Como principal fator desinflacionário individual, a queda {art} *{nome}* ({var}% e impacto de {imp}) atuou sobre o índice do mês.",
];

// ---------------------------------------------------------------------------
// Blocos individuais
// ---------------------------------------------------------------------------

export function blocoTitulo(r, cfg) {
  const m = mes(r.mes_ref).toUpperCase();
  return `${cfg.emoji_titulo} *${r.indicador} ${m}/${ano(r.mes_ref)}*`;
}

/** '202605' -> '202505' */
function mesmoMesAnoAnterior(mesRef) {
  return `${parseInt(mesRef.slice(0, 4), 10) - 1}${mesRef.slice(4)}`;
}

export function blocoResultado(r, cfg) {
  const mesAnoAnt = mesmoMesAnoAnterior(r.mes_ref);

  // Comparação com mês anterior
  const compAnterior =
    `após ${movimento(r.variacao_mensal_anterior, "avanço", "recuo")} ` +
    `em ${mes(r.mes_ant)}`;

  // Comparação com mesmo mês do ano anterior (quando disponível)
  let comparacoes;
  if (r.variacao_mesmo_mes_ano_anterior !== null) {
    const compAnoAnt =
      `e ${movimento(r.variacao_mesmo_mes_ano_anterior)} ` +
      `em ${mes(mesAnoAnt)} de ${ano(mesAnoAnt)}`;
    comparacoes = `${compAnterior} ${compAnoAnt}.`;
  } else {
    comparacoes = `${compAnterior}.`;
  }

  let texto =
    `${cfg.emoji_resultado} O ${r.indicador} registrou ` +
    `*${movimento(r.variacao_mensal)}* ` +
    `em ${mes(r.mes_ref)} de ${ano(r.mes_ref)}, ` +
    `${comparacoes}`;

  if (r.projecao_focus !== null) {
    const relFoc = emLinhaOuRelativo(r.variacao_mensal, r.projecao_focus);
    texto +=
      ` O resultado ficou ${relFoc} a projeção da Pesquisa Focus ` +
      `do Banco Central (${fmt(r.projecao_focus)}%).`;
  }

  return texto;
}

/**
 * Parágrafos dos grupos + subitens de destaque; pode conter \n\n interno.
 * Ordem: inflação (grupos → subitem) → deflação (grupos → subitem).
 * Frases variam por trimestre para evitar repetição entre divulgações.
 *
 * Sem grupo em alta relevante (mês de deflação), a queda abre a explicação
 * com as frases de destaque principal, e os parágrafos de queda seguintes
 * perdem o conector de contraste ("Em sentido contrário"), que não teria a
 * que se opor.
 */
export function blocoExplicacao(r, cfg) {
  const idx = idxVar(r.mes_ref);
  const grupos = gruposRelevantes(
    r.grupos,
    cfg.top_n_grupos,
    cfg.threshold_grupos,
  );
  const gqs = gruposQueda(r.grupos, cfg.top_n_queda, cfg.threshold_queda);
  const partes = [];
  let idxQueda;

  if (grupos.length > 0) {
    partes.push(paragrafoGrupos(r, grupos, cfg.emoji_explicacao, idx));
    partes.push(...paragrafosAlta(r, cfg, idx));
    if (gqs.length > 0) partes.push(paragrafoQuedaContraste(gqs, cfg, idx));
    idxQueda = idx;
  } else {
    if (gqs.length > 0) {
      partes.push(paragrafoGrupos(r, gqs, cfg.emoji_queda, idx));
    }
    idxQueda = IDX_NEUTRO;
  }

  partes.push(...paragrafosQueda(r, cfg, idxQueda));
  return partes.join("\n\n");
}

/** Abertura da explicação: o grupo principal e até dois seguintes. */
function paragrafoGrupos(r, grupos, emoji, idx) {
  const g1 = grupos[0];
  const g1n = stripNome(g1.nome);
  const dirG1 = direcao(g1.variacao);

  const abertura = preencher(ABR_ALTA[idx], {
    ind: r.indicador,
    mes: mes(r.mes_ref),
    dir: dirG1,
    nome: g1n,
  });
  let texto =
    `${emoji} ${abertura}, ` +
    `com variação de ${fmt(g1.variacao)}% e impacto de ` +
    `${ppLongo(g1.impacto)} no índice do mês.`;

  if (grupos.length === 2) {
    const g2 = grupos[1];
    const g2n = stripNome(g2.nome);
    texto +=
      ` ${CON_SG[idx]} ${g2n}, ` +
      `com variação de ${fmt(g2.variacao)}% ` +
      `e impacto de ${pp(g2.impacto)}`;
  } else if (grupos.length >= 3) {
    const g2 = grupos[1];
    const g3 = grupos[2];
    const g2n = stripNome(g2.nome);
    const g3n = stripNome(g3.nome);
    texto +=
      ` ${CON_PL[idx]} ${g2n}, ` +
      `com variação de ${fmt(g2.variacao)}% ` +
      `e impacto de ${pp(g2.impacto)}, ` +
      `e ${g3n}, ` +
      `com variação de ${fmt(g3.variacao)}% ` +
      `e impacto de ${pp(g3.impacto)}`;
  }
  return texto;
}

/** Subgrupo, item e subitem de maior impacto positivo. */
function paragrafosAlta(r, cfg, idx) {
  const partes = [];

  // --- INFLAÇÃO: subgrupo de maior impacto (nivel 2) ---
  const subgrupo = topSubitem(r.subitens, 2);
  if (subgrupo !== null) {
    const sgn = stripNome(subgrupo.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_explicacao} ` +
        preencher(SUBGRUPO_ALTA[idx], {
          dir: direcao(subgrupo.variacao),
          art: artigoDe(sgn),
          nome: sgn,
          var: fmt(subgrupo.variacao),
          imp: pp(subgrupo.impacto),
        }),
    );
  }

  // --- INFLAÇÃO: item de maior impacto (nivel 3) ---
  const item = topSubitem(r.subitens, 3);
  if (item !== null) {
    const itn = stripNome(item.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_explicacao} ` +
        preencher(ITEM_ALTA[idx], {
          dir: direcao(item.variacao),
          art: artigoDe(itn),
          nome: itn,
          var: fmt(item.variacao),
          imp: pp(item.impacto),
        }),
    );
  }

  // --- INFLAÇÃO: subitem de maior impacto positivo (nivel 4) ---
  const subitem = topSubitem(r.subitens, 4);
  if (subitem !== null) {
    const sn = stripNome(subitem.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_explicacao} ` +
        preencher(SUB_ALTA[idx], {
          dir: direcao(subitem.variacao),
          art: artigoDe(sn),
          nome: sn,
          var: fmt(subitem.variacao),
          imp: pp(subitem.impacto),
        }),
    );
  }

  return partes;
}

/** Grupos em queda, em contraste com o parágrafo de alta que os precede. */
function paragrafoQuedaContraste(gqs, cfg, idx) {
  if (gqs.length === 1) {
    const gq = gqs[0];
    const aberturaQ = preencher(ABR_QUEDA_1[idx], {
      nome: stripNome(gq.nome),
    });
    return (
      `${cfg.emoji_queda} ${aberturaQ}, ` +
      `com variação de ${fmt(gq.variacao)}% e impacto de ` +
      `${pp(gq.impacto)} no índice do mês.`
    );
  }
  const [gq1, gq2] = gqs;
  return (
    `${cfg.emoji_queda} ` +
    preencher(ABR_QUEDA_2[idx], {
      n1: stripNome(gq1.nome),
      v1: fmt(gq1.variacao),
      i1: pp(gq1.impacto),
      n2: stripNome(gq2.nome),
      v2: fmt(gq2.variacao),
      i2: pp(gq2.impacto),
    })
  );
}

/** Subgrupo, item e subitem de maior deflação. */
function paragrafosQueda(r, cfg, idx) {
  const partes = [];

  // --- DEFLAÇÃO: subgrupo de maior queda (nivel 2) ---
  const subgrupoQ = topSubitemQueda(r.subitens, 2, cfg.threshold_queda);
  if (subgrupoQ !== null) {
    const sqgn = stripNome(subgrupoQ.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_queda} ` +
        preencher(SUBGRUPO_QUEDA[idx], {
          art: artigoDe(sqgn),
          nome: sqgn,
          var: fmt(subgrupoQ.variacao),
          imp: pp(subgrupoQ.impacto),
        }),
    );
  }

  // --- DEFLAÇÃO: item de maior queda (nivel 3) ---
  const itemQ = topSubitemQueda(r.subitens, 3, cfg.threshold_queda);
  if (itemQ !== null) {
    const iqn = stripNome(itemQ.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_queda} ` +
        preencher(ITEM_QUEDA[idx], {
          art: artigoDe(iqn),
          nome: iqn,
          var: fmt(itemQ.variacao),
          imp: pp(itemQ.impacto),
        }),
    );
  }

  // --- DEFLAÇÃO: subitem de maior queda (nivel 4) ---
  const subitemQ = topSubitemQueda(r.subitens, 4, cfg.threshold_queda);
  if (subitemQ !== null) {
    const sqn = stripNome(subitemQ.nome).toLowerCase();
    partes.push(
      `${cfg.emoji_queda} ` +
        preencher(SUB_QUEDA[idx], {
          art: artigoDe(sqn),
          nome: sqn,
          var: fmt(subitemQ.variacao),
          imp: pp(subitemQ.impacto),
        }),
    );
  }

  return partes;
}

export function blocoAcumulado(r, cfg) {
  const rel = { acima: "acima dos", abaixo: "abaixo dos", igual: "igual aos" }[
    comparacao(r.acum_12m, r.acum_12m_anterior)
  ];
  return (
    `${cfg.emoji_acumulado} O *${r.indicador} acumulado em 12 meses* ` +
    `até ${mes(r.mes_ref)} ficou em *${fmt(r.acum_12m)}%*, ` +
    `${rel} ${fmt(r.acum_12m_anterior)}% ` +
    `registrados nos 12 meses encerrados em ${mes(r.mes_ant)}.`
  );
}

/** Apenas para IPCA e quando nucleo_12m não é null. */
export function blocoNucleo(r, cfg) {
  if (r.indicador !== "IPCA" || r.nucleo_12m === null) return null;

  const base =
    `${cfg.emoji_nucleo} *A média dos núcleos de inflação*, ` +
    `que suavizam os efeitos de itens mais voláteis, ` +
    `ficou em *${fmt(r.nucleo_12m)}%* no acumulado em 12 meses ` +
    `até ${mes(r.mes_ref)}`;

  // Sem o mês anterior não há comparação a fazer. O fallback antigo usava o
  // próprio nucleo_12m no lugar do ausente, o que publicava a frase
  // "ficou em X%, ligeiramente abaixo dos X%" — um número inventado para o
  // mês anterior, afirmado como fato. Mesma política do bloco de difusão:
  // havendo só um dado, informa-se só ele.
  if (r.nucleo_12m_anterior === null) return `${base}.`;

  const rel = {
    acima: "ligeiramente acima dos",
    abaixo: "ligeiramente abaixo dos",
    igual: "igual aos",
  }[comparacao(r.nucleo_12m, r.nucleo_12m_anterior)];
  return (
    `${base}, ${rel} ` +
    `${fmt(r.nucleo_12m_anterior)}% no acumulado até ${mes(r.mes_ant)}.`
  );
}

export function blocoDifusao(r, cfg) {
  if (r.difusao === null) return null;
  const dif = fmt(r.difusao, 1);
  if (r.difusao_anterior !== null) {
    const rel = { acima: "acima do", abaixo: "abaixo do", igual: "igual ao" }[
      comparacao(r.difusao, r.difusao_anterior, 1)
    ];
    const ant = fmt(r.difusao_anterior, 1);
    return (
      `${cfg.emoji_difusao} O *índice de difusão*, que mede a disseminação ` +
      `das altas de preços entre os itens que compõem o ${r.indicador}, ` +
      `ficou em *${dif}%*, ${rel} registrado em ` +
      `${mes(r.mes_ant)} (${ant}%).`
    );
  }
  return (
    `${cfg.emoji_difusao} O *índice de difusão*, que mede a disseminação ` +
    `das altas de preços entre os itens que compõem o ${r.indicador}, ` +
    `ficou em *${dif}%*.`
  );
}

export function blocoLink(r) {
  if (!r.url_ibge) return null;
  return `Notícia: ${r.url_ibge}`;
}

// ---------------------------------------------------------------------------
// Composição final
// ---------------------------------------------------------------------------

/**
 * Monta o texto completo da nota de WhatsApp.
 * Determinístico: nenhum token gerado por IA.
 */
export function comporNota(r, cfg = null) {
  const c = cfg === null ? CONFIG_PADRAO : { ...CONFIG_PADRAO, ...cfg };

  const blocos = [
    blocoTitulo(r, c),
    blocoResultado(r, c),
    blocoExplicacao(r, c),
    blocoAcumulado(r, c),
    blocoNucleo(r, c),
    blocoDifusao(r, c),
    blocoLink(r),
  ];

  return blocos.filter((b) => b).join("\n\n");
}
