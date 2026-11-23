"""
GESTAV · Sistema de Gestão Técnico-Económica da Granja da FAVET-UEM
Faculdade de Veterinária, Universidade Eduardo Mondlane
Autor: Alberto Jeque Júnior
Licenciatura em Ciência e Tecnologia Animal
"""

import os
from datetime import datetime, date

import altair as alt
import pandas as pd
import streamlit as st

from database import (
    conectar, inicializar_bd, ler_df, listar_linhagens, uniformidade_minima,
)
from auth import (
    validar_credenciais, criar_admin_padrao, registar_utilizador,
    mudar_palavra_passe, definir_palavra_passe, admin_com_senha_padrao, SENHA_PADRAO,
)
from calculos import (
    resumo_ciclo, semaforos, custos_totais, receitas_totais,
    ler_pesos, calcular_uniformidade, progresso_fim, descrever_fim,
)
from sensibilidade import tabela_cenarios, simular
from relatorios import gerar_relatorio_ciclo
from motor_alertas import (
    avaliar, avaliar_abate, guardar_alertas, listar_alertas_abertos, resolver_alerta,
)
from importar import pagina_importar
from semanal import pagina_registo_semanal
from linhagens import pagina_linhagens
import estilo as ui
from estilo import P, num, mzn, icone


