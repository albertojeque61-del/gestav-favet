"""
GESTAV — Sistema de Gestão Técnico-Económica da Unidade Avícola
FAVET — Universidade Eduardo Mondlane
Autor: Alberto Jeque Júnior
Licenciatura em Ciência e Tecnologia Animal
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os

from database import conectar, inicializar_bd
from auth import validar_credenciais, criar_admin_padrao, registar_utilizador
from calculos import (
    resumo_ciclo, semaforos, mortalidade_acumulada,
    conversao_alimentar, ganho_medio_diario, iep,
    custos_totais, receitas_totais, margens, ponto_equilibrio,
)
from sensibilidade import tabela_cenarios, simular
from relatorios import gerar_relatorio_ciclo
from motor_alertas import (
    avaliar, guardar_alertas, listar_alertas_abertos, resolver_alerta,
)
from importar import pagina_importar


# ======================================================================
# Configuração da página
# ======================================================================
st.set_page_config(
    page_title="GESTAV — FAVET/UEM",
    page_icon="🐔",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inicializar BD na primeira execução
inicializar_bd()
criar_admin_padrao()


# ======================================================================
# Autenticação
# ======================================================================
def tela_login():
    st.markdown("<h1 style='text-align:center;'>GESTAV</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:#666;'>"
        "Sistema de Gestão Técnico-Económica da Unidade Avícola<br>"
        "<small>FAVET — Universidade Eduardo Mondlane</small></p>",
        unsafe_allow_html=True,
    )
    st.divider()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login"):
            st.subheader("Iniciar sessão")
            u = st.text_input("Utilizador")
            p = st.text_input("Palavra-passe", type="password")
            if st.form_submit_button("Entrar", use_container_width=True, type="primary"):
                dados = validar_credenciais(u, p)
                if dados:
                    st.session_state.user = dados
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

        st.info("**Primeiro acesso:** utilizador `admin`, palavra-passe `admin123`")


# ======================================================================
# Módulos
# ======================================================================
def modulo_dashboard():
    st.title("📊 Dashboard")

    # Banner de alertas no topo
    alertas_abertos = listar_alertas_abertos()
    criticos = [a for a in alertas_abertos if a["nivel"] == "critico"]
    if criticos:
        st.error(f"🔴 **{len(criticos)} alerta(s) crítico(s) aberto(s)** — veja o módulo Alertas para intervenção imediata.")
        with st.expander("Ver resumo"):
            for a in criticos[:5]:
                st.markdown(f"- **[{a['ciclo_codigo']}]** {a['titulo']}: {a['mensagem']}")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ciclos ORDER BY data_inicio DESC")
            ciclos = cur.fetchall()

    if not ciclos:
        st.info("Ainda não há ciclos registados. Crie um novo ciclo no menu lateral.")
        return

    activos = [c for c in ciclos if c["estado"] == "activo"]
    encerrados = [c for c in ciclos if c["estado"] == "encerrado"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Ciclos activos", len(activos))
    col2.metric("Ciclos encerrados", len(encerrados))
    col3.metric("Total de ciclos", len(ciclos))

    st.divider()

    # Ciclo seleccionado
    opcoes = {f"{c['codigo']} — {c['data_inicio']} ({c['estado']})": c["id"] for c in ciclos}
    escolha = st.selectbox("Seleccionar ciclo", list(opcoes.keys()))
    cid = opcoes[escolha]

    r = resumo_ciclo(cid)

    st.subheader("Indicadores técnicos")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dia do ciclo", r["dia_ciclo"])
    c2.metric("Aves vivas", f"{r['aves_vivas']:,}".replace(",", "."))
    c3.metric("Peso médio (g)", f"{r['peso_actual_g']:.0f}")
    c4.metric("GMD (g/dia)", f"{r['gmd']:.1f}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mortalidade", f"{r['mortalidade_pct']}%")
    c2.metric("Viabilidade", f"{r['viabilidade_pct']}%")
    c3.metric("ICA", f"{r['ica']:.2f}")
    c4.metric("IEP", f"{r['iep']:.0f}")

    st.subheader("Indicadores económicos")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Custo total (MZN)", f"{r['custo_total']:,.0f}".replace(",", "."))
    c2.metric("Receita (MZN)", f"{r['receita']:,.0f}".replace(",", "."))
    c3.metric("Margem bruta", f"{r['margem_bruta_pct']}%")
    c4.metric("Margem líquida", f"{r['margem_liquida_pct']}%")

    st.divider()

    # Semáforos
    st.subheader("Comparação com Ross 308")
    semas = semaforos(cid)
    if semas:
        for nome, (actual, ref, (cor, desvio)) in semas.items():
            emoji = {"verde": "🟢", "amarelo": "🟡", "vermelho": "🔴"}.get(cor, "⚪")
            st.markdown(f"{emoji} **{nome}:** {actual:.1f} (ref. {ref:.1f}, desvio {desvio:+.1f}%)")
    else:
        st.caption("Sem pesagens suficientes para comparar com a referência.")

    # Gráficos
    st.divider()
    st.subheader("Evolução do ciclo")

    with conectar() as conn:
        reg = pd.read_sql_query(
            "SELECT * FROM registo_diario WHERE ciclo_id = %s ORDER BY dia_ciclo",
            conn, params=(cid,))
        pes = pd.read_sql_query(
            "SELECT * FROM pesagens WHERE ciclo_id = %s ORDER BY dia_ciclo",
            conn, params=(cid,))

    g1, g2 = st.columns(2)
    with g1:
        if not pes.empty:
            st.markdown("**Peso médio (g)**")
            st.line_chart(pes.set_index("dia_ciclo")["peso_medio_g"])
    with g2:
        if not reg.empty:
            st.markdown("**Mortalidade diária**")
            st.bar_chart(reg.set_index("dia_ciclo")["mortalidade"])


def modulo_novo_ciclo():
    st.title("🥚 Novo ciclo")

    with st.form("novo_ciclo"):
        col1, col2 = st.columns(2)
        with col1:
            codigo = st.text_input("Código do ciclo", value=f"C{datetime.now():%Y%m}")
            data_inicio = st.date_input("Data de alojamento", value=date.today())
            n_aves = st.number_input("Nº de aves alojadas", min_value=1, value=1000, step=100)
        with col2:
            linhagem = st.selectbox("Linhagem", ["Ross 308", "Cobb 500", "Hubbard", "Outra"])
            sexo = st.selectbox("Sexo", ["Misto", "Macho", "Fêmea"])
            observacoes = st.text_area("Observações (opcional)")

        if st.form_submit_button("Criar ciclo", type="primary"):
            with conectar() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO ciclos
                        (utilizador_id, codigo, data_inicio, n_aves_alojadas,
                         linhagem, sexo, observacoes, estado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'activo')
                """, (st.session_state.user["id"], codigo, str(data_inicio),
                      n_aves, linhagem, sexo, observacoes))
                conn.commit()
            st.success(f"Ciclo **{codigo}** criado com sucesso.")
            st.balloons()


