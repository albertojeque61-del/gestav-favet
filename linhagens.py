"""
Linhagens de referência: valores esperados por idade (peso, ICA e
mortalidade acumulada) usados para comparar cada ciclo com a sua linhagem.
O chefe ou o administrador podem acrescentar linhagens novas, corrigir valores e
definir o critério de uniformidade para o alerta de abate.
"""

import io

import altair as alt
import pandas as pd
import streamlit as st

import perfis

import estilo as ui
from estilo import P
from database import (
    conectar, ler_df, listar_linhagens, guardar_linhagem, apagar_linhagem,
    uniformidade_minima, definir_config,
)

COLUNAS = {
    "dia": "Dia",
    "peso_medio_g": "Peso médio (g)",
    "ica_acumulado": "ICA acumulado",
    "mortalidade_acumulada_pct": "Mortalidade acum. (%)",
}
CONFIG_COLUNAS = {
    "Dia": st.column_config.NumberColumn(min_value=0, max_value=90, step=1, format="%d", required=True),
    "Peso médio (g)": st.column_config.NumberColumn(min_value=0.0, step=1.0, format="%.0f"),
    "ICA acumulado": st.column_config.NumberColumn(min_value=0.0, step=0.001, format="%.3f"),
    "Mortalidade acum. (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.1, format="%.1f"),
}


def _tabela_modelo() -> pd.DataFrame:
    return pd.DataFrame({
        "Dia": [0, 7, 14, 21, 28, 35, 42],
        "Peso médio (g)": [None] * 7,
        "ICA acumulado": [None] * 7,
        "Mortalidade acum. (%)": [None] * 7,
    }).astype({"Peso médio (g)": float, "ICA acumulado": float, "Mortalidade acum. (%)": float})


def _excel_modelo() -> bytes:
    buf = io.BytesIO()
    _tabela_modelo().rename(columns={v: k for k, v in COLUNAS.items()}).to_excel(
        buf, index=False, sheet_name="referencia")
    return buf.getvalue()


def _validar(df: pd.DataFrame) -> tuple[list[dict] | None, str | None]:
    """Devolve as linhas prontas a gravar ou uma mensagem de erro."""
    df = df.rename(columns={v: k for k, v in COLUNAS.items()}).copy()
    if "dia" not in df.columns or "peso_medio_g" not in df.columns:
        return None, "A tabela precisa pelo menos das colunas do dia e do peso médio."
    df = df.dropna(subset=["dia"])
    df = df[df["peso_medio_g"].notna()]
    if len(df) < 2:
        return None, "Indique o peso médio de pelo menos dois dias (por exemplo, dia 0 e dia 42)."
    if df["dia"].duplicated().any():
        return None, "Há dias repetidos na tabela."
    linhas = []
    for r in df.sort_values("dia").to_dict("records"):
        def val(c):
            v = r.get(c)
            return None if v is None or pd.isna(v) else float(v)
        if val("peso_medio_g") <= 0:
            return None, f"O peso do dia {int(r['dia'])} tem de ser maior que zero."
        linhas.append({
            "dia": int(r["dia"]),
            "peso_medio_g": val("peso_medio_g"),
            "ica_acumulado": val("ica_acumulado"),
            "mortalidade_acumulada_pct": val("mortalidade_acumulada_pct"),
        })
    return linhas, None