# ======================================================================
# Configuração da página
# ======================================================================
st.set_page_config(
    page_title="GESTAV · FAVET-UEM",
    page_icon="🐔",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.aplicar_estilo()


@st.cache_resource(show_spinner=False)
def _preparar_bd():
    """Cria as tabelas e o utilizador admin uma única vez por sessão do servidor."""
    inicializar_bd()
    criar_admin_padrao()
    return True


_preparar_bd()


# ======================================================================
# Auxiliares de dados
# ======================================================================
def _ciclos(apenas_activos: bool = False) -> list[dict]:
    with conectar() as conn:
        with conn.cursor() as cur:
            q = "SELECT * FROM ciclos"
            if apenas_activos:
                q += " WHERE estado = 'activo'"
            q += " ORDER BY data_inicio DESC"
            cur.execute(q)
            return [dict(r) for r in cur.fetchall()]


def _selecionar_ciclo(label: str = "Ciclo", apenas_activos: bool = False,
                      chave: str | None = None) -> int | None:
    ciclos = _ciclos(apenas_activos)
    if not ciclos:
        ui.vazio("Ainda não há ciclos disponíveis. Crie um ciclo novo ou importe um ciclo histórico.")
        return None
    opcoes = {
        f"{c['codigo']}  ·  início {ui.data_curta(c['data_inicio'])}  ·  {c['estado']}": c["id"]
        for c in ciclos
    }
    escolha = st.selectbox(label, list(opcoes.keys()), key=chave)
    return opcoes[escolha]


def _referencia(linhagem: str) -> pd.DataFrame:
    with conectar() as conn:
        return ler_df(
            "SELECT dia, peso_medio_g FROM parametros_referencia "
            "WHERE linhagem = %s ORDER BY dia",
            conn, params=(linhagem,),
        )


def _dia_ciclo(ciclo: dict, resumo: dict) -> int:
    """Dia actual para ciclos activos; para ciclos encerrados, o último dia com dados."""
    if ciclo.get("estado") == "activo":
        inicio = datetime.strptime(ciclo["data_inicio"], "%Y-%m-%d").date()
        return max(0, (date.today() - inicio).days)
    return resumo["dia_ciclo"]


def _cartoes_margem(r: dict) -> list[str]:
    if not r["receita"]:
        return [
            ui.kpi_html("Margem bruta", "–", "", "ainda sem vendas registadas", "percent", "neutro"),
            ui.kpi_html("Margem líquida", "–", "", "ainda sem vendas registadas", "percent", "neutro"),
        ]
    tb = "verde" if r["margem_bruta"] >= 0 else "verm"
    tl = "verde" if r["margem_liquida"] >= 0 else "verm"
    return [
        ui.kpi_html("Margem bruta", num(r["margem_bruta_pct"], 1), "%", mzn(r["margem_bruta"]), "percent", tb),
        ui.kpi_html("Margem líquida", num(r["margem_liquida_pct"], 1), "%", mzn(r["margem_liquida"]), "percent", tl),
    ]


def _cartao_roi(r: dict) -> str:
    if r.get("roi_pct") is None:
        return ui.kpi_html("Retorno do investimento", "–", "", "ainda sem vendas registadas", "subida", "neutro")
    tom = "verde" if r["roi_pct"] >= 0 else "verm"
    return ui.kpi_html("Retorno do investimento", num(r["roi_pct"], 1), "%",
                       "lucro por cada 100 MZN gastos", "subida", tom)


def _cartao_fim(ciclo: dict, r: dict, dia: int) -> str:
    p = progresso_fim(ciclo, dia, r["peso_actual_g"])
    if p["valor"] is None:
        return ui.kpi_html("Fim do ciclo", "–", "", p["nota"], "calendario", "neutro")
    if ciclo.get("estado") != "activo":
        return ui.kpi_html("Fim do ciclo", "encerrado", "", f"critério: {descrever_fim(ciclo)}", "calendario", "neutro")
    if p["atingido"]:
        return ui.kpi_html("Fim do ciclo", "atingido", "", p["nota"], "ok", "azul")
    casas = 0
    return ui.kpi_html("Fim do ciclo", f"faltam {num(p['valor'], casas)}", p["unidade"], p["nota"],
                       "calendario", "neutro")


def _cartao_uniformidade(r: dict) -> str | None:
    if r.get("uniformidade_pct") is None:
        return None
    minimo = uniformidade_minima()
    tom = "verde" if r["uniformidade_pct"] >= minimo else "amar"
    nota = f"mínimo {num(minimo)}%"
    if r.get("cv_pct") is not None:
        nota += f" · CV {num(r['cv_pct'], 1)}%"
    return ui.kpi_html("Uniformidade", num(r["uniformidade_pct"], 0), "%", nota, "camada", tom)


def _controlo_fim(prefixo: str, ciclo: dict | None = None) -> tuple[str, int, float | None]:
    """Campos para escolher como termina o ciclo. Devolve (tipo, idade, peso_g)."""
    tipo_actual = (ciclo or {}).get("fim_tipo", "idade")
    idade_actual = int((ciclo or {}).get("fim_idade") or 42)
    peso_actual = float((ciclo or {}).get("fim_peso_g") or 1700)
    opcoes = ["Por idade (dias)", "Por peso-alvo (g)"]
    escolha = st.radio("Como termina o ciclo", opcoes, horizontal=True,
                       index=1 if tipo_actual == "peso" else 0, key=f"{prefixo}_fim_tipo")
    if escolha == opcoes[0]:
        idades = ["35 dias", "42 dias", "Outra idade"]
        pre = {35: 0, 42: 1}.get(idade_actual, 2)
        c1, c2 = st.columns(2)
        sel = c1.selectbox("Idade de abate", idades, index=pre, key=f"{prefixo}_fim_idade")
        if sel == "Outra idade":
            idade = c2.number_input("Idade (dias)", min_value=21, max_value=70, step=1,
                                    value=idade_actual if pre == 2 else 30, key=f"{prefixo}_fim_outra")
        else:
            idade = int(sel.split()[0])
        return "idade", int(idade), None
    peso = st.number_input("Peso-alvo de abate (g)", min_value=800.0, max_value=4500.0, step=50.0,
                           value=peso_actual, key=f"{prefixo}_fim_peso",
                           help="O ciclo dá-se por terminado quando o peso médio da pesagem atingir este valor.")
    return "peso", idade_actual, float(peso)


DESTINOS = ["Comunidade FAVET", "Comunidade vizinha", "UEM", "Outro"]


def _ir_para(pagina: str):
    st.session_state.pagina = pagina


# ======================================================================
# Ecrã de entrada
# ======================================================================
def tela_login():
    esq, dir_ = st.columns([1.15, 1], gap="large")
    with esq:
        itens = [
            ("pulso", "Registo diário com alertas automáticos"),
            ("subida", "Indicadores técnicos comparados com a linhagem"),
            ("carteira", "Custos, receitas e margens por ciclo"),
            ("camada", "Análise de ciclos passados e cenários"),
        ]
        lista = "".join(
            f"<li><span>{icone(i, 15, '#F3D9A6')}</span>{t}</li>" for i, t in itens
        )
        st.markdown(
            f"""<div class="gv-login-arte">
            <div>{ui.logo_svg(56)}
            <h1>GESTAV</h1>
            <p class="lema">Gestão técnico-económica da produção de frangos de corte na granja da FAVET-UEM.</p>
            <ul>{lista}</ul></div>
            <footer>Faculdade de Veterinária · Universidade Eduardo Mondlane</footer>
            </div>""",
            unsafe_allow_html=True,
        )
    with dir_:
        st.markdown(
            '<div class="gv-login-titulo"><h2>Iniciar sessão</h2>'
            "<p>Entre com o seu utilizador para aceder ao painel da granja.</p></div>",
            unsafe_allow_html=True,
        )
        with st.form("login"):
            u = st.text_input("Utilizador", placeholder="ex.: admin")
            p = st.text_input("Palavra-passe", type="password", placeholder="••••••••")
            if st.form_submit_button("Entrar", type="primary", width="stretch",
                                     icon=":material/login:"):
                dados = validar_credenciais(u.strip(), p)
                if dados:
                    st.session_state.user = dados
                    st.session_state.pagina = "inicio"
                    st.session_state.aviso_pw = (p == SENHA_PADRAO)
                    st.rerun()
                else:
                    st.error("Utilizador ou palavra-passe incorrectos.")
        # A dica só aparece enquanto a conta admin mantiver a palavra-passe de origem
        if admin_com_senha_padrao():
            st.markdown(
                '<div class="gv-dica-acesso"><b>Primeiro acesso:</b> utilizador '
                "<code>admin</code> e palavra-passe <code>admin123</code>. "
                "Mude a palavra-passe depois de entrar.</div>",
                unsafe_allow_html=True,
            )


# ======================================================================
# Início
# ======================================================================
def modulo_inicio():
    user = st.session_state.user
    activos = _ciclos(apenas_activos=True)
    alertas = listar_alertas_abertos()
    criticos = [a for a in alertas if a["nivel"] == "critico"]
    aves = sum(c["n_aves_alojadas"] for c in activos)
    primeiro_nome = user["nome_completo"].split()[0] if user["nome_completo"] else ""

    st.markdown(
        f"""<div class="gv-hero">
        <div class="marca-agua">{ui.logo_svg(190)}</div>
        <div class="data">{ui.data_extenso()}</div>
        <h1>{ui.saudacao()}, {primeiro_nome}.</h1>
        <p>Este é o ponto de partida da gestão da granja: registe o dia, acompanhe os
        indicadores e responda aos alertas antes que os problemas cresçam.</p>
        <div class="gv-hero-stats">
          <div><b>{len(activos)}</b>ciclo(s) em curso</div>
          <div><b>{num(aves)}</b>aves alojadas</div>
          <div><b>{len(alertas)}</b>alerta(s) abertos</div>
          <div><b>{len(criticos)}</b>crítico(s)</div>
        </div></div>""",
        unsafe_allow_html=True,
    )

    ui.secao("Acções rápidas")
    with st.container(key="atalhos"):
        c1, c2, c3, c4 = st.columns(4)
        c1.button("Registar o dia", icon=":material/edit_note:", width="stretch",
                  on_click=_ir_para, args=("registo",))
        c2.button("Nova pesagem", icon=":material/scale:", width="stretch",
                  on_click=_ir_para, args=("pesagens",))
        c3.button("Ver alertas", icon=":material/notifications:", width="stretch",
                  on_click=_ir_para, args=("alertas",))
        c4.button("Novo ciclo", icon=":material/add_circle:", width="stretch",
                  on_click=_ir_para, args=("novo",))

    ui.secao("Ciclos em curso", "situação actual de cada lote")
    if not activos:
        ui.vazio("Não há ciclos activos neste momento. Comece por criar um ciclo novo.")
        return

    cartoes = []
    for c in activos:
        r = resumo_ciclo(c["id"])
        semas = semaforos(c["id"])
        estado = "verde"
        if semas:
            cores = [v[2][0] for v in semas.values()]
            estado = "verm" if "vermelho" in cores else ("amar" if "amarelo" in cores else "verde")
        n_al = len([a for a in alertas if a["ciclo_id"] == c["id"]])
        nota = f"{n_al} alerta(s) aberto(s)" if n_al else "sem alertas abertos"
        cartoes.append(ui.kpi_html(
            f"Ciclo {c['codigo']} · dia {_dia_ciclo(c, r)}",
            num(r["aves_vivas"]), "aves vivas",
            f"Mortalidade {num(r['mortalidade_pct'], 1)}% · peso {num(r['peso_actual_g'])} g · {nota}",
            "ovo", estado,
        ))
    ui.grelha(cartoes, minimo=300, preencher=True)


# ======================================================================
# Painel do ciclo
# ======================================================================
def modulo_dashboard():
    ui.cabecalho("Painel do ciclo",
                 "Indicadores técnicos e económicos do lote seleccionado, comparados com a referência da linhagem.",
                 "Visão geral")

    alertas_abertos = listar_alertas_abertos()
    criticos = [a for a in alertas_abertos if a["nivel"] == "critico"]
    if criticos:
        ui.faixa_alerta(len(criticos))

    ciclos = _ciclos()
    if not ciclos:
        ui.vazio("Ainda não há ciclos registados. Crie um ciclo novo no menu lateral.")
        return

    cid = _selecionar_ciclo("Ciclo em análise", chave="dash_ciclo")
    ciclo = next(c for c in ciclos if c["id"] == cid)
    r = resumo_ciclo(cid)

    ui.secao("Indicadores técnicos")
    tom_mort = "verde" if r["mortalidade_pct"] <= 5 else ("amar" if r["mortalidade_pct"] <= 8 else "verm")
    dia = _dia_ciclo(ciclo, r)
    extra = [_cartao_fim(ciclo, r, dia)]
    unif = _cartao_uniformidade(r)
    if unif:
        extra.append(unif)
    ui.grelha(extra + [
        ui.kpi_html("Dia do ciclo", str(dia), "dias", f"início em {ui.data_curta(ciclo['data_inicio'])}", "calendario", "neutro"),
        ui.kpi_html("Aves vivas", num(r["aves_vivas"]), "", f"de {num(ciclo['n_aves_alojadas'])} alojadas", "ovo", "verde"),
        ui.kpi_html("Peso médio", num(r["peso_actual_g"]), "g", "última pesagem", "peso", "verde"),
        ui.kpi_html("Ganho médio diário", num(r["gmd"], 1), "g/dia", "", "subida", "verde"),
        ui.kpi_html("Mortalidade", num(r["mortalidade_pct"], 1), "%", f"{num(r['mortalidade_total'])} aves", "pulso", tom_mort),
        ui.kpi_html("Viabilidade", num(r["viabilidade_pct"], 1), "%", "", "escudo", "verde"),
        ui.kpi_html("Conversão alimentar", num(r["ica"], 2), "", "kg ração por kg de peso", "ciclo", "ouro"),
        ui.kpi_html("Índice de eficiência", num(r["iep"]), "", "IEP", "medalha", "ouro"),
    ])

    ui.secao("Indicadores económicos")
    ui.grelha([
        ui.kpi_html("Custo total", num(r["custo_total"]), "MZN", f"{mzn(r['custo_por_ave'], 2)} por ave", "carteira", "ouro"),
        ui.kpi_html("Receita", num(r["receita"]), "MZN", f"{num(r['kg_vendidos'], 1)} kg vendidos", "nota", "verde"),
    ] + _cartoes_margem(r) + [_cartao_roi(r)])

    ui.secao("Comparação com a referência", ciclo["linhagem"])
    semas = semaforos(cid)
    if semas:
        casas = {"Peso médio (g)": 0, "ICA": 2}
        cols = st.columns(len(semas))
        for col, (nome, (actual, ref, (cor, desvio))) in zip(cols, semas.items()):
            col.markdown(ui.semaforo_html(nome, actual, ref, cor, desvio, casas.get(nome, 1)),
                         unsafe_allow_html=True)
    else:
        ui.vazio("Sem pesagens suficientes para comparar com a referência.")

    with conectar() as conn:
        reg = ler_df(
            "SELECT dia_ciclo, mortalidade, consumo_racao_kg FROM registo_diario "
            "WHERE ciclo_id = %s ORDER BY dia_ciclo", conn, params=(cid,))
        pes = ler_df(
            "SELECT dia_ciclo, peso_medio_g FROM pesagens WHERE ciclo_id = %s "
            "ORDER BY dia_ciclo", conn, params=(cid,))

    ui.secao("Evolução do ciclo")
    g1, g2 = st.columns(2, gap="medium")
    with g1:
        with st.container(border=True, key="caixa_1"):
            st.markdown("**Peso médio vs referência**")
            if pes.empty:
                st.caption("Sem pesagens registadas.")
            else:
                ref = _referencia(ciclo["linhagem"])
                ref = ref[ref["dia"] <= max(pes["dia_ciclo"].max() + 7, 7)]
                dados = pd.concat([
                    pes.rename(columns={"dia_ciclo": "Dia", "peso_medio_g": "Peso"}).assign(Série="Peso real"),
                    ref.rename(columns={"dia": "Dia", "peso_medio_g": "Peso"}).assign(Série=f"Referência {ciclo['linhagem']}"),
                ])
                nome_ref = f"Referência {ciclo['linhagem']}"
                dominio = ["Peso real", nome_ref]
                cor = alt.Color("Série:N", title=None,
                                scale=alt.Scale(domain=dominio, range=[P["g700"], P["ouro"]]),
                                legend=alt.Legend(orient="top", symbolStrokeWidth=3))
                eixo_x = alt.X("Dia:Q", title="Dia do ciclo")
                eixo_y = alt.Y("Peso:Q", title="Peso médio (g)", axis=alt.Axis(format="d"))
                dica = ["Série", "Dia", alt.Tooltip("Peso:Q", format=".0f", title="Peso (g)")]
                linha_ref = alt.Chart(dados[dados["Série"] == nome_ref]).mark_line(
                    strokeWidth=2.5, strokeDash=[6, 4]).encode(x=eixo_x, y=eixo_y, color=cor, tooltip=dica)
                linha_real = alt.Chart(dados[dados["Série"] == "Peso real"]).mark_line(
                    strokeWidth=3.5, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
                    x=eixo_x, y=eixo_y, color=cor, tooltip=dica)
                graf = (linha_ref + linha_real).properties(height=260)
                st.altair_chart(ui.tema_grafico(graf), use_container_width=True)
    with g2:
        with st.container(border=True, key="caixa_2"):
            st.markdown("**Mortalidade diária**")
            if reg.empty:
                st.caption("Sem registos diários.")
            else:
                limite = max(3, round(ciclo["n_aves_alojadas"] * 0.005))
                d = reg.rename(columns={"dia_ciclo": "Dia", "mortalidade": "Mortes"})
                barras = alt.Chart(d).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("Dia:O", title="Dia do ciclo", axis=alt.Axis(labelAngle=0, labelOverlap=True)),
                    y=alt.Y("Mortes:Q", title="Aves mortas", axis=alt.Axis(format="d", tickMinStep=1)),
                    color=alt.condition(alt.datum.Mortes > limite, alt.value(P["verm"]), alt.value(P["g500"])),
                    tooltip=["Dia", "Mortes"],
                )
                linha = alt.Chart(pd.DataFrame({"y": [limite]})).mark_rule(
                    color=P["verm"], strokeDash=[5, 4], opacity=.7).encode(y="y:Q")
                st.altair_chart(ui.tema_grafico((barras + linha).properties(height=260)),
                                use_container_width=True)
                st.caption(f"Barras a vermelho: dias acima de {limite} mortes (0,5% do lote).")

    if not reg.empty:
        with st.container(border=True, key="caixa_3"):
            st.markdown("**Consumo diário de ração (kg)**")
            d = reg.rename(columns={"dia_ciclo": "Dia", "consumo_racao_kg": "Ração"})
            area = alt.Chart(d).mark_area(
                line={"color": P["terra"], "strokeWidth": 2},
                color=alt.Gradient(gradient="linear", x1=1, x2=1, y1=1, y2=0,
                                   stops=[alt.GradientStop(color="#FFFFFF", offset=0),
                                          alt.GradientStop(color=P["ouro"], offset=1)]),
                opacity=.55,
            ).encode(
                x=alt.X("Dia:Q", title="Dia do ciclo"),
                y=alt.Y("Ração:Q", title="kg por dia"),
                tooltip=["Dia", alt.Tooltip("Ração:Q", format=".1f")],
            ).properties(height=220)
            st.altair_chart(ui.tema_grafico(area), use_container_width=True)


