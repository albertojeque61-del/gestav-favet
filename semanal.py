"""
Registo semanal e ficha de registo em papel.

Serve para quando não há internet ou computador na granja no próprio dia:
o tratador anota na ficha em papel e, uma vez por semana, alguém lança os
dias em falta de uma só vez. Os dias que já foram registados (no registo
diário ou numa semana anterior) não são alterados.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from fpdf import FPDF

import estilo as ui
from database import conectar, ler_df
from motor_alertas import avaliar, avaliar_abate, guardar_alertas
from relatorios import _sanitizar

COLUNAS_NUM = ["Mortes", "Ração (kg)", "T. máx (°C)", "T. mín (°C)", "Humidade (%)"]


def _data_pt(d) -> str:
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()
    return d.strftime("%d/%m/%Y")


def _vazio(v) -> bool:
    if v is None or v is pd.NA:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return isinstance(v, str) and not v.strip()


def _num(v, campo: str, data_txt: str):
    """Converte o texto de uma célula em número (aceita vírgula decimal).
    Devolve None se estiver vazia."""
    if _vazio(v):
        return None
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"No dia {data_txt}, o valor «{v}» em {campo} não é um número.")


def _txt(v, casas: int = 1) -> str:
    """Número da base de dados para texto com vírgula decimal ('' se vazio)."""
    if _vazio(v) or v == "":
        return ""
    v = float(v)
    if v.is_integer():
        return str(int(v))
    return f"{v:.{casas}f}".replace(".", ",")


# ----------------------------------------------------------------------
# Ficha em papel (PDF para imprimir)
# ----------------------------------------------------------------------
class _Ficha(FPDF):
    def cell(self, w=0, h=0, text="", **kw):
        return super().cell(w, h, _sanitizar(text), **kw)


def gerar_ficha_semanal(ciclo: dict | None, inicio_semana: date) -> bytes:
    """Ficha A4 deitada, com os mesmos campos do registo semanal, mais a
    pesagem da semana e as vacinas/medicamentos."""
    pdf = _Ficha(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_margins(10, 10, 10)
    verde = (31, 77, 43)

    # Cabeçalho
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*verde)
    pdf.cell(0, 8, "GESTAV - Ficha semanal de registo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 5, "Granja da FAVET-UEM. Preencher todos os dias e entregar no fim da semana para lançar no sistema.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_text_color(0, 0, 0)

    fim_semana = inicio_semana + timedelta(days=6)
    pdf.set_font("Helvetica", "", 10)
    codigo = ciclo["codigo"] if ciclo else "________"
    linhagem = ciclo["linhagem"] if ciclo else "________"
    alojadas = f"{ciclo['n_aves_alojadas']:,}".replace(",", ".") if ciclo else "______"
    pdf.cell(70, 6, f"Ciclo: {codigo}")
    pdf.cell(60, 6, f"Linhagem: {linhagem}")
    pdf.cell(55, 6, f"Aves alojadas: {alojadas}")
    semana = (f"{_data_pt(inicio_semana)} a {_data_pt(fim_semana)}" if ciclo
              else "____/____/______ a ____/____/______")
    pdf.cell(0, 6, f"Semana: {semana}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(70, 6, "Área do aviário (m2): ________")
    pdf.cell(60, 6, "Bebedouros a funcionar: ______")
    pdf.cell(0, 6, "Comedouros a funcionar: ______", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Tabela diária
    cab = [("Data", 24), ("Dia", 12), ("Mortes", 18), ("Ração (kg)", 24),
           ("T. máx (°C)", 22), ("T. mín (°C)", 22), ("Humid. (%)", 20),
           ("Água N/E/C", 22), ("Luz N/F", 18), ("Observações", 95)]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(227, 237, 221)
    for t, w in cab:
        pdf.cell(w, 8, t, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    inicio_ciclo = (datetime.strptime(ciclo["data_inicio"], "%Y-%m-%d").date()
                    if ciclo else None)
    for k in range(7):
        d = inicio_semana + timedelta(days=k)
        dia = str((d - inicio_ciclo).days) if inicio_ciclo else ""
        valores = [_data_pt(d) if ciclo else "", dia] + [""] * (len(cab) - 2)
        for (t, w), v in zip(cab, valores):
            pdf.cell(w, 10, v, border=1, align="C")
        pdf.ln()
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 5, "Água: N = normal, E = escassa, C = corte.   Luz: N = normal, F = houve falhas.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Pesagem da semana
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Pesagem da semana (peso de cada ave em gramas)   Data: ____/____/______",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    for linha in range(2):
        for i in range(15):
            n = linha * 15 + i + 1
            x, y = pdf.get_x(), pdf.get_y()
            pdf.cell(18.5, 9, "", border=1)
            pdf.set_xy(x + 0.6, y + 0.4)
            pdf.cell(5, 3, str(n))
            pdf.set_xy(x + 18.5, y)
        pdf.ln(9)
    pdf.ln(2)

    # Vacinas e medicamentos
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Vacinas e medicamentos aplicados", new_x="LMARGIN", new_y="NEXT")
    cab2 = [("Data", 28), ("Vacina / medicamento", 80), ("Para quê", 60),
            ("Dose", 40), ("Via (água, spray, injecção...)", 69)]
    pdf.set_font("Helvetica", "B", 9)
    for t, w in cab2:
        pdf.cell(w, 7, t, border=1, align="C", fill=True)
    pdf.ln()
    for _ in range(2):
        for t, w in cab2:
            pdf.cell(w, 8, "", border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(140, 6, "Preenchido por: ______________________________")
    pdf.cell(0, 6, "Lançado no sistema em: ____/____/______ por: ________________")

    return bytes(pdf.output())


def gravar_dias(cid: int, linhas: list[dict], area: float, n_beb: int, n_com: int) -> tuple[int, list[dict]]:
    """Grava os dias "por lançar" que tenham o consumo de ração preenchido,
    avalia os alertas de cada dia e, no fim, o alerta de abate.
    Devolve (nº de dias gravados, alertas gerados)."""
    novos = [r for r in linhas
             if r["Situação"] == "por lançar" and not _vazio(r["Ração (kg)"])]
    if not novos:
        return 0, []
    # Validar tudo antes de gravar, para não ficar a semana a meio
    for r in novos:
        for campo in COLUNAS_NUM:
            _num(r[campo], campo, r["Data"])
    novos.sort(key=lambda r: datetime.strptime(r["Data"], "%d/%m/%Y"))
    gerados = []
    for r in novos:
        d = datetime.strptime(r["Data"], "%d/%m/%Y").date()
        reg = {
            "data": str(d),
            "mortalidade": int(_num(r["Mortes"], "Mortes", r["Data"]) or 0),
            "consumo_racao_kg": _num(r["Ração (kg)"], "Ração (kg)", r["Data"]),
            "temp_max": _num(r["T. máx (°C)"], "T. máx (°C)", r["Data"]),
            "temp_min": _num(r["T. mín (°C)"], "T. mín (°C)", r["Data"]),
            "humidade": _num(r["Humidade (%)"], "Humidade (%)", r["Data"]),
            "estado_agua": r["Água"] or "normal",
            "estado_electricidade": r["Electricidade"] or "normal",
            "n_bebedouros": int(n_beb), "n_comedouros": int(n_com),
            "area_m2": float(area),
        }
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO registo_diario
                        (ciclo_id, data, dia_ciclo, mortalidade, consumo_racao_kg,
                         temp_max, temp_min, humidade, estado_agua,
                         estado_electricidade, n_bebedouros, n_comedouros,
                         area_m2, observacoes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ciclo_id, data) DO NOTHING
                """, (cid, reg["data"], int(r["Dia"]), reg["mortalidade"],
                      reg["consumo_racao_kg"], reg["temp_max"], reg["temp_min"],
                      reg["humidade"], reg["estado_agua"],
                      reg["estado_electricidade"], reg["n_bebedouros"],
                      reg["n_comedouros"], reg["area_m2"], r["Observações"] or None))
            conn.commit()
        alertas = avaliar(cid, reg)
        guardar_alertas(cid, reg["data"], alertas)
        gerados += [{**a, "data": _data_pt(d)} for a in alertas]
    ultimo_dia = datetime.strptime(novos[-1]["Data"], "%d/%m/%Y").date()
    abate = avaliar_abate(cid, str(ultimo_dia))
    guardar_alertas(cid, str(ultimo_dia), abate)
    gerados += [{**a, "data": _data_pt(ultimo_dia)} for a in abate]
    from stock import verificar_stock
    gerados += [{**a, "data": _data_pt(ultimo_dia)} for a in verificar_stock(cid, str(ultimo_dia))]
    return len(novos), gerados


