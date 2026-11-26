"""
Comparação de ciclos: os indicadores de vários lotes lado a lado, a curva
de mortalidade de cada um e as falhas que se repetem de lote para lote
(tiradas da nota técnica).
"""

import io
from collections import Counter

import altair as alt
import pandas as pd
import streamlit as st

import estilo as ui
import perfis
from estilo import P, num
from database import conectar, ler_df
from calculos import resumo_ciclo
from nota_tecnica import analisar_ciclo

# (chave, rótulo, casas decimais, melhor: "maior" | "menor" | None, económico?)
INDICADORES = [
    ("dias", "Duração (dias)", 0, None, False),
    ("alojadas", "Aves alojadas", 0, None, False),
    ("peso_pinto_g", "Peso do pinto (g)", 1, "maior", False),
    ("mort_1sem", "Mortalidade na 1.ª semana (%)", 2, "menor", False),
    ("mortalidade_pct", "Mortalidade total (%)", 2, "menor", False),
    ("viabilidade_pct", "Viabilidade (%)", 2, "maior", False),
    ("peso_actual_g", "Peso médio final (g)", 0, "maior", False),
    ("gmd", "Ganho médio diário (g/dia)", 1, "maior", False),
    ("racao_ave", "Ração por ave alojada (kg)", 2, None, False),
    ("ica", "Conversão alimentar", 2, "menor", False),
    ("iep", "Índice de Eficiência Produtiva", 0, "maior", False),
    ("aves_vendidas", "Aves vendidas", 0, None, False),
    ("kg_vendidos", "Kg vendidos", 1, None, False),
    ("custo_total", "Custos totais (MZN)", 2, None, True),
    ("custo_por_ave", "Custo por ave (MZN)", 2, "menor", True),
    ("custo_por_kg", "Custo por kg de peso vivo (MZN)", 2, "menor", True),
    ("receita", "Receita (MZN)", 2, "maior", True),
    ("margem_liquida", "Margem líquida (MZN)", 2, "maior", True),
    ("margem_liquida_pct", "Margem líquida (% da receita)", 1, "maior", True),
    ("roi_pct", "Retorno sobre o investimento (%)", 1, "maior", True),
    ("n_falhas", "Falhas na nota técnica", 0, "menor", False),
]

# Indicadores em que zero quer dizer "sem dados" e não "resultado bom"
ZERO_E_FALTA = {"peso_pinto_g", "peso_actual_g", "gmd", "ica", "iep", "custo_por_ave",
                "custo_por_kg", "racao_ave"}


def _todos_ciclos():
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, codigo, data_inicio, estado, linhagem, n_aves_alojadas "
                    "FROM ciclos ORDER BY data_inicio DESC, id DESC")
        return [dict(r) for r in cur.fetchall()]


@st.cache_data(ttl=120, show_spinner=False)
def _linha_ciclo(cid: int) -> dict:
    r = resumo_ciclo(cid)
    nota = analisar_ciclo(cid)
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (cid,))
        alojadas = cur.fetchone()["n_aves_alojadas"] or 0
        cur.execute("""SELECT COALESCE(SUM(mortalidade), 0) AS m, MAX(dia_ciclo) AS d
                       FROM registo_diario WHERE ciclo_id = %s AND dia_ciclo <= 7""", (cid,))
        m1 = cur.fetchone()["m"]
        cur.execute("SELECT MAX(dia_ciclo) AS d FROM registo_diario WHERE ciclo_id = %s", (cid,))
        dias = cur.fetchone()["d"] or r.get("dia_ciclo") or 0
    linha = {k: r.get(k) for k, *_ in INDICADORES if k in r}
    linha.update({
        "dias": dias,
        "alojadas": alojadas,
        "mort_1sem": round(m1 / alojadas * 100, 2) if alojadas else None,
        "racao_ave": round(r["consumo_racao_kg"] / alojadas, 2) if alojadas else None,
        "n_falhas": len(nota["falhas"]),
        "_areas": sorted({f["area"] for f in nota["falhas"]}),
    })
    # Sem vendas ou sem custos lançados, as margens não dizem nada (dariam 100% de lucro)
    if not r.get("receita") or not r.get("custo_total"):
        for k in ("margem_liquida", "margem_liquida_pct", "roi_pct"):
            linha[k] = None
    if not r.get("custo_total"):
        linha["custo_total"] = None
    return linha


