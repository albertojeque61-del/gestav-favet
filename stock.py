"""
Stock de insumos de cada lote.

Cada compra (ração, cama, vacinas e medicamentos, outros) entra no stock e,
se se quiser, também nos custos do ciclo, sem ter de ser escrita duas vezes.
A ração gasta é descontada automaticamente a partir do registo diário ou
semanal; os outros insumos saem quando se regista o seu uso. Quando um
insumo desce abaixo do limite definido (20% por defeito), o sistema cria
um alerta, que se fecha sozinho quando o stock é reposto.
"""

from datetime import date, datetime

import pandas as pd
import streamlit as st

import estilo as ui
from estilo import num, mzn
from database import conectar, ler_df, obter_config, definir_config
from motor_alertas import guardar_alertas
import perfis

CATEGORIAS = ["Ração", "Cama", "Medicamentos e vacinas", "Outros insumos"]
UNIDADES = ["kg", "sacos", "doses", "frascos", "litros", "unidades"]
CATEGORIA_CUSTO = {"Ração": "Ração", "Cama": "Cama",
                   "Medicamentos e vacinas": "Medicamentos e vacinas", "Outros insumos": "Outros"}
PREFIXOS = ("Stock baixo: ", "Stock esgotado: ")


def limite_stock() -> float:
    try:
        return float(obter_config("stock_min_pct", "20"))
    except (TypeError, ValueError):
        return 20.0


# ----------------------------------------------------------------------
# Cálculo dos saldos
# ----------------------------------------------------------------------
def saldos(cid: int) -> pd.DataFrame:
    """Uma linha por insumo: comprado, usado, saldo e percentagem restante.
    Toda a ração do lote conta como um único stock, em kg."""
    with conectar() as conn:
        mov = ler_df("""
            SELECT tipo, categoria, item, unidade, SUM(quantidade) AS q
            FROM stock_movimentos WHERE ciclo_id = %s
            GROUP BY tipo, categoria, item, unidade
        """, conn, params=(cid,))
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(consumo_racao_kg), 0) AS kg FROM registo_diario WHERE ciclo_id = %s", (cid,))
            racao_registada = float(cur.fetchone()["kg"])

    linhas = {}
    for r in mov.to_dict("records"):
        if r["categoria"] == "Ração":
            chave = ("Ração", "Ração", "kg")
        else:
            chave = (r["categoria"], r["item"], r["unidade"])
        l = linhas.setdefault(chave, {"comprado": 0.0, "usado": 0.0})
        l["comprado" if r["tipo"] == "entrada" else "usado"] += float(r["q"] or 0)

    if ("Ração", "Ração", "kg") in linhas:
        linhas[("Ração", "Ração", "kg")]["usado"] += racao_registada

    out = []
    for (cat, item, un), v in linhas.items():
        saldo = v["comprado"] - v["usado"]
        pct = (saldo / v["comprado"] * 100) if v["comprado"] else 0.0
        out.append({"categoria": cat, "item": item, "unidade": un, "comprado": v["comprado"],
                    "usado": v["usado"], "saldo": saldo, "pct": pct})
    df = pd.DataFrame(out, columns=["categoria", "item", "unidade", "comprado", "usado", "saldo", "pct"])
    ordem = {c: i for i, c in enumerate(CATEGORIAS)}
    return df.sort_values(by=["categoria", "item"], key=lambda s: s.map(ordem) if s.name == "categoria" else s) \
             .reset_index(drop=True)


def dias_de_racao(cid: int, saldo_kg: float) -> float | None:
    """Dias que a ração ainda dá, pela média dos últimos 3 registos."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT consumo_racao_kg FROM registo_diario WHERE ciclo_id = %s
                ORDER BY data DESC LIMIT 3
            """, (cid,))
            vals = [float(r["consumo_racao_kg"] or 0) for r in cur.fetchall()]
    media = sum(vals) / len(vals) if vals else 0
    return (saldo_kg / media) if media > 0 and saldo_kg > 0 else None