# ----------------------------------------------------------------------
# Página do registo semanal
# ----------------------------------------------------------------------
def pagina_registo_semanal(selecionar):
    ui.cabecalho(
        "Registo semanal",
        "Para os dias sem internet: anote na ficha em papel e lance aqui a semana inteira de uma vez. "
        "Os dias que já estão registados não são alterados.",
        "Operação diária",
    )
    cid = selecionar("Ciclo", chave="sem_ciclo")
    if cid is None:
        return

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ciclos WHERE id = %s", (cid,))
            ciclo = dict(cur.fetchone())
            cur.execute("""
                SELECT area_m2, n_bebedouros, n_comedouros FROM registo_diario
                WHERE ciclo_id = %s ORDER BY data DESC LIMIT 1
            """, (cid,))
            ultimo = cur.fetchone()
    inicio_ciclo = datetime.strptime(ciclo["data_inicio"], "%Y-%m-%d").date()
    hoje = date.today()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sugestao = max(inicio_ciclo, hoje - timedelta(days=6))
        ini = st.date_input("Primeiro dia da semana", value=sugestao,
                            min_value=inicio_ciclo, format="DD/MM/YYYY", key=f"sem_ini_{cid}")
    with c2:
        area = st.number_input("Área do aviário (m²)", min_value=0.0, step=5.0,
                               value=float(ultimo["area_m2"] or 100) if ultimo else 100.0)
    with c3:
        n_beb = st.number_input("Bebedouros funcionais", min_value=0, step=1,
                                value=int(ultimo["n_bebedouros"] or 20) if ultimo else 20)
    with c4:
        n_com = st.number_input("Comedouros funcionais", min_value=0, step=1,
                                value=int(ultimo["n_comedouros"] or 15) if ultimo else 15)

    dias = [ini + timedelta(days=k) for k in range(7) if ini + timedelta(days=k) <= hoje]
    if not dias:
        ui.vazio("A semana escolhida ainda não começou. Escolha uma data até hoje.")
        return

    with conectar() as conn:
        existentes = ler_df("""
            SELECT data, mortalidade, consumo_racao_kg, temp_max, temp_min, humidade,
                   estado_agua, estado_electricidade, observacoes
            FROM registo_diario WHERE ciclo_id = %s AND data BETWEEN %s AND %s
        """, conn, params=(cid, str(dias[0]), str(dias[-1])))
    ja = {r["data"]: r for r in existentes.to_dict("records")}

    linhas = []
    for d in dias:
        e = ja.get(str(d))
        linhas.append({
            "Data": _data_pt(d),
            "Dia": (d - inicio_ciclo).days,
            "Situação": "já registado" if e else "por lançar",
            "Mortes": _txt(e["mortalidade"], 0) if e else "",
            "Ração (kg)": _txt(e["consumo_racao_kg"]) if e else "",
            "T. máx (°C)": _txt(e["temp_max"]) if e else "",
            "T. mín (°C)": _txt(e["temp_min"]) if e else "",
            "Humidade (%)": _txt(e["humidade"], 0) if e else "",
            "Água": (e["estado_agua"] or "normal") if e else "normal",
            "Electricidade": (e["estado_electricidade"] or "normal") if e else "normal",
            "Observações": (e["observacoes"] or "") if e else "",
        })
    df = pd.DataFrame(linhas)

    st.caption("Preencha só os dias **por lançar** (pode usar vírgula nas casas decimais, ex.: 28,5). "
               "Um dia só é gravado se tiver o consumo de ração preenchido; as mortes em branco contam como zero.")
    editado = st.data_editor(
        df, key=f"sem_tab_{cid}_{ini}", hide_index=True, width="stretch", num_rows="fixed",
        disabled=["Data", "Dia", "Situação"],
        column_config={
            "Mortes": st.column_config.TextColumn(),
            "Ração (kg)": st.column_config.TextColumn(),
            "T. máx (°C)": st.column_config.TextColumn(),
            "T. mín (°C)": st.column_config.TextColumn(),
            "Humidade (%)": st.column_config.TextColumn(),
            "Água": st.column_config.SelectboxColumn(options=["normal", "escassa", "corte"], required=True),
            "Electricidade": st.column_config.SelectboxColumn(options=["normal", "falhas"], required=True),
            "Observações": st.column_config.TextColumn(width="medium"),
        },
    )

    if st.button("Gravar a semana", type="primary", icon=":material/save:"):
        resultado = None
        try:
            resultado = gravar_dias(cid, editado.to_dict("records"), area, n_beb, n_com)
        except Exception as e:
            st.error(f"Não foi possível gravar a semana: {e}")
        if resultado is not None:
            if resultado[0] == 0:
                st.warning("Não há dias novos para gravar. Preencha pelo menos o consumo de ração "
                           "dos dias por lançar.")
            else:
                st.session_state["_semana_gravada"] = resultado
                st.rerun()

    if "_semana_gravada" in st.session_state:
        n, gerados = st.session_state.pop("_semana_gravada")
        st.success(f"{n} dia(s) gravado(s).")
        if gerados:
            ui.secao(f"{len(gerados)} alerta(s) gerado(s) nesta semana",
                     "cada alerta mostra o dia a que se refere")
            for a in gerados:
                st.markdown(ui.alerta_html({**a, "ciclo_codigo": ciclo["codigo"]}),
                            unsafe_allow_html=True)
        else:
            st.info("Nenhum alerta nesta semana. Dias dentro da normalidade.")

    ui.secao("Ficha em papel para imprimir",
             "mesmos campos deste ecrã, mais a pesagem e as vacinas da semana")
    st.markdown("Imprima uma ficha por semana e deixe-a no aviário. O tratador preenche à mão "
                "todos os dias e, no fim da semana, os valores são lançados neste ecrã.")
    f1, f2 = st.columns(2)
    with f1:
        st.download_button(
            "Ficha desta semana (com o ciclo)",
            data=gerar_ficha_semanal(ciclo, ini),
            file_name=f"ficha_semanal_{ciclo['codigo']}_{ini:%Y%m%d}.pdf",
            mime="application/pdf", icon=":material/print:", width="stretch",
        )
    with f2:
        st.download_button(
            "Ficha em branco",
            data=gerar_ficha_semanal(None, ini),
            file_name="ficha_semanal_em_branco.pdf",
            mime="application/pdf", icon=":material/description:", width="stretch",
        )