def _selecionar_ciclo(label: str = "Ciclo", apenas_activos: bool = False) -> int | None:
    with conectar() as conn:
        cur = conn.cursor()
        q = "SELECT id, codigo, data_inicio, estado FROM ciclos"
        if apenas_activos:
            q += " WHERE estado = 'activo'"
        q += " ORDER BY data_inicio DESC"
        cur.execute(q)
        ciclos = cur.fetchall()
    if not ciclos:
        st.warning("Sem ciclos disponíveis.")
        return None
    opcoes = {f"{c['codigo']} — {c['data_inicio']} ({c['estado']})": c["id"] for c in ciclos}
    escolha = st.selectbox(label, list(opcoes.keys()))
    return opcoes[escolha]


def modulo_ver_ciclos():
    st.title("📋 Ver ciclos")

    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT c.codigo, c.data_inicio, c.data_fim, c.n_aves_alojadas,
                   c.linhagem, c.sexo, c.estado, u.nome_completo AS responsavel
            FROM ciclos c JOIN utilizadores u ON u.id = c.utilizador_id
            ORDER BY c.data_inicio DESC
        """, conn)

    if df.empty:
        st.info("Nenhum ciclo registado.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Encerrar / reactivar ciclo")
    cid = _selecionar_ciclo("Ciclo")
    if cid:
        with conectar() as conn:
            cur = conn.cursor()
            cur.execute("SELECT estado FROM ciclos WHERE id = %s", (cid,))
            estado = cur.fetchone()["estado"]
        col1, col2 = st.columns(2)
        if estado == "activo":
            with col1:
                if st.button("Encerrar ciclo", type="primary"):
                    with conectar() as conn:
                        conn.cursor().execute("""
                            UPDATE ciclos SET estado='encerrado', data_fim=%s
                            WHERE id = %s
                        """, (str(date.today()), cid))
                        conn.commit()
                    st.success("Ciclo encerrado.")
                    st.rerun()
        else:
            with col1:
                if st.button("Reactivar ciclo"):
                    with conectar() as conn:
                        conn.cursor().execute("UPDATE ciclos SET estado='activo' WHERE id = %s", (cid,))
                        conn.commit()
                    st.success("Ciclo reactivado.")
                    st.rerun()


def modulo_registo_diario():
    st.title("📝 Registo diário")
    cid = _selecionar_ciclo("Ciclo", apenas_activos=True)
    if cid is None:
        return

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT data_inicio FROM ciclos WHERE id = %s", (cid,))
            inicio = datetime.strptime(cur.fetchone()["data_inicio"], "%Y-%m-%d").date()

    with st.form("registo"):
        st.markdown("**Dados zootécnicos**")
        col1, col2, col3 = st.columns(3)
        with col1:
            data_reg = st.date_input("Data", value=date.today())
        with col2:
            mort = st.number_input("Mortalidade (aves)", min_value=0, value=0)
        with col3:
            racao = st.number_input("Consumo de ração (kg)", min_value=0.0, value=0.0, step=0.5)

        st.markdown("**Condições ambientais e operacionais**")
        c1, c2, c3 = st.columns(3)
        with c1:
            temp_max = st.number_input("Temperatura máx. (°C)", min_value=0.0, max_value=50.0, value=28.0, step=0.5)
            temp_min = st.number_input("Temperatura mín. (°C)", min_value=0.0, max_value=50.0, value=20.0, step=0.5)
        with c2:
            humidade = st.number_input("Humidade relativa (%)", min_value=0.0, max_value=100.0, value=60.0, step=1.0)
            area_m2 = st.number_input("Área do aviário (m²)", min_value=0.0, value=100.0, step=5.0)
        with c3:
            estado_agua = st.selectbox("Estado da água", ["normal", "escassa", "corte"])
            estado_luz = st.selectbox("Estado da electricidade", ["normal", "falhas"])

        c4, c5 = st.columns(2)
        with c4:
            n_beb = st.number_input("Bebedouros funcionais", min_value=0, value=20)
        with c5:
            n_com = st.number_input("Comedouros funcionais", min_value=0, value=15)

        obs = st.text_input("Observações (opcional)")

        if st.form_submit_button("Registar", type="primary"):
            dia = (data_reg - inicio).days
            try:
                with conectar() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO registo_diario
                                (ciclo_id, data, dia_ciclo, mortalidade, consumo_racao_kg,
                                 temp_max, temp_min, humidade, estado_agua,
                                 estado_electricidade, n_bebedouros, n_comedouros,
                                 area_m2, observacoes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (cid, str(data_reg), dia, mort, racao,
                              temp_max, temp_min, humidade, estado_agua,
                              estado_luz, n_beb, n_com, area_m2, obs))
                    conn.commit()

                # Avaliar motor de alertas
                registo = {
                    "data": str(data_reg), "mortalidade": mort,
                    "consumo_racao_kg": racao, "temp_max": temp_max,
                    "temp_min": temp_min, "humidade": humidade,
                    "estado_agua": estado_agua, "estado_electricidade": estado_luz,
                    "n_bebedouros": n_beb, "n_comedouros": n_com, "area_m2": area_m2,
                }
                alertas = avaliar(cid, registo)
                guardar_alertas(cid, str(data_reg), alertas)

                st.success(f"Registo do dia {dia} guardado.")

                if alertas:
                    st.warning(f"⚠️ Foram gerados {len(alertas)} alerta(s):")
                    for a in alertas:
                        icone = {"critico": "🔴", "aviso": "🟡", "info": "🔵"}.get(a["nivel"], "⚪")
                        with st.container():
                            st.markdown(f"**{icone} {a['titulo']}** — {a['mensagem']}")
                            st.caption(f"**Recomendação:** {a['recomendacao']}")
                else:
                    st.info("Sem alertas gerados por este registo. Dia dentro da normalidade.")
            except Exception as e:
                st.error(f"Erro: {e}")

    # Histórico
    st.divider()
    st.subheader("Histórico do ciclo")
    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT data, dia_ciclo, mortalidade, consumo_racao_kg, observacoes
            FROM registo_diario WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC
        """, conn, params=(cid,))
    if df.empty:
        st.caption("Sem registos ainda.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def modulo_pesagens():
    st.title("⚖️ Pesagens")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data_inicio FROM ciclos WHERE id = %s", (cid,))
        inicio = datetime.strptime(cur.fetchone()["data_inicio"], "%Y-%m-%d").date()

    with st.form("pesagem"):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_pes = st.date_input("Data da pesagem", value=date.today())
        with col2:
            n_amostra = st.number_input("Nº de aves amostradas", min_value=1, value=20)
        with col3:
            peso_total = st.number_input("Peso total da amostra (kg)", min_value=0.0, value=0.0, step=0.1)

        if st.form_submit_button("Registar pesagem", type="primary"):
            peso_medio_g = (peso_total * 1000) / n_amostra if n_amostra else 0
            dia = (data_pes - inicio).days
            with conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO pesagens
                        (ciclo_id, data, dia_ciclo, n_aves_amostra, peso_medio_g, peso_total_kg)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (cid, str(data_pes), dia, n_amostra, peso_medio_g, peso_total))
                conn.commit()
            st.success(f"Pesagem registada: peso médio = **{peso_medio_g:.1f} g** (dia {dia}).")

    st.divider()
    st.subheader("Histórico de pesagens")
    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT data, dia_ciclo, n_aves_amostra, peso_medio_g, peso_total_kg
            FROM pesagens WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC
        """, conn, params=(cid,))
    if df.empty:
        st.caption("Sem pesagens ainda.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def modulo_custos():
    st.title("💰 Custos")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    CATEGORIAS = ["Pintos do dia", "Ração", "Medicamentos e vacinas",
                  "Cama", "Água e electricidade", "Mão-de-obra",
                  "Combustível e transporte", "Manutenção", "Outros"]

    with st.form("custo"):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_c = st.date_input("Data", value=date.today())
        with col2:
            cat = st.selectbox("Categoria", CATEGORIAS)
        with col3:
            tipo = st.selectbox("Tipo", ["variável", "fixo"])
        valor = st.number_input("Valor (MZN)", min_value=0.0, value=0.0, step=100.0)
        desc = st.text_input("Descrição (opcional)")

        if st.form_submit_button("Registar custo", type="primary"):
            with conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO custos (ciclo_id, data, categoria, tipo, descricao, valor_mzn)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (cid, str(data_c), cat, tipo, desc, valor))
                conn.commit()
            st.success(f"Custo de **{valor:,.2f} MZN** registado.")

    st.divider()
    st.subheader("Resumo de custos")
    c = custos_totais(cid)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total", f"{c['total']:,.2f} MZN")
    col2.metric("Variáveis", f"{c['variavel']:,.2f} MZN")
    col3.metric("Fixos", f"{c['fixo']:,.2f} MZN")

    if c["por_categoria"]:
        st.markdown("**Por categoria**")
        df_cat = pd.DataFrame(
            [(k, v) for k, v in c["por_categoria"].items()],
            columns=["Categoria", "Valor (MZN)"]
        ).sort_values("Valor (MZN)", ascending=False)
        st.dataframe(df_cat, use_container_width=True, hide_index=True)

    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT data, categoria, tipo, descricao, valor_mzn
            FROM custos WHERE ciclo_id = %s
            ORDER BY data DESC, id DESC
        """, conn, params=(cid,))
    if not df.empty:
        st.markdown("**Histórico**")
        st.dataframe(df, use_container_width=True, hide_index=True)