def pagina_linhagens():
    ui.cabecalho(
        "Linhagens de referência",
        "Valores esperados por idade para cada linhagem. O sistema usa-os para comparar o peso, "
        "o ICA e a mortalidade de cada ciclo com a linhagem certa.",
        "Administração",
    )
    admin = perfis.edita_linhagens()
    linhagens = listar_linhagens()

    # ---------------- Consultar ----------------
    if linhagens:
        escolha = st.selectbox("Linhagem", linhagens, key="lin_ver")
        with conectar() as conn:
            df = ler_df("""
                SELECT dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct, fonte
                FROM parametros_referencia WHERE linhagem = %s ORDER BY dia
            """, conn, params=(escolha,))
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM ciclos WHERE linhagem = %s", (escolha,))
                n_ciclos = cur.fetchone()["n"]
        fonte = next((f for f in df["fonte"] if f), "")
        tabela = df.drop(columns=["fonte"]).rename(columns=COLUNAS)
        for c in ["Peso médio (g)", "ICA acumulado", "Mortalidade acum. (%)"]:
            tabela[c] = pd.to_numeric(tabela[c], errors="coerce")

        visivel = tabela.copy()
        formatos = {"Peso médio (g)": "{:.0f}", "ICA acumulado": "{:.3f}", "Mortalidade acum. (%)": "{:.1f}"}
        for c, f in formatos.items():
            visivel[c] = visivel[c].map(lambda v, f=f: "–" if pd.isna(v) else f.format(v).replace(".", ","))
        c1, c2 = st.columns([1, 1.2], gap="medium")
        with c1:
            st.dataframe(visivel, hide_index=True, width="stretch")
            st.caption((f"Fonte: {fonte}. " if fonte else "") +
                       f"Usada em {n_ciclos} ciclo(s). Entre os dias da tabela, o sistema calcula "
                       "os valores intermédios.")
        with c2:
            with st.container(border=True, key="caixa_lin"):
                graf = alt.Chart(tabela).mark_line(
                    strokeWidth=3, color=P["ouro"], point=alt.OverlayMarkDef(size=60, filled=True, color=P["ouro"])
                ).encode(
                    x=alt.X("Dia:Q", title="Dia do ciclo"),
                    y=alt.Y("Peso médio (g):Q", title="Peso médio esperado (g)", axis=alt.Axis(format="d")),
                    tooltip=["Dia", alt.Tooltip("Peso médio (g):Q", format=".0f")],
                ).properties(height=260)
                st.altair_chart(ui.tema_grafico(graf), use_container_width=True)
    else:
        ui.vazio("Ainda não há linhagens registadas.")
        escolha, tabela, n_ciclos, fonte = None, pd.DataFrame(), 0, ""

    if not admin:
        st.info("Só o chefe ou o administrador podem acrescentar ou corrigir linhagens.")
        return

    # ---------------- Corrigir ----------------
    if escolha:
        ui.secao("Corrigir esta linhagem", escolha)
        with st.expander(f"Editar os valores da {escolha}"):
            editada = st.data_editor(
                tabela.copy(), key=f"lin_ed_{escolha}",
                num_rows="dynamic", hide_index=True, width="stretch", column_config=CONFIG_COLUNAS,
            )
            nova_fonte = st.text_input("Fonte dos valores", value=fonte, key=f"lin_fonte_{escolha}")
            b1, b2 = st.columns(2)
            if b1.button("Guardar alterações", type="primary", icon=":material/save:", key="lin_guardar"):
                linhas, erro = _validar(editada)
                if erro:
                    st.error(erro)
                else:
                    guardar_linhagem(escolha, linhas, nova_fonte or None)
                    st.success(f"Linhagem {escolha} actualizada.")
                    st.rerun()
            if n_ciclos == 0:
                if b2.button("Apagar esta linhagem", icon=":material/delete:", key="lin_apagar"):
                    apagar_linhagem(escolha)
                    st.success(f"Linhagem {escolha} apagada.")
                    st.rerun()
            else:
                b2.caption(f"Não pode ser apagada: está a ser usada em {n_ciclos} ciclo(s).")

    # ---------------- Acrescentar ----------------
    ui.secao("Acrescentar uma linhagem nova",
             "os valores vêm normalmente do manual da empresa genética")
    c1, c2 = st.columns(2)
    with c1:
        nome = st.text_input("Nome da linhagem", placeholder="ex.: Hubbard Classic")
    with c2:
        fonte_nova = st.text_input("Fonte dos valores", placeholder="ex.: Manual da Hubbard (2023)")
    aba1, aba2 = st.tabs(["Escrever no ecrã", "Carregar de um Excel"])
    with aba1:
        st.caption("Preencha pelo menos o peso médio de cada dia. O ICA e a mortalidade são opcionais. "
                   "Pode acrescentar ou apagar linhas.")
        nova = st.data_editor(_tabela_modelo(), key="lin_nova", num_rows="dynamic",
                              hide_index=True, width="stretch", column_config=CONFIG_COLUNAS)
        if st.button("Guardar linhagem", type="primary", icon=":material/add:", key="lin_add"):
            if not nome.strip():
                st.error("Escreva o nome da linhagem.")
            elif nome.strip() in linhagens:
                st.error("Já existe uma linhagem com esse nome. Use a secção de correcção acima.")
            else:
                linhas, erro = _validar(nova)
                if erro:
                    st.error(erro)
                else:
                    guardar_linhagem(nome.strip(), linhas, fonte_nova or None)
                    st.success(f"Linhagem {nome.strip()} guardada. Já pode ser escolhida num novo ciclo.")
                    st.rerun()
    with aba2:
        st.download_button("Descarregar o modelo Excel", data=_excel_modelo(),
                           file_name="modelo_linhagem.xlsx", icon=":material/download:",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        fich = st.file_uploader("Ficheiro preenchido", type=["xlsx"], key="lin_xlsx")
        if fich is not None:
            try:
                lido = pd.read_excel(fich)
                lido = lido.rename(columns={k: v for k, v in COLUNAS.items()})
                st.dataframe(lido, hide_index=True, width="stretch")
                if st.button("Guardar linhagem a partir do Excel", type="primary",
                             icon=":material/upload:", key="lin_add_xlsx"):
                    if not nome.strip():
                        st.error("Escreva o nome da linhagem acima.")
                    elif nome.strip() in linhagens:
                        st.error("Já existe uma linhagem com esse nome.")
                    else:
                        linhas, erro = _validar(lido)
                        if erro:
                            st.error(erro)
                        else:
                            guardar_linhagem(nome.strip(), linhas, fonte_nova or None)
                            st.success(f"Linhagem {nome.strip()} guardada.")
                            st.rerun()
            except Exception as e:
                st.error(f"Não foi possível ler o ficheiro: {e}")

    # ---------------- Critério de abate ----------------
    ui.secao("Critério de lote pronto para abate")
    st.markdown(
        "A **uniformidade** é a percentagem de aves da amostra com peso dentro de 10% do peso médio "
        "(para mais ou para menos). Quando o lote chega ao fim definido no ciclo, o sistema avisa que "
        "está pronto para abate se a uniformidade for igual ou superior ao mínimo abaixo; se for "
        "inferior, gera um aviso de uniformidade baixa."
    )
    with st.form("cfg_unif"):
        minimo = st.number_input("Uniformidade mínima (%)", min_value=50, max_value=100, step=1,
                                 value=int(round(uniformidade_minima())))
        if st.form_submit_button("Guardar critério", icon=":material/save:"):
            definir_config("uniformidade_min", str(minimo))
            st.success(f"Uniformidade mínima definida em {minimo}%.")