@st.cache_data(ttl=120, show_spinner=False)
def _curvas_mortalidade(ids: tuple, nomes: tuple) -> pd.DataFrame:
    with conectar() as conn:
        df = ler_df("""
            SELECT r.ciclo_id, r.dia_ciclo, r.mortalidade, c.n_aves_alojadas
            FROM registo_diario r JOIN ciclos c ON c.id = r.ciclo_id
            WHERE r.ciclo_id = ANY(%s) ORDER BY r.ciclo_id, r.dia_ciclo
        """, conn, params=(list(ids),))
    if df.empty:
        return df
    df["mortalidade"] = pd.to_numeric(df["mortalidade"], errors="coerce").fillna(0)
    df["acum"] = df.groupby("ciclo_id")["mortalidade"].cumsum()
    df["Mortalidade acumulada (%)"] = df["acum"] / df["n_aves_alojadas"] * 100
    df["Ciclo"] = df["ciclo_id"].map(dict(zip(ids, nomes)))
    df = df.rename(columns={"dia_ciclo": "Dia"})
    return df[["Ciclo", "Dia", "Mortalidade acumulada (%)"]]


def _fmt(v, casas):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return num(v, casas)


def pagina_comparar():
    ui.cabecalho("Comparar ciclos",
                 "Os indicadores de vários lotes lado a lado, para ver o que melhorou, o que piorou "
                 "e que falhas se repetem.", "Análise")
    ciclos = _todos_ciclos()
    if len(ciclos) < 2:
        ui.vazio("São precisos pelo menos dois ciclos para comparar. Crie ou importe mais ciclos.")
        return

    rotulo = {c["id"]: f"{c['codigo']} · {ui.data_curta(c['data_inicio'])}" for c in ciclos}
    padrao = [c["id"] for c in ciclos[:6]]
    escolhidos = st.multiselect(
        "Ciclos a comparar", options=[c["id"] for c in ciclos], default=padrao,
        format_func=lambda i: rotulo[i], key="cmp_ciclos",
        help="Escolha de 2 a 8 ciclos. Por omissão aparecem os 6 mais recentes.")
    if len(escolhidos) < 2:
        st.info("Escolha pelo menos dois ciclos.")
        return
    if len(escolhidos) > 8:
        st.warning("Para a tabela ficar legível, só os primeiros 8 ciclos escolhidos são comparados.")
        escolhidos = escolhidos[:8]

    # do mais antigo para o mais recente, para se ler a evolução da esquerda para a direita
    ordem = {c["id"]: n for n, c in enumerate(reversed(ciclos))}
    escolhidos = sorted(escolhidos, key=lambda i: ordem[i])
    nomes = [rotulo[i].split(" · ")[0] for i in escolhidos]

    with st.spinner("A calcular os indicadores dos ciclos..."):
        linhas = {i: _linha_ciclo(i) for i in escolhidos}

    economia = perfis.ve_economia()
    inds = [x for x in INDICADORES if economia or not x[4]]

    # ---------- tabela lado a lado ----------
    ui.secao("Indicadores lado a lado", "a verde, o melhor valor de cada linha")
    tabela, melhor = [], []
    for chave, nome, casas, direccao, _ in inds:
        valores = [linhas[i].get(chave) for i in escolhidos]
        validos = [v for v in valores if v is not None and not (chave in ZERO_E_FALTA and v == 0)]
        alvo = None
        if direccao and len(validos) >= 2 and len(set(validos)) > 1:
            alvo = max(validos) if direccao == "maior" else min(validos)
        linha_fmt = {"Indicador": nome}
        for nm, v in zip(nomes, valores):
            falta = v is None or (chave in ZERO_E_FALTA and v == 0)
            linha_fmt[nm] = "–" if falta else _fmt(v, casas)
        tabela.append(linha_fmt)
        melhor.append([(v == alvo and alvo is not None) for v in valores])
    df = pd.DataFrame(tabela)

    def _pintar(_):
        estilos = pd.DataFrame("", index=df.index, columns=df.columns)
        for r_, flags in enumerate(melhor):
            for nm, f in zip(nomes, flags):
                if f:
                    estilos.loc[r_, nm] = (f"background-color: {P['g100']}; color: {P['g800']}; "
                                           "font-weight: 700")
        return estilos

    st.dataframe(df.style.apply(_pintar, axis=None), hide_index=True, width="stretch",
                 height=min(38 * (len(df) + 1) + 4, 820))
    st.caption("“–” quer dizer que o ciclo não tem dados para esse indicador (por exemplo, sem "
               "pesagens não há peso médio nem conversão alimentar).")

    # ---------- gráfico de um indicador ----------
    ui.secao("Um indicador em gráfico")
    opcoes = {nome: (chave, casas) for chave, nome, casas, _d, _e in inds
              if chave not in ("alojadas",)}
    escolha = st.selectbox("Indicador", list(opcoes.keys()),
                           index=list(opcoes.keys()).index("Mortalidade total (%)"), key="cmp_ind")
    chave, casas = opcoes[escolha]
    dados = pd.DataFrame({"Ciclo": nomes,
                          "Valor": [linhas[i].get(chave) for i in escolhidos]}).dropna()
    if chave in ZERO_E_FALTA:
        dados = dados[dados["Valor"] != 0]
    if dados.empty:
        ui.vazio("Nenhum dos ciclos escolhidos tem dados para este indicador.")
    else:
        barras = alt.Chart(dados).mark_bar(color=P["g700"], cornerRadiusTopLeft=4,
                                           cornerRadiusTopRight=4).encode(
            x=alt.X("Ciclo:N", sort=nomes, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Valor:Q", title=escolha),
            tooltip=["Ciclo", alt.Tooltip("Valor:Q", format=f",.{casas}f", title=escolha)],
        )
        rotulos = barras.mark_text(dy=-8, color=P["tinta"], fontSize=12).encode(
            text=alt.Text("Valor:Q", format=f",.{casas}f"))
        st.altair_chart(ui.tema_grafico((barras + rotulos).properties(height=300)),
                        use_container_width=True)

    # ---------- curva de mortalidade ----------
    ui.secao("Mortalidade acumulada ao longo do ciclo", "% das aves alojadas")
    curvas = _curvas_mortalidade(tuple(escolhidos), tuple(nomes))
    if curvas.empty:
        ui.vazio("Os ciclos escolhidos não têm registos diários.")
    else:
        linha_g = alt.Chart(curvas).mark_line(strokeWidth=2.5).encode(
            x=alt.X("Dia:Q", title="Dia do ciclo"),
            y=alt.Y("Mortalidade acumulada (%):Q"),
            color=alt.Color("Ciclo:N", sort=nomes,
                            scale=alt.Scale(range=[P["g700"], P["ouro"], P["azul"], P["verm"],
                                                   P["terra"], P["g500"], P["amar"], P["cinza"]])),
            tooltip=["Ciclo", "Dia", alt.Tooltip("Mortalidade acumulada (%):Q", format=".2f")],
        )
        st.altair_chart(ui.tema_grafico(linha_g.properties(height=320)), use_container_width=True)
        st.caption("Uma curva que sobe de repente mostra um pico de mortalidade nesses dias.")

    # ---------- falhas que se repetem ----------
    ui.secao("Falhas que se repetem", "tiradas da nota técnica de cada ciclo")
    contagem = Counter(a for i in escolhidos for a in linhas[i]["_areas"])
    if not contagem:
        st.success("Nenhum dos ciclos escolhidos tem falhas na nota técnica.")
    else:
        rep = pd.DataFrame([
            {"Área": a, "Em quantos ciclos": n,
             "Ciclos": ", ".join(nm for i, nm in zip(escolhidos, nomes) if a in linhas[i]["_areas"])}
            for a, n in contagem.most_common()
        ])
        st.dataframe(rep, hide_index=True, width="stretch")
        repetidas = [a for a, n in contagem.items() if n == len(escolhidos)]
        if repetidas:
            st.warning("Aparecem em todos os ciclos escolhidos: " + ", ".join(repetidas).lower()
                       + ". São estes os pontos a atacar primeiro no próximo lote.")
        st.caption("O detalhe de cada falha e o que melhorar estão na nota técnica do ciclo, em Relatórios.")

    # ---------- exportar ----------
    numeros = []
    for chave, nome, casas, _d, _e in inds:
        linha_n = {"Indicador": nome}
        for i, nm in zip(escolhidos, nomes):
            v = linhas[i].get(chave)
            falta = v is None or (chave in ZERO_E_FALTA and v == 0)
            linha_n[nm] = None if falta else round(float(v), casas)
        numeros.append(linha_n)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(numeros).to_excel(xw, sheet_name="Comparacao", index=False)
        xw.sheets["Comparacao"].column_dimensions["A"].width = 36
        if contagem:
            rep.to_excel(xw, sheet_name="Falhas repetidas", index=False)
    st.download_button("Transferir a comparação em Excel", data=buf.getvalue(),
                       file_name="comparacao_ciclos.xlsx", icon=":material/download:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