def modulo_vendas():
    st.title("🛒 Vendas")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    with st.form("venda"):
        col1, col2 = st.columns(2)
        with col1:
            data_v = st.date_input("Data", value=date.today())
            n_aves = st.number_input("Nº de aves vendidas", min_value=1, value=100)
            cliente = st.text_input("Cliente (opcional)")
        with col2:
            peso_total = st.number_input("Peso total (kg)", min_value=0.0, value=0.0, step=0.5)
            preco_kg = st.number_input("Preço por kg (MZN)", min_value=0.0, value=380.0, step=5.0)

        if st.form_submit_button("Registar venda", type="primary"):
            with conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO vendas (ciclo_id, data, n_aves, peso_total_kg, preco_por_kg, cliente)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (cid, str(data_v), n_aves, peso_total, preco_kg, cliente))
                conn.commit()
            st.success(f"Venda de **{peso_total:.1f} kg** por **{peso_total*preco_kg:,.2f} MZN** registada.")

    st.divider()
    r = receitas_totais(cid)
    col1, col2, col3 = st.columns(3)
    col1.metric("Receita total (MZN)", f"{r['receita']:,.2f}")
    col2.metric("Kg vendidos", f"{r['kg_vendidos']}")
    col3.metric("Aves vendidas", f"{r['aves_vendidas']:,}".replace(",", "."))

    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT data, n_aves, peso_total_kg, preco_por_kg,
                   (peso_total_kg * preco_por_kg) AS total_mzn, cliente
            FROM vendas WHERE ciclo_id = %s
            ORDER BY data DESC
        """, conn, params=(cid,))
    if not df.empty:
        st.markdown("**Histórico de vendas**")
        st.dataframe(df, use_container_width=True, hide_index=True)


def modulo_indicadores():
    st.title("📈 Indicadores (síntese)")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    r = resumo_ciclo(cid)

    st.subheader("Técnicos")
    df_t = pd.DataFrame({
        "Indicador": ["Dia do ciclo", "Aves vivas", "Mortalidade",
                      "Viabilidade", "Peso médio actual", "GMD",
                      "Consumo ração", "ICA", "IEP"],
        "Valor": [
            f"{r['dia_ciclo']} dias",
            f"{r['aves_vivas']}",
            f"{r['mortalidade_pct']}%",
            f"{r['viabilidade_pct']}%",
            f"{r['peso_actual_g']} g",
            f"{r['gmd']} g/dia",
            f"{r['consumo_racao_kg']} kg",
            f"{r['ica']}",
            f"{r['iep']}",
        ]
    })
    st.dataframe(df_t, use_container_width=True, hide_index=True)

    st.subheader("Económicos")
    df_e = pd.DataFrame({
        "Indicador": ["Custo total", "Custo variável", "Custo fixo",
                      "Custo por kg", "Custo por ave",
                      "Receita", "Margem bruta", "Margem líquida",
                      "Ponto de equilíbrio"],
        "Valor": [
            f"{r['custo_total']:,.2f} MZN",
            f"{r['custo_variavel']:,.2f} MZN",
            f"{r['custo_fixo']:,.2f} MZN",
            f"{r['custo_por_kg']:,.2f} MZN",
            f"{r['custo_por_ave']:,.2f} MZN",
            f"{r['receita']:,.2f} MZN",
            f"{r['margem_bruta']:,.2f} MZN ({r['margem_bruta_pct']}%)",
            f"{r['margem_liquida']:,.2f} MZN ({r['margem_liquida_pct']}%)",
            f"{r['ponto_equilibrio_kg']} kg",
        ]
    })
    st.dataframe(df_e, use_container_width=True, hide_index=True)

    st.subheader("Comparação com Ross 308")
    semas = semaforos(cid)
    if semas:
        linhas = []
        for nome, (actual, ref, (cor, desvio)) in semas.items():
            label = {"verde": "🟢 OK", "amarelo": "🟡 Atenção", "vermelho": "🔴 Crítico"}.get(cor, "⚪")
            linhas.append({
                "Indicador": nome,
                "Actual": f"{actual:.1f}",
                "Referência": f"{ref:.1f}",
                "Desvio": f"{desvio:+.1f}%",
                "Estado": label,
            })
        st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)


def modulo_sensibilidade():
    st.title("📊 Análise de sensibilidade")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    st.markdown(
        "Simule variações do **preço de venda por kg** e do **preço da ração** "
        "para avaliar o impacto na margem líquida."
    )

    col1, col2 = st.columns(2)
    with col1:
        var_preco = st.slider("Variação do preço de venda (%)", -30, 30, 0, step=5)
    with col2:
        var_racao = st.slider("Variação do preço da ração (%)", -30, 50, 0, step=5)

    s = simular(cid, var_preco, var_racao)
    c1, c2, c3 = st.columns(3)
    c1.metric("Nova receita (MZN)", f"{s['receita']:,.2f}")
    c2.metric("Novo custo total (MZN)", f"{s['custo_total']:,.2f}")
    c3.metric("Nova margem líquida", f"{s['margem_liquida']:,.2f} MZN ({s['margem_liquida_pct']}%)")

    st.divider()
    st.subheader("Grelha de cenários")
    cenarios = tabela_cenarios(cid)
    df = pd.DataFrame(cenarios)
    pivot = df.pivot_table(
        index="var_preco_venda",
        columns="var_preco_racao",
        values="margem_liquida",
    )
    pivot.index = [f"Venda {int(i):+d}%" for i in pivot.index]
    pivot.columns = [f"Ração {int(c):+d}%" for c in pivot.columns]

    st.caption("Margem líquida (MZN) para cada combinação de variações.")
    st.dataframe(
        pivot.style.format("{:,.0f}").background_gradient(cmap="RdYlGn"),
        use_container_width=True,
    )


def modulo_relatorios():
    st.title("📄 Relatórios")
    cid = _selecionar_ciclo("Ciclo")
    if cid is None:
        return

    st.markdown("Gere um relatório completo do ciclo em formato PDF.")
    if st.button("Gerar PDF", type="primary"):
        try:
            caminho = gerar_relatorio_ciclo(cid)
            with open(caminho, "rb") as f:
                st.download_button(
                    "⬇️ Transferir PDF",
                    data=f.read(),
                    file_name=os.path.basename(caminho),
                    mime="application/pdf",
                    use_container_width=True,
                )
            st.success(f"Relatório gerado: {os.path.basename(caminho)}")
        except Exception as e:
            st.error(f"Erro ao gerar relatório: {e}")


def modulo_alertas():
    st.title("⚠️ Alertas e apoio à decisão diária")

    opcoes = {"Todos os ciclos activos": None}
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, codigo FROM ciclos WHERE estado='activo' ORDER BY data_inicio DESC")
            for row in cur.fetchall():
                opcoes[f"Apenas ciclo {row['codigo']}"] = row["id"]
    escolha = st.selectbox("Filtro", list(opcoes.keys()))
    cid_filtro = opcoes[escolha]

    alertas = listar_alertas_abertos(cid_filtro)

    if not alertas:
        st.success("✅ Sem alertas abertos no momento.")
        return

    criticos = [a for a in alertas if a["nivel"] == "critico"]
    avisos = [a for a in alertas if a["nivel"] == "aviso"]
    infos = [a for a in alertas if a["nivel"] == "info"]

    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Críticos", len(criticos))
    c2.metric("🟡 Avisos", len(avisos))
    c3.metric("🔵 Informativos", len(infos))

    st.divider()

    for a in alertas:
        icone = {"critico": "🔴", "aviso": "🟡", "info": "🔵"}.get(a["nivel"], "⚪")
        with st.expander(f"{icone} [{a['ciclo_codigo']} · {a['data']}] {a['titulo']}", expanded=(a["nivel"] == "critico")):
            st.markdown(f"**{a['mensagem']}**")
            st.markdown(f"💡 **Recomendação:** {a['recomendacao']}")
            with st.form(f"resolver_{a['id']}"):
                accao = st.text_area(
                    "Acção correctiva tomada",
                    placeholder="Descreva o que foi feito para resolver o alerta...",
                    height=80,
                )
                if st.form_submit_button("Marcar como resolvido", type="primary"):
                    if accao.strip():
                        resolver_alerta(a["id"], accao)
                        st.success("Alerta marcado como resolvido.")
                        st.rerun()
                    else:
                        st.warning("Descreva a acção tomada antes de marcar como resolvido.")

    # Histórico de alertas resolvidos
    st.divider()
    st.subheader("Histórico de alertas resolvidos")
    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT c.codigo AS ciclo, a.data, a.nivel, a.titulo,
                   a.accao_tomada, a.resolvido_em
            FROM alertas a JOIN ciclos c ON c.id = a.ciclo_id
            WHERE a.resolvido = TRUE
            ORDER BY a.resolvido_em DESC LIMIT 50
        """, conn)
    if df.empty:
        st.caption("Sem alertas resolvidos registados.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def modulo_utilizadores():
    st.title("👥 Utilizadores")
    if st.session_state.user["papel"] != "administrador":
        st.warning("Apenas administradores podem gerir utilizadores.")
        return

    with conectar() as conn:
        df = pd.read_sql_query("""
            SELECT username, nome_completo, papel, criado_em
            FROM utilizadores ORDER BY criado_em DESC
        """, conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Registar novo utilizador")
    with st.form("novo_user"):
        col1, col2 = st.columns(2)
        with col1:
            u = st.text_input("Utilizador (username)")
            n = st.text_input("Nome completo")
        with col2:
            p = st.text_input("Palavra-passe", type="password")
            papel = st.selectbox("Papel", ["operador", "administrador"])
        if st.form_submit_button("Criar"):
            if registar_utilizador(u, n, p, papel):
                st.success("Utilizador criado.")
                st.rerun()
            else:
                st.error("Esse username já existe.")


# ======================================================================
# Encaminhador
# ======================================================================
def main():
    if "user" not in st.session_state:
        tela_login()
        return

    user = st.session_state.user

    with st.sidebar:
        st.markdown(f"### 👤 {user['nome_completo']}")
        st.caption(f"@{user['username']} ({user['papel']})")
        st.divider()

        # Contar alertas abertos para badge
        try:
            n_alertas = len(listar_alertas_abertos())
        except Exception:
            n_alertas = 0
        label_alertas = f"⚠️ Alertas ({n_alertas})" if n_alertas else "⚠️ Alertas"

        modulos = {
            "📊 Dashboard": modulo_dashboard,
            label_alertas: modulo_alertas,
            "🥚 Novo ciclo": modulo_novo_ciclo,
            "📥 Importar ciclo histórico": pagina_importar,
            "📋 Ver ciclos": modulo_ver_ciclos,
            "📝 Registo diário": modulo_registo_diario,
            "⚖️ Pesagens": modulo_pesagens,
            "💰 Custos": modulo_custos,
            "🛒 Vendas": modulo_vendas,
            "📈 Indicadores": modulo_indicadores,
            "📊 Análise de sensibilidade": modulo_sensibilidade,
            "📄 Relatórios (PDF)": modulo_relatorios,
            "👥 Utilizadores": modulo_utilizadores,
        }

        escolha = st.radio("Menu", list(modulos.keys()), label_visibility="collapsed")

        st.divider()
        if st.button("Terminar sessão", use_container_width=True):
            del st.session_state.user
            st.rerun()

        st.caption("GESTAV v1.0 — FAVET/UEM")

    modulos[escolha]()


if __name__ == "__main__":
    main()