# ======================================================================
# Ciclos
# ======================================================================
def modulo_novo_ciclo():
    ui.cabecalho("Novo ciclo", "Registe o alojamento de um novo lote de pintos.", "Ciclos")

    with st.container(border=True, key="caixa_novo"):
        col1, col2 = st.columns(2)
        with col1:
            codigo = st.text_input("Código do ciclo", value=f"C{datetime.now():%Y%m}")
            data_inicio = st.date_input("Data de alojamento", value=date.today(), format="DD/MM/YYYY")
            n_aves = st.number_input("Nº de aves alojadas", min_value=1, value=1000, step=100)
        with col2:
            sem_ref = "Outra (sem referência)"
            linhagens = listar_linhagens()
            pre = linhagens.index("Cobb 500") if "Cobb 500" in linhagens else 0
            linhagem = st.selectbox("Linhagem", linhagens + [sem_ref], index=pre,
                                    help="A lista mostra as linhagens com valores de referência. "
                                         "Pode acrescentar outras em Linhagens de referência.")
            if linhagem == sem_ref:
                linhagem = st.text_input("Nome da linhagem", placeholder="ex.: Hubbard").strip()
                st.caption("Sem valores de referência, o ciclo não terá a comparação com a linhagem.")
            sexo = st.selectbox("Sexo", ["Misto", "Macho", "Fêmea"])

        ui.secao("Fim do ciclo")
        fim_tipo, fim_idade, fim_peso = _controlo_fim("novo")
        observacoes = st.text_area("Observações (opcional)", height=90)

        if st.button("Criar ciclo", type="primary", icon=":material/add:"):
            if not codigo.strip() or not linhagem:
                st.error("Preencha o código do ciclo e a linhagem.")
            else:
                with conectar() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO ciclos
                            (utilizador_id, codigo, data_inicio, n_aves_alojadas,
                             linhagem, sexo, observacoes, estado,
                             fim_tipo, fim_idade, fim_peso_g)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'activo', %s, %s, %s)
                    """, (st.session_state.user["id"], codigo.strip(), str(data_inicio),
                          n_aves, linhagem, sexo, observacoes, fim_tipo, fim_idade, fim_peso))
                    conn.commit()
                fim_txt = descrever_fim({"fim_tipo": fim_tipo, "fim_idade": fim_idade, "fim_peso_g": fim_peso})
                st.success(f"Ciclo **{codigo}** criado, com fim previsto por {fim_txt}. "
                           "Já pode lançar o registo diário.")


def modulo_ver_ciclos():
    ui.cabecalho("Ciclos", "Todos os lotes registados no sistema, activos e encerrados.", "Ciclos")

    with conectar() as conn:
        df = ler_df("""
            SELECT c.codigo, c.data_inicio, c.data_fim, c.n_aves_alojadas,
                   c.linhagem, c.sexo, c.estado, c.fim_tipo, c.fim_idade, c.fim_peso_g,
                   u.nome_completo AS responsavel
            FROM ciclos c JOIN utilizadores u ON u.id = c.utilizador_id
            ORDER BY c.data_inicio DESC
        """, conn)

    if df.empty:
        ui.vazio("Nenhum ciclo registado.")
        return

    df["fim"] = [descrever_fim(r) for r in df.to_dict("records")]
    df["data_inicio"] = df["data_inicio"].map(ui.data_curta)
    df["data_fim"] = df["data_fim"].map(ui.data_curta)
    df = df.drop(columns=["fim_tipo", "fim_idade", "fim_peso_g"])
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_order=["codigo", "data_inicio", "data_fim", "n_aves_alojadas", "linhagem",
                      "sexo", "fim", "estado", "responsavel"],
        column_config={
            "codigo": "Código", "data_inicio": "Início", "data_fim": "Fim",
            "n_aves_alojadas": st.column_config.NumberColumn("Aves alojadas", format="%d"),
            "linhagem": "Linhagem", "sexo": "Sexo", "fim": "Termina por", "estado": "Estado",
            "responsavel": "Responsável",
        },
    )

    ui.secao("Encerrar ou reactivar um ciclo")
    cid = _selecionar_ciclo("Ciclo", chave="ver_ciclo")
    if cid:
        with conectar() as conn:
            cur = conn.cursor()
            cur.execute("SELECT estado FROM ciclos WHERE id = %s", (cid,))
            estado = cur.fetchone()["estado"]
        if estado == "activo":
            if st.button("Encerrar ciclo", type="primary", icon=":material/lock:"):
                with conectar() as conn:
                    conn.cursor().execute(
                        "UPDATE ciclos SET estado='encerrado', data_fim=%s WHERE id = %s",
                        (str(date.today()), cid))
                    conn.commit()
                st.success("Ciclo encerrado.")
                st.rerun()
        else:
            if st.button("Reactivar ciclo", icon=":material/lock_open:"):
                with conectar() as conn:
                    conn.cursor().execute("UPDATE ciclos SET estado='activo' WHERE id = %s", (cid,))
                    conn.commit()
                st.success("Ciclo reactivado.")
                st.rerun()

        ui.secao("Alterar o fim do ciclo", "por exemplo, se decidirem abater mais cedo ou mais tarde")
        ciclo = next(c for c in _ciclos() if c["id"] == cid)
        st.caption(f"Actualmente termina por {descrever_fim(ciclo)}.")
        fim_tipo, fim_idade, fim_peso = _controlo_fim(f"ver_{cid}", ciclo)
        if st.button("Guardar o novo fim", icon=":material/event:"):
            with conectar() as conn:
                conn.cursor().execute(
                    "UPDATE ciclos SET fim_tipo=%s, fim_idade=%s, fim_peso_g=%s WHERE id = %s",
                    (fim_tipo, fim_idade, fim_peso, cid))
                conn.commit()
            st.success("Fim do ciclo actualizado.")
            st.rerun()


# ======================================================================
# Operação diária
# ======================================================================
def modulo_registo_diario():
    ui.cabecalho("Registo diário",
                 "Lance os dados do dia. O sistema avalia logo as condições e gera alertas quando é preciso agir.",
                 "Operação diária")
    cid = _selecionar_ciclo("Ciclo", apenas_activos=True, chave="reg_ciclo")
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
            data_reg = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
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

        if st.form_submit_button("Registar o dia", type="primary", icon=":material/save:"):
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

                registo = {
                    "data": str(data_reg), "mortalidade": mort,
                    "consumo_racao_kg": racao, "temp_max": temp_max,
                    "temp_min": temp_min, "humidade": humidade,
                    "estado_agua": estado_agua, "estado_electricidade": estado_luz,
                    "n_bebedouros": n_beb, "n_comedouros": n_com, "area_m2": area_m2,
                }
                alertas = avaliar(cid, registo)
                alertas += avaliar_abate(cid, str(data_reg))
                guardar_alertas(cid, str(data_reg), alertas)
                st.session_state["_ultimo_registo"] = (dia, alertas)
            except Exception as e:
                st.error(f"Não foi possível gravar o registo: {e}")

    if "_ultimo_registo" in st.session_state:
        dia, alertas = st.session_state.pop("_ultimo_registo")
        st.success(f"Registo do dia {dia} guardado.")
        if alertas:
            ui.secao(f"{len(alertas)} alerta(s) gerado(s) por este registo")
            codigo = next((c["codigo"] for c in _ciclos() if c["id"] == cid), "")
            for a in alertas:
                st.markdown(ui.alerta_html({**a, "ciclo_codigo": codigo, "data": "hoje"}),
                            unsafe_allow_html=True)
        else:
            st.info("Sem alertas gerados por este registo. Dia dentro da normalidade.")

    ui.secao("Histórico do ciclo")
    with conectar() as conn:
        df = ler_df("""
            SELECT data, dia_ciclo, mortalidade, consumo_racao_kg, temp_max,
                   estado_agua, observacoes
            FROM registo_diario WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC
        """, conn, params=(cid,))
    if df.empty:
        ui.vazio("Sem registos ainda neste ciclo.")
    else:
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "data": "Data", "dia_ciclo": "Dia", "mortalidade": "Mortes",
            "consumo_racao_kg": st.column_config.NumberColumn("Ração (kg)", format="%.1f"),
            "temp_max": st.column_config.NumberColumn("T. máx (°C)", format="%.1f"),
            "estado_agua": "Água", "observacoes": "Observações",
        })


def modulo_pesagens():
    ui.cabecalho("Pesagens",
                 "Registe a pesagem de uma amostra de aves. Com o peso de cada ave, o sistema calcula "
                 "também a uniformidade do lote, que apoia a decisão de abate.",
                 "Operação diária")
    cid = _selecionar_ciclo("Ciclo", chave="pes_ciclo")
    if cid is None:
        return

    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data_inicio FROM ciclos WHERE id = %s", (cid,))
        inicio = datetime.strptime(cur.fetchone()["data_inicio"], "%Y-%m-%d").date()

    modos = ["Peso de cada ave (calcula a uniformidade)", "Só o peso total da amostra"]
    modo = st.radio("Como quer registar?", modos, horizontal=True, key="pes_modo")

    with st.form("pesagem"):
        data_pes = st.date_input("Data da pesagem", value=date.today(), format="DD/MM/YYYY")
        if modo == modos[0]:
            texto = st.text_area(
                "Peso de cada ave, em gramas",
                placeholder="ex.: 1720 1650 1805 1690 1740 ...",
                help="Escreva os pesos separados por espaços ou um por linha. "
                     "Recomenda-se pesar pelo menos 30 aves de vários pontos do aviário.",
                height=110,
            )
            n_amostra, peso_total = None, None
        else:
            c1, c2 = st.columns(2)
            n_amostra = c1.number_input("Nº de aves amostradas", min_value=1, value=20)
            peso_total = c2.number_input("Peso total da amostra (kg)", min_value=0.0, value=0.0, step=0.1)
            texto = None

        if st.form_submit_button("Registar pesagem", type="primary", icon=":material/scale:"):
            dia = (data_pes - inicio).days
            unif = cv = None
            pesos_txt = None
            erro = None
            if texto is not None:
                try:
                    pesos = ler_pesos(texto)
                except ValueError as e:
                    pesos, erro = [], str(e)
                if not erro and len(pesos) < 2:
                    erro = "Escreva o peso de pelo menos 2 aves."
                if not erro:
                    u = calcular_uniformidade(pesos)
                    n_amostra, peso_medio_g = u["n"], u["media"]
                    peso_total = round(sum(pesos) / 1000, 3)
                    unif, cv = u["uniformidade_pct"], u["cv_pct"]
                    pesos_txt = " ".join(f"{p:g}" for p in pesos)
            else:
                if peso_total <= 0:
                    erro = "Indique o peso total da amostra."
                peso_medio_g = (peso_total * 1000) / n_amostra if n_amostra else 0

            if erro:
                st.error(erro)
            else:
                with conectar() as conn:
                    conn.cursor().execute("""
                        INSERT INTO pesagens
                            (ciclo_id, data, dia_ciclo, n_aves_amostra, peso_medio_g, peso_total_kg,
                             uniformidade_pct, cv_pct, pesos_individuais)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (cid, str(data_pes), dia, n_amostra, peso_medio_g, peso_total,
                          unif, cv, pesos_txt))
                    conn.commit()
                abate = avaliar_abate(cid, str(data_pes))
                guardar_alertas(cid, str(data_pes), abate)
                st.session_state["_ultima_pesagem"] = (dia, n_amostra, peso_medio_g, unif, cv, abate)

    if "_ultima_pesagem" in st.session_state:
        dia, n, media, unif, cv, abate = st.session_state.pop("_ultima_pesagem")
        msg = f"Pesagem do dia {dia} registada: {n} aves, peso médio de **{num(media, 0)} g**"
        if unif is not None:
            minimo = uniformidade_minima()
            msg += f", uniformidade de **{num(unif, 0)}%**"
            msg += f" (CV {num(cv, 1)}%)" if cv is not None else ""
            msg += "." if unif >= minimo else f", abaixo do mínimo de {num(minimo)}%."
        else:
            msg += "."
        st.success(msg)
        codigo = next((c["codigo"] for c in _ciclos() if c["id"] == cid), "")
        for a in abate:
            st.markdown(ui.alerta_html({**a, "ciclo_codigo": codigo, "data": "hoje"}),
                        unsafe_allow_html=True)

    ui.secao("Histórico de pesagens")
    with conectar() as conn:
        df = ler_df("""
            SELECT data, dia_ciclo, n_aves_amostra, peso_medio_g, peso_total_kg,
                   uniformidade_pct, cv_pct
            FROM pesagens WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC
        """, conn, params=(cid,))
    if df.empty:
        ui.vazio("Sem pesagens ainda neste ciclo.")
    else:
        df["data"] = df["data"].map(ui.data_curta)
        for c in ["uniformidade_pct", "cv_pct"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "data": "Data", "dia_ciclo": "Dia", "n_aves_amostra": "Aves na amostra",
            "peso_medio_g": st.column_config.NumberColumn("Peso médio (g)", format="%.0f"),
            "peso_total_kg": st.column_config.NumberColumn("Peso total (kg)", format="%.2f"),
            "uniformidade_pct": st.column_config.NumberColumn("Uniformidade (%)", format="%.0f"),
            "cv_pct": st.column_config.NumberColumn("CV (%)", format="%.1f"),
        })
        st.caption("Uniformidade: percentagem de aves com peso dentro de 10% do peso médio. "
                   "CV: coeficiente de variação (quanto menor, mais homogéneo o lote).")