def texto_dias(d: float) -> str:
    return "menos de 1 dia" if d < 1 else f"cerca de {num(d, 0)} dia(s)"


def verificar_stock(cid: int, data_ref: str | None = None) -> list[dict]:
    """Cria alertas de stock baixo ou esgotado (sem repetir os que já estão
    abertos) e fecha os que deixaram de fazer sentido porque o stock foi reposto."""
    df = saldos(cid)
    if df.empty:
        return []
    minimo = limite_stock()
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, titulo FROM alertas WHERE ciclo_id = %s AND resolvido = FALSE
                           AND (titulo LIKE 'Stock baixo: %%' OR titulo LIKE 'Stock esgotado: %%')""", (cid,))
            abertos = {r["titulo"]: r["id"] for r in cur.fetchall()}

    novos, fechar = [], []
    for r in df.to_dict("records"):
        if r["comprado"] <= 0:
            continue
        item, un = r["item"], r["unidade"]
        t_baixo, t_esg = PREFIXOS[0] + item, PREFIXOS[1] + item
        if r["saldo"] <= 0:
            if t_esg not in abertos:
                extra = (f" Foram registados {num(-r['saldo'], 1)} {un} a mais do que o comprado: "
                         "falta registar alguma compra." if r["saldo"] < 0 else "")
                novos.append({"nivel": "critico", "titulo": t_esg,
                              "mensagem": f"Já não há {item.lower()} em stock neste lote.{extra}",
                              "recomendacao": "Comprar com urgência e registar a compra no Stock."})
            if t_baixo in abertos:
                fechar.append(abertos[t_baixo])
        elif r["pct"] < minimo:
            if t_baixo not in abertos:
                msg = f"Restam {num(r['saldo'], 1)} {un} de {item.lower()} ({num(r['pct'], 0)}% do comprado)."
                if r["categoria"] == "Ração":
                    d = dias_de_racao(cid, r["saldo"])
                    if d is not None:
                        msg += f" Ao ritmo actual, dá para {texto_dias(d)}."
                novos.append({"nivel": "aviso", "titulo": t_baixo, "mensagem": msg,
                              "recomendacao": "Programar a compra antes que acabe e registá-la no Stock."})
            if t_esg in abertos:
                fechar.append(abertos[t_esg])
        else:
            for t in (t_baixo, t_esg):
                if t in abertos:
                    fechar.append(abertos[t])

    if fechar:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE alertas SET resolvido = TRUE, resolvido_em = NOW(),
                               accao_tomada = 'Stock reposto (fecho automático)' WHERE id = ANY(%s)""", (fechar,))
            conn.commit()
    guardar_alertas(cid, data_ref or str(date.today()), novos)
    return novos


# ----------------------------------------------------------------------
# Escrita
# ----------------------------------------------------------------------
def registar_compra(cid, data_c, categoria, item, quantidade, unidade, preco, lancar_custo, obs=None) -> int | None:
    custo_id = None
    with conectar() as conn:
        with conn.cursor() as cur:
            if lancar_custo and preco and preco > 0:
                cur.execute("""
                    INSERT INTO custos (ciclo_id, data, categoria, tipo, descricao, valor_mzn)
                    VALUES (%s, %s, %s, 'variável', %s, %s) RETURNING id
                """, (cid, str(data_c), CATEGORIA_CUSTO[categoria],
                      f"Compra: {item} ({num(quantidade, 1)} {unidade})", preco))
                custo_id = cur.fetchone()["id"]
            cur.execute("""
                INSERT INTO stock_movimentos (ciclo_id, data, tipo, categoria, item, quantidade,
                                              unidade, preco_total, custo_id, origem, observacoes)
                VALUES (%s, %s, 'entrada', %s, %s, %s, %s, %s, %s, 'compra', %s)
            """, (cid, str(data_c), categoria, item, quantidade, unidade, preco or None, custo_id, obs))
        conn.commit()
    return custo_id


