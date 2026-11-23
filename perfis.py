"""
Perfis de utilizador, ajustados à forma como a granja trabalha.

  Tratador       faz os registos do dia a dia (registo, pesagens, saúde do
                 lote, uso do stock); não vê a parte económica.
  Técnico        tudo o que é técnico: ciclos, alertas, indicadores técnicos,
                 compras de insumos e linhagens (consulta).
  Chefe          tudo o que o técnico faz e ainda a parte económica (custos,
                 vendas, margens, sensibilidade, relatórios) e as linhagens.
  Administrador  tudo, incluindo a gestão de utilizadores.
"""

import streamlit as st

TODOS = {"tratador", "tecnico", "chefe", "administrador"}
TECNICOS = {"tecnico", "chefe", "administrador"}
GESTAO = {"chefe", "administrador"}

ACESSO = {
    "inicio": TODOS, "dashboard": TODOS, "alertas": TODOS,
    "registo": TODOS, "semanal": TODOS, "pesagens": TODOS, "sanitario": TODOS, "stock": TODOS,
    "novo": TECNICOS, "ciclos": TECNICOS, "importar": GESTAO,
    "custos": GESTAO, "vendas": GESTAO,
    "indicadores": TECNICOS, "sensibilidade": GESTAO, "relatorios": GESTAO,
    "linhagens": TECNICOS, "utilizadores": {"administrador"},
    "conta": TODOS,
}

DESCRICAO = {
    "tratador": "Registos do dia a dia, pesagens, saúde do lote e uso do stock. Não vê custos nem vendas.",
    "tecnico": "Tudo o que é técnico: ciclos, alertas, indicadores técnicos e compras de insumos.",
    "chefe": "Tudo o que o técnico faz, mais custos, vendas, margens, sensibilidade e relatórios.",
    "administrador": "Acesso total, incluindo criar utilizadores e repor palavras-passe.",
}


def papel() -> str:
    p = st.session_state.get("user", {}).get("papel", "tratador")
    return "tecnico" if p == "operador" else p


def pode(pagina: str) -> bool:
    return papel() in ACESSO.get(pagina, {"administrador"})


def ve_economia() -> bool:
    return papel() in GESTAO


def compra_insumos() -> bool:
    return papel() in TECNICOS


def edita_linhagens() -> bool:
    return papel() in GESTAO