# ======================================================================
# Economia
# ======================================================================
CATEGORIAS = ["Pintos do dia", "Ração", "Medicamentos e vacinas",
              "Cama", "Água e electricidade", "Mão-de-obra",
              "Combustível e transporte", "Manutenção", "Outros"]


def modulo_custos():
    ui.cabecalho("Custos", "Lance cada despesa do ciclo para acompanhar o custo por ave e por quilo.", "Economia")
    cid = _selecionar_ciclo("Ciclo", chave="custo_ciclo")
    if cid is None:
        return

    with st.form("custo"):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_c = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        with col2:
            cat = st.selectbox("Categoria", CATEGORIAS)
        with col3:
            tipo = st.selectbox("Tipo", ["variável", "fixo"])
        valor = st.number_input("Valor (MZN)", min_value=0.0, value=0.0, step=100.0)
        desc = st.text_input("Descrição (opcional)")

        if st.form_submit_button("Registar custo", type="primary", icon=":material/add_card:"):
            with conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO custos (ciclo_id, data, categoria, tipo, descricao, valor_mzn)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (cid, str(data_c), cat, tipo, desc, valor))
                conn.commit()
            st.success(f"Custo de **{mzn(valor, 2)}** registado.")

    c = custos_totais(cid)
    ui.secao("Resumo de custos")
    ui.grelha([
        ui.kpi_html("Total", num(c["total"]), "MZN", "", "carteira", "ouro"),
        ui.kpi_html("Variáveis", num(c["variavel"]), "MZN", "", "racao", "verde"),
        ui.kpi_html("Fixos", num(c["fixo"]), "MZN", "", "camada", "neutro"),
    ])

    if c["por_categoria"]:
        df_cat = pd.DataFrame(
            [(k, v) for k, v in c["por_categoria"].items()],
            columns=["Categoria", "Valor"],
        ).sort_values("Valor", ascending=False)
        ui.secao("Distribuição por categoria")
        with st.container(border=True, key="caixa_4"):
            graf = alt.Chart(df_cat).mark_bar(cornerRadiusTopRight=5, cornerRadiusBottomRight=5,
                                               color=P["ouro"]).encode(
                x=alt.X("Valor:Q", title="MZN", axis=alt.Axis(format="~s")),
                y=alt.Y("Categoria:N", sort="-x", title=None),
                tooltip=["Categoria", alt.Tooltip("Valor:Q", format=".0f", title="MZN")],
            ).properties(height=max(120, 38 * len(df_cat)))
            st.altair_chart(ui.tema_grafico(graf), use_container_width=True)

    with conectar() as conn:
        df = ler_df("""
            SELECT data, categoria, tipo, descricao, valor_mzn
            FROM custos WHERE ciclo_id = %s
            ORDER BY data DESC, id DESC
        """, conn, params=(cid,))
    if not df.empty:
        ui.secao("Histórico")
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "data": "Data", "categoria": "Categoria", "tipo": "Tipo", "descricao": "Descrição",
            "valor_mzn": st.column_config.NumberColumn("Valor (MZN)", format="%.2f"),
        })