def registar_uso(cid, data_u, categoria, item, quantidade, unidade, origem="uso", obs=None):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO stock_movimentos (ciclo_id, data, tipo, categoria, item, quantidade,
                                              unidade, origem, observacoes)
                VALUES (%s, %s, 'saida', %s, %s, %s, %s, %s, %s)
            """, (cid, str(data_u), categoria, item, quantidade, unidade, origem, obs))
        conn.commit()


# ----------------------------------------------------------------------
# Página
# ----------------------------------------------------------------------
def pagina_stock(selecionar):
    ui.cabecalho(
        "Stock de insumos",
        "O que foi comprado para o lote e o que ainda resta. A ração gasta desconta-se sozinha a partir "
        "do registo diário; os outros insumos descontam-se ao registar o uso.",
        "Operação diária",
    )
    cid = selecionar("Ciclo", chave="stock_ciclo")
    if cid is None:
        return
    df = saldos(cid)
    minimo = limite_stock()

    if df.empty:
        ui.vazio("Ainda não há compras registadas para este lote.")
    else:
        cartoes = []
        for r in df.to_dict("records"):
            tom = "verm" if r["saldo"] <= 0 else ("amar" if r["pct"] < minimo else "verde")
            nota = f"{num(r['pct'], 0)}% do comprado"
            if r["categoria"] == "Ração":
                d = dias_de_racao(cid, r["saldo"])
                if d is not None:
                    nota += f" · {texto_dias(d)}"
            cartoes.append(ui.kpi_html(r["item"], num(r["saldo"], 1), r["unidade"], nota,
                                       "racao" if r["categoria"] == "Ração" else "camada", tom))
        ui.grelha(cartoes, minimo=200)

        vis = df.copy()
        vis["pct"] = vis["pct"].clip(lower=0, upper=100)
        for c in ["comprado", "usado", "saldo"]:
            vis[c] = vis[c].map(lambda v: num(v, 1))
        st.dataframe(vis, hide_index=True, width="stretch", column_config={
            "categoria": "Categoria", "item": "Insumo", "unidade": "Unidade",
            "comprado": "Comprado", "usado": "Usado", "saldo": "Resta",
            "pct": st.column_config.ProgressColumn("Resta (%)", min_value=0, max_value=100, format="%.0f%%"),
        })
        st.caption(f"Abaixo de {num(minimo)}% o sistema cria um alerta de stock baixo.")

    abas = ["Registar uso", "Movimentos"]
    if perfis.compra_insumos():
        abas.insert(0, "Registar compra")
    tabs = dict(zip(abas, st.tabs(abas)))

    if "Registar compra" in tabs:
        with tabs["Registar compra"]:
            with st.form("compra_stock"):
                c1, c2, c3 = st.columns(3)
                data_c = c1.date_input("Data", value=date.today(), format="DD/MM/YYYY")
                cat = c2.selectbox("Categoria", CATEGORIAS)
                item = c3.text_input("Insumo", placeholder="ex.: Serradura, Vacina Newcastle",
                                     help="Na ração basta deixar em branco: toda a ração do lote conta como um só stock.")
                c4, c5, c6 = st.columns(3)
                qtd = c4.number_input("Quantidade", min_value=0.0, step=1.0)
                un = c5.selectbox("Unidade", UNIDADES, help="A ração regista-se sempre em kg.")
                preco = c6.number_input("Preço total (MZN)", min_value=0.0, step=50.0)
                lancar = st.checkbox("Lançar também nos Custos do ciclo", value=True,
                                     help="Evita escrever a mesma despesa duas vezes.")
                obs = st.text_input("Observações (opcional)")
                if st.form_submit_button("Registar compra", type="primary", icon=":material/add_shopping_cart:"):
                    nome = "Ração" if cat == "Ração" else item.strip()
                    unidade = "kg" if cat == "Ração" else un
                    if not nome:
                        st.error("Indique o insumo comprado.")
                    elif qtd <= 0:
                        st.error("Indique a quantidade comprada.")
                    else:
                        registar_compra(cid, data_c, cat, nome, qtd, unidade, preco, lancar,
                                        obs or (item.strip() if cat == "Ração" and item.strip() else None))
                        verificar_stock(cid, str(data_c))
                        st.success(f"Compra registada: {num(qtd, 1)} {unidade} de {nome.lower()}"
                                   + (f" por {mzn(preco, 2)}, já lançada nos Custos." if lancar and preco else "."))

    with tabs["Registar uso"]:
        itens = [] if df.empty else df.to_dict("records")
        if not itens:
            st.caption("Registe primeiro uma compra.")
        else:
            st.caption("A ração consumida já sai sozinha pelo registo diário. Use este formulário para "
                       "outros insumos ou para ração estragada ou perdida.")
            with st.form("uso_stock"):
                rotulos = {f"{r['item']} ({r['unidade']}, resta {num(r['saldo'], 1)})": r for r in itens}
                escolha = st.selectbox("Insumo", list(rotulos))
                c1, c2 = st.columns(2)
                data_u = c1.date_input("Data", value=date.today(), format="DD/MM/YYYY", key="uso_data")
                qtd_u = c2.number_input("Quantidade usada", min_value=0.0, step=1.0)
                motivo = st.text_input("Motivo (opcional)", placeholder="ex.: troca de cama, ração molhada")
                if st.form_submit_button("Registar uso", type="primary", icon=":material/remove_shopping_cart:"):
                    r = rotulos[escolha]
                    if qtd_u <= 0:
                        st.error("Indique a quantidade usada.")
                    else:
                        registar_uso(cid, data_u, r["categoria"], r["item"], qtd_u, r["unidade"], obs=motivo or None)
                        alertas = verificar_stock(cid, str(data_u))
                        st.success(f"Uso registado: {num(qtd_u, 1)} {r['unidade']} de {r['item'].lower()}.")
                        for a in alertas:
                            st.warning(f"{a['titulo']}. {a['mensagem']}")

    with tabs["Movimentos"]:
        with conectar() as conn:
            mov = ler_df("""
                SELECT data, tipo, categoria, item, quantidade, unidade, preco_total, origem, observacoes
                FROM stock_movimentos WHERE ciclo_id = %s ORDER BY data DESC, id DESC
            """, conn, params=(cid,))
        if mov.empty:
            st.caption("Sem movimentos registados.")
        else:
            mov["data"] = mov["data"].map(ui.data_curta)
            mov["tipo"] = mov["tipo"].map({"entrada": "Compra", "saida": "Uso"})
            mov["quantidade"] = mov["quantidade"].map(lambda v: num(v, 1))
            if perfis.ve_economia():
                mov["preco_total"] = mov["preco_total"].map(
                    lambda v: "–" if v in ("", None) or pd.isna(pd.to_numeric(v, errors="coerce")) else num(float(v), 2))
            else:
                mov = mov.drop(columns=["preco_total"])
            st.dataframe(mov, hide_index=True, width="stretch", column_config={
                "data": "Data", "tipo": "Movimento", "categoria": "Categoria", "item": "Insumo",
                "quantidade": "Quantidade", "unidade": "Unidade", "preco_total": "Preço (MZN)",
                "origem": "Origem", "observacoes": "Observações",
            })
            st.caption("O consumo diário de ração não aparece aqui: é lido directamente do registo diário.")

    if perfis.ve_economia():
        ui.secao("Limite para o aviso de stock baixo")
        with st.form("cfg_stock"):
            novo = st.number_input("Avisar quando restar menos de (%)", min_value=5, max_value=60, step=5,
                                   value=int(round(minimo)))
            if st.form_submit_button("Guardar limite", icon=":material/save:"):
                definir_config("stock_min_pct", str(novo))
                st.success(f"O aviso passa a aparecer abaixo de {novo}%.")