def modulo_vendas():
    ui.cabecalho("Vendas", "Registe cada venda de aves para calcular a receita e as margens do ciclo.", "Economia")
    cid = _selecionar_ciclo("Ciclo", chave="venda_ciclo")
    if cid is None:
        return

    with st.form("venda"):
        col1, col2 = st.columns(2)
        with col1:
            data_v = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            n_aves = st.number_input("Nº de aves vendidas", min_value=1, value=100)
            destino = st.selectbox("Destino", DESTINOS)
        with col2:
            peso_total = st.number_input("Peso total (kg)", min_value=0.0, value=0.0, step=0.5)
            preco_kg = st.number_input("Preço por kg (MZN)", min_value=0.0, value=380.0, step=5.0)
            cliente = st.text_input("Cliente ou nota (opcional)")

        if st.form_submit_button("Registar venda", type="primary", icon=":material/point_of_sale:"):
            with conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO vendas (ciclo_id, data, n_aves, peso_total_kg, preco_por_kg,
                                        cliente, destino)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (cid, str(data_v), n_aves, peso_total, preco_kg, cliente, destino))
                conn.commit()
            st.success(f"Venda de **{num(peso_total, 1)} kg** por **{mzn(peso_total * preco_kg, 2)}** registada.")

    r = receitas_totais(cid)
    ui.secao("Resumo de vendas")
    ui.grelha([
        ui.kpi_html("Receita total", num(r["receita"]), "MZN", "", "nota", "verde"),
        ui.kpi_html("Quilos vendidos", num(r["kg_vendidos"], 1), "kg", "", "peso", "ouro"),
        ui.kpi_html("Aves vendidas", num(r["aves_vendidas"]), "", "", "ovo", "neutro"),
    ])

    with conectar() as conn:
        df = ler_df("""
            SELECT data, n_aves, peso_total_kg, preco_por_kg,
                   (peso_total_kg * preco_por_kg) AS total_mzn, destino, cliente
            FROM vendas WHERE ciclo_id = %s
            ORDER BY data DESC
        """, conn, params=(cid,))
    if not df.empty:
        df["destino"] = df["destino"].replace("", "Sem destino indicado")
        por_destino = (df.groupby("destino", as_index=False)
                       .agg(Aves=("n_aves", "sum"), Receita=("total_mzn", "sum"))
                       .rename(columns={"destino": "Destino"}))
        ui.secao("Vendas por destino")
        with st.container(border=True, key="caixa_destino"):
            graf = alt.Chart(por_destino).mark_bar(
                cornerRadiusTopRight=5, cornerRadiusBottomRight=5, color=P["g700"]).encode(
                x=alt.X("Aves:Q", title="Aves vendidas", axis=alt.Axis(format="d")),
                y=alt.Y("Destino:N", sort="-x", title=None),
                tooltip=["Destino", alt.Tooltip("Aves:Q", format="d"),
                         alt.Tooltip("Receita:Q", format=",.0f", title="Receita (MZN)")],
            ).properties(height=max(110, 42 * len(por_destino)))
            st.altair_chart(ui.tema_grafico(graf), use_container_width=True)

        ui.secao("Histórico de vendas")
        df["data"] = df["data"].map(ui.data_curta)
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "data": "Data", "n_aves": "Aves",
            "peso_total_kg": st.column_config.NumberColumn("Peso (kg)", format="%.1f"),
            "preco_por_kg": st.column_config.NumberColumn("Preço/kg (MZN)", format="%.2f"),
            "total_mzn": st.column_config.NumberColumn("Total (MZN)", format="%.2f"),
            "destino": "Destino", "cliente": "Cliente ou nota",
        })


# ======================================================================
# Análise
# ======================================================================
def modulo_indicadores():
    ui.cabecalho("Indicadores", "Síntese completa dos resultados técnicos e económicos de um ciclo.", "Análise")
    cid = _selecionar_ciclo("Ciclo", chave="ind_ciclo")
    if cid is None:
        return

    r = resumo_ciclo(cid)
    ciclo = next(c for c in _ciclos() if c["id"] == cid)
    dia = _dia_ciclo(ciclo, r)
    ui.secao("Técnicos")
    extra = [c for c in [_cartao_fim(ciclo, r, dia), _cartao_uniformidade(r)] if c]
    ui.grelha(extra + [
        ui.kpi_html("Dia do ciclo", str(dia), "dias", "", "calendario", "neutro"),
        ui.kpi_html("Aves vivas", num(r["aves_vivas"]), "", "", "ovo", "verde"),
        ui.kpi_html("Mortalidade", num(r["mortalidade_pct"], 1), "%", "", "pulso", "verm" if r["mortalidade_pct"] > 8 else "verde"),
        ui.kpi_html("Viabilidade", num(r["viabilidade_pct"], 1), "%", "", "escudo", "verde"),
        ui.kpi_html("Peso médio", num(r["peso_actual_g"]), "g", "", "peso", "verde"),
        ui.kpi_html("GMD", num(r["gmd"], 1), "g/dia", "", "subida", "verde"),
        ui.kpi_html("Consumo de ração", num(r["consumo_racao_kg"]), "kg", "", "racao", "ouro"),
        ui.kpi_html("ICA", num(r["ica"], 2), "", "", "ciclo", "ouro"),
        ui.kpi_html("IEP", num(r["iep"]), "", "", "medalha", "ouro"),
    ])

    ui.secao("Económicos")
    pe = r["ponto_equilibrio_kg"]
    ui.grelha([
        ui.kpi_html("Custo total", num(r["custo_total"]), "MZN", "", "carteira", "ouro"),
        ui.kpi_html("Custo variável", num(r["custo_variavel"]), "MZN", "", "racao", "neutro"),
        ui.kpi_html("Custo fixo", num(r["custo_fixo"]), "MZN", "", "camada", "neutro"),
        ui.kpi_html("Custo por kg", num(r["custo_por_kg"], 2), "MZN", "", "peso", "ouro"),
        ui.kpi_html("Custo por ave", num(r["custo_por_ave"], 2), "MZN", "", "ovo", "ouro"),
        ui.kpi_html("Receita", num(r["receita"]), "MZN", "", "nota", "verde"),
    ] + _cartoes_margem(r) + [
        _cartao_roi(r),
        ui.kpi_html("Ponto de equilíbrio", num(pe), "kg", "quilos a vender para cobrir custos", "medalha", "azul"),
    ])

    ui.secao("Comparação com a referência", ciclo["linhagem"])
    semas = semaforos(cid)
    if semas:
        casas = {"Peso médio (g)": 0, "ICA": 2}
        cols = st.columns(len(semas))
        for col, (nome, (actual, ref, (cor, desvio))) in zip(cols, semas.items()):
            col.markdown(ui.semaforo_html(nome, actual, ref, cor, desvio, casas.get(nome, 1)),
                         unsafe_allow_html=True)
    else:
        ui.vazio("Sem pesagens suficientes para comparar com a referência.")


def modulo_sensibilidade():
    ui.cabecalho("Análise de sensibilidade",
                 "Simule variações do preço de venda e do preço da ração para ver o impacto na margem líquida.",
                 "Análise")
    cid = _selecionar_ciclo("Ciclo", chave="sens_ciclo")
    if cid is None:
        return

    base = simular(cid, 0, 0)
    with st.container(border=True, key="caixa_5"):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            var_preco = st.slider("Variação do preço de venda (%)", -30, 30, 0, step=5)
        with col2:
            var_racao = st.slider("Variação do preço da ração (%)", -30, 50, 0, step=5)

    s = simular(cid, var_preco, var_racao)
    dif = s["margem_liquida"] - base["margem_liquida"]
    sinal = "+" if dif >= 0 else ""
    ui.grelha([
        ui.kpi_html("Nova receita", num(s["receita"]), "MZN", "", "nota", "verde"),
        ui.kpi_html("Novo custo total", num(s["custo_total"]), "MZN", "", "carteira", "ouro"),
        ui.kpi_html("Nova margem líquida", num(s["margem_liquida"]), "MZN",
                    f"{num(s['margem_liquida_pct'], 1)}% · {sinal}{mzn(dif)} face ao real",
                    "percent", "verde" if s["margem_liquida"] >= 0 else "verm"),
    ])

    ui.secao("Grelha de cenários", "margem líquida (MZN) para cada combinação")
    df = pd.DataFrame(tabela_cenarios(cid))
    df["Venda"] = df["var_preco_venda"].map(lambda v: f"{int(v):+d}%")
    df["Ração"] = df["var_preco_racao"].map(lambda v: f"{int(v):+d}%")
    df["Margem"] = df["margem_liquida"]
    df["Rótulo"] = df["margem_liquida"].map(lambda v: num(v / 1000) + "k")
    ordem_v = [f"{int(v):+d}%" for v in sorted(df["var_preco_venda"].unique(), reverse=True)]
    ordem_r = [f"{int(v):+d}%" for v in sorted(df["var_preco_racao"].unique())]
    limite = max(abs(df["Margem"].min()), abs(df["Margem"].max())) or 1
    with st.container(border=True, key="caixa_6"):
        base_c = alt.Chart(df).encode(
            x=alt.X("Ração:N", sort=ordem_r, title="Variação do preço da ração",
                    axis=alt.Axis(labelAngle=0, orient="top")),
            y=alt.Y("Venda:N", sort=ordem_v, title="Variação do preço de venda"),
        )
        mapa = base_c.mark_rect(stroke="#FFFFFF", strokeWidth=3).encode(
            color=alt.Color("Margem:Q", legend=None,
                            scale=alt.Scale(domain=[-limite, 0, limite],
                                            range=[P["verm"], "#F7F3E8", P["g700"]])),
            tooltip=["Venda", "Ração", alt.Tooltip("Margem:Q", format=".0f", title="Margem (MZN)")],
        )
        texto = base_c.mark_text(fontSize=11, fontWeight=600).encode(
            text="Rótulo:N",
            color=alt.condition(f"abs(datum.Margem) > {limite * 0.55}",
                                alt.value("#FFFFFF"), alt.value(P["tinta"])),
        )
        st.altair_chart(ui.tema_grafico((mapa + texto).properties(height=360)),
                        use_container_width=True)
        st.caption("Verde: lucro. Vermelho: prejuízo. Valores em milhares de meticais.")


def modulo_relatorios():
    ui.cabecalho("Relatórios", "Gere um relatório completo do ciclo em PDF, pronto a imprimir ou partilhar.", "Análise")
    cid = _selecionar_ciclo("Ciclo", chave="rel_ciclo")
    if cid is None:
        return

    if st.button("Gerar relatório em PDF", type="primary", icon=":material/picture_as_pdf:"):
        try:
            caminho = gerar_relatorio_ciclo(cid)
            with open(caminho, "rb") as f:
                st.download_button(
                    "Transferir PDF", data=f.read(),
                    file_name=os.path.basename(caminho), mime="application/pdf",
                    icon=":material/download:",
                )
            st.success(f"Relatório gerado: {os.path.basename(caminho)}")
        except Exception as e:
            st.error(f"Erro ao gerar relatório: {e}")


# ======================================================================
# Alertas
# ======================================================================
def modulo_alertas():
    ui.cabecalho("Alertas e apoio à decisão",
                 "Situações que pedem intervenção, com a acção recomendada. Registe o que foi feito para fechar cada alerta.",
                 "Principal")

    opcoes = {"Todos os ciclos activos": None}
    for c in _ciclos(apenas_activos=True):
        opcoes[f"Apenas o ciclo {c['codigo']}"] = c["id"]
    cid_filtro = opcoes[st.selectbox("Filtro", list(opcoes.keys()))]

    alertas = listar_alertas_abertos(cid_filtro)
    criticos = [a for a in alertas if a["nivel"] == "critico"]
    avisos = [a for a in alertas if a["nivel"] == "aviso"]
    infos = [a for a in alertas if a["nivel"] == "info"]

    ui.grelha([
        ui.kpi_html("Críticos", str(len(criticos)), "", "intervenção imediata", "aviso", "verm"),
        ui.kpi_html("Avisos", str(len(avisos)), "", "vigiar de perto", "aviso", "amar"),
        ui.kpi_html("Informativos", str(len(infos)), "", "para conhecimento", "info", "azul"),
    ])

    ui.secao("Alertas abertos")
    if not alertas:
        st.markdown(
            f'<div class="gv-vazio">{icone("ok", 28, P["g700"])}<br><b>Sem alertas abertos.</b> '
            "Todos os ciclos estão dentro da normalidade.</div>",
            unsafe_allow_html=True,
        )
    for a in alertas:
        st.markdown(ui.alerta_html(a), unsafe_allow_html=True)
        with st.expander("Registar acção tomada e fechar o alerta"):
            with st.form(f"resolver_{a['id']}"):
                accao = st.text_area(
                    "Acção correctiva tomada",
                    placeholder="Descreva o que foi feito para resolver a situação...",
                    height=80,
                )
                if st.form_submit_button("Marcar como resolvido", type="primary", icon=":material/task_alt:"):
                    if accao.strip():
                        resolver_alerta(a["id"], accao)
                        st.success("Alerta marcado como resolvido.")
                        st.rerun()
                    else:
                        st.warning("Descreva a acção tomada antes de marcar como resolvido.")

    ui.secao("Histórico de alertas resolvidos")
    with conectar() as conn:
        df = ler_df("""
            SELECT c.codigo AS ciclo, a.data, a.nivel, a.titulo,
                   a.accao_tomada, a.resolvido_em
            FROM alertas a JOIN ciclos c ON c.id = a.ciclo_id
            WHERE a.resolvido = TRUE
            ORDER BY a.resolvido_em DESC LIMIT 50
        """, conn)
    if df.empty:
        st.caption("Ainda não há alertas resolvidos.")
    else:
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "ciclo": "Ciclo", "data": "Data", "nivel": "Nível", "titulo": "Alerta",
            "accao_tomada": "Acção tomada",
            "resolvido_em": st.column_config.DatetimeColumn("Resolvido em", format="DD/MM/YYYY HH:mm"),
        })


# ======================================================================
# Administração
# ======================================================================
def modulo_utilizadores():
    ui.cabecalho("Utilizadores", "Contas com acesso ao sistema e respectivos papéis.", "Administração")
    if st.session_state.user["papel"] != "administrador":
        st.warning("Apenas administradores podem gerir utilizadores.")
        return

    with conectar() as conn:
        df = ler_df("""
            SELECT username, nome_completo, papel, criado_em
            FROM utilizadores ORDER BY criado_em DESC
        """, conn)
    st.dataframe(df, width="stretch", hide_index=True, column_config={
        "username": "Utilizador", "nome_completo": "Nome", "papel": "Papel", "criado_em": "Criado em",
    })

    ui.secao("Registar novo utilizador")
    with st.form("novo_user"):
        col1, col2 = st.columns(2)
        with col1:
            u = st.text_input("Utilizador (username)")
            n = st.text_input("Nome completo")
        with col2:
            p = st.text_input("Palavra-passe", type="password")
            papel = st.selectbox("Papel", ["operador", "administrador"])
        if st.form_submit_button("Criar utilizador", type="primary", icon=":material/person_add:"):
            if not u.strip() or not n.strip() or len(p) < 6:
                st.error("Preencha o utilizador e o nome, com uma palavra-passe de pelo menos 6 caracteres.")
            elif registar_utilizador(u.strip(), n.strip(), p, papel):
                st.success("Utilizador criado.")
                st.rerun()
            else:
                st.error("Esse utilizador já existe.")

    ui.secao("Repor a palavra-passe de um utilizador",
             "para quando alguém se esquece da sua")
    with st.form("repor_pw"):
        nomes = df["username"].tolist()
        alvo = st.selectbox("Utilizador", nomes)
        nova = st.text_input("Nova palavra-passe", type="password")
        if st.form_submit_button("Repor palavra-passe", icon=":material/lock_reset:"):
            if len(nova) < 6:
                st.error("A palavra-passe deve ter pelo menos 6 caracteres.")
            else:
                definir_palavra_passe(alvo, nova)
                st.success(f"Palavra-passe de {alvo} reposta. Comunique-a ao utilizador.")


def modulo_conta():
    user = st.session_state.user
    ui.cabecalho("A minha conta", f"{user['nome_completo']} · @{user['username']} · {user['papel']}", "Conta")
    ui.secao("Mudar a palavra-passe")
    with st.form("mudar_pw"):
        actual = st.text_input("Palavra-passe actual", type="password")
        nova = st.text_input("Nova palavra-passe", type="password",
                             help="Pelo menos 6 caracteres. Evite datas de nascimento e o nome.")
        conf = st.text_input("Repita a nova palavra-passe", type="password")
        if st.form_submit_button("Guardar nova palavra-passe", type="primary", icon=":material/key:"):
            if nova != conf:
                st.error("As duas palavras-passe novas não são iguais.")
            else:
                ok, msg = mudar_palavra_passe(user["username"], actual, nova)
                if ok:
                    st.session_state.aviso_pw = False
                    st.success(msg + " Use a nova palavra-passe da próxima vez que entrar.")
                else:
                    st.error(msg)


VIAS = ["Água de bebida", "Spray", "Ocular ou nasal", "Injecção", "Ração", "Outra"]


def modulo_sanitario():
    ui.cabecalho("Vacinas e medicamentos",
                 "Registe cada vacina ou tratamento aplicado ao lote, com a data e a dose. "
                 "O custo dos produtos lança-se em Custos, na categoria Medicamentos e vacinas.",
                 "Operação diária")
    cid = _selecionar_ciclo("Ciclo", chave="san_ciclo")
    if cid is None:
        return
    ciclo = next(c for c in _ciclos() if c["id"] == cid)
    inicio = datetime.strptime(ciclo["data_inicio"], "%Y-%m-%d").date()
    aves_vivas = resumo_ciclo(cid)["aves_vivas"]

    with st.form("sanitario"):
        c1, c2, c3 = st.columns(3)
        with c1:
            data_s = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            tipo = st.selectbox("Tipo", ["Vacina", "Medicamento", "Vitaminas e outros"])
        with c2:
            produto = st.text_input("Produto", placeholder="ex.: Vacina contra Newcastle")
            finalidade = st.text_input("Para quê", placeholder="ex.: prevenção de Newcastle")
        with c3:
            dose = st.text_input("Dose", placeholder="ex.: 1 frasco por 1000 aves")
            via = st.selectbox("Via de aplicação", VIAS)
        c4, c5 = st.columns([1, 2])
        n_aves = c4.number_input("Aves tratadas", min_value=0, value=int(aves_vivas), step=10)
        obs = c5.text_input("Observações (opcional)")
        if st.form_submit_button("Registar aplicação", type="primary", icon=":material/vaccines:"):
            if not produto.strip():
                st.error("Indique o produto aplicado.")
            else:
                with conectar() as conn:
                    conn.cursor().execute("""
                        INSERT INTO sanitario (ciclo_id, data, dia_ciclo, tipo, produto,
                            finalidade, dose, via, n_aves, observacoes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (cid, str(data_s), (data_s - inicio).days, tipo, produto.strip(),
                          finalidade, dose, via, n_aves, obs))
                    conn.commit()
                st.success(f"{tipo} **{produto.strip()}** registada no dia {(data_s - inicio).days} do ciclo.")

    ui.secao("Histórico do ciclo")
    with conectar() as conn:
        df = ler_df("""
            SELECT data, dia_ciclo, tipo, produto, finalidade, dose, via, n_aves, observacoes
            FROM sanitario WHERE ciclo_id = %s ORDER BY data DESC, id DESC
        """, conn, params=(cid,))
    if df.empty:
        ui.vazio("Ainda não há vacinas nem medicamentos registados neste ciclo.")
    else:
        df["data"] = df["data"].map(ui.data_curta)
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "data": "Data", "dia_ciclo": "Dia", "tipo": "Tipo", "produto": "Produto",
            "finalidade": "Para quê", "dose": "Dose", "via": "Via",
            "n_aves": st.column_config.NumberColumn("Aves", format="%d"),
            "observacoes": "Observações",
        })


# ======================================================================
# Navegação
# ======================================================================
MODULOS = {
    "inicio": modulo_inicio,
    "dashboard": modulo_dashboard,
    "alertas": modulo_alertas,
    "registo": modulo_registo_diario,
    "semanal": lambda: pagina_registo_semanal(_selecionar_ciclo),
    "pesagens": modulo_pesagens,
    "sanitario": modulo_sanitario,
    "novo": modulo_novo_ciclo,
    "ciclos": modulo_ver_ciclos,
    "importar": pagina_importar,
    "custos": modulo_custos,
    "vendas": modulo_vendas,
    "indicadores": modulo_indicadores,
    "sensibilidade": modulo_sensibilidade,
    "relatorios": modulo_relatorios,
    "linhagens": pagina_linhagens,
    "utilizadores": modulo_utilizadores,
    "conta": modulo_conta,
}


def _menu_lateral(user: dict):
    try:
        n_alertas = len(listar_alertas_abertos())
    except Exception:
        n_alertas = 0

    grupos = [
        ("Principal", [
            ("inicio", "Início", ":material/home:"),
            ("dashboard", "Painel do ciclo", ":material/space_dashboard:"),
            ("alertas", f"Alertas ({n_alertas})" if n_alertas else "Alertas", ":material/notifications:"),
        ]),
        ("Operação diária", [
            ("registo", "Registo diário", ":material/edit_note:"),
            ("semanal", "Registo semanal", ":material/date_range:"),
            ("pesagens", "Pesagens", ":material/scale:"),
            ("sanitario", "Vacinas e medicamentos", ":material/vaccines:"),
        ]),
        ("Ciclos", [
            ("novo", "Novo ciclo", ":material/add_circle:"),
            ("ciclos", "Ver ciclos", ":material/list_alt:"),
            ("importar", "Importar histórico", ":material/upload_file:"),
        ]),
        ("Economia", [
            ("custos", "Custos", ":material/payments:"),
            ("vendas", "Vendas", ":material/point_of_sale:"),
        ]),
        ("Análise", [
            ("indicadores", "Indicadores", ":material/insights:"),
            ("sensibilidade", "Sensibilidade", ":material/tune:"),
            ("relatorios", "Relatórios PDF", ":material/picture_as_pdf:"),
        ]),
        ("Administração", [
            ("linhagens", "Linhagens de referência", ":material/genetics:"),
            ("utilizadores", "Utilizadores", ":material/group:"),
        ]),
    ]

    with st.sidebar:
        st.markdown(
            f'<div class="gv-marca">{ui.logo_svg(42)}<div><b>GESTAV</b>'
            "<small>Granja FAVET-UEM</small></div></div>",
            unsafe_allow_html=True,
        )
        actual = st.session_state.pagina
        for titulo, itens in grupos:
            st.markdown(f'<div class="gv-grupo">{titulo}</div>', unsafe_allow_html=True)
            for chave, rotulo, ico in itens:
                st.button(
                    rotulo, icon=ico, key=f"nav_{chave}", width="stretch",
                    type="primary" if chave == actual else "tertiary",
                    on_click=_ir_para, args=(chave,),
                )

        st.divider()
        st.markdown(
            f'<div class="gv-utilizador"><span class="av">{ui.iniciais(user["nome_completo"])}</span>'
            f'<div><b>{user["nome_completo"]}</b><small>@{user["username"]} · {user["papel"]}</small></div></div>',
            unsafe_allow_html=True,
        )
        st.button("A minha conta", icon=":material/key:", width="stretch",
                  type="primary" if st.session_state.pagina == "conta" else "tertiary",
                  key="nav_conta", on_click=_ir_para, args=("conta",))
        if st.button("Terminar sessão", icon=":material/logout:", width="stretch", type="tertiary"):
            st.session_state.clear()
            st.rerun()


def main():
    if "user" not in st.session_state:
        tela_login()
        return

    if st.session_state.get("pagina") not in MODULOS:
        st.session_state.pagina = "inicio"

    _menu_lateral(st.session_state.user)
    if st.session_state.get("aviso_pw") and st.session_state.pagina != "conta":
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.warning("Está a usar a palavra-passe de origem (admin123). Como o sistema está na "
                   "internet, mude-a já para proteger os dados da granja.")
        c2.button("Mudar agora", type="primary", icon=":material/key:", width="stretch",
                  on_click=_ir_para, args=("conta",))
    MODULOS[st.session_state.pagina]()


if __name__ == "__main__":
    main()
