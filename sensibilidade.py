"""
Análise de sensibilidade: simula variações de preço de venda e de preço
de ração para avaliar o impacto na margem líquida.
"""

from calculos import custos_totais, receitas_totais, peso_vivo_total
from database import conectar


def _preco_racao_actual(ciclo_id: int) -> tuple[float, float]:
    """Devolve (custo_total_racao, kg_racao). Útil para calcular preço
    actual por kg de ração."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(valor_mzn), 0) AS v
            FROM custos
            WHERE ciclo_id = %s AND categoria = 'Ração'
        """, (ciclo_id,))
        v = cur.fetchone()["v"] or 0.0
        cur.execute("""
            SELECT COALESCE(SUM(consumo_racao_kg), 0) AS kg
            FROM registo_diario WHERE ciclo_id = %s
        """, (ciclo_id,))
        kg = cur.fetchone()["kg"] or 0.0
    return float(v), float(kg)


def simular(ciclo_id: int,
            variacao_preco_venda_pct: float = 0.0,
            variacao_preco_racao_pct: float = 0.0) -> dict:
    """Devolve nova margem líquida e nova margem bruta sob as variações
    pedidas (em pontos percentuais)."""
    c = custos_totais(ciclo_id)
    r = receitas_totais(ciclo_id)

    # Nova receita
    nova_receita = r["receita"] * (1 + variacao_preco_venda_pct / 100)

    # Novo custo de ração (parte dos custos variáveis)
    racao_valor, _ = _preco_racao_actual(ciclo_id)
    novo_racao = racao_valor * (1 + variacao_preco_racao_pct / 100)
    delta_racao = novo_racao - racao_valor

    novo_variavel = c["variavel"] + delta_racao
    novo_fixo = c["fixo"]
    novo_total = novo_variavel + novo_fixo

    nova_bruta = nova_receita - novo_variavel
    nova_liquida = nova_receita - novo_total

    return {
        "receita": round(nova_receita, 2),
        "custo_total": round(novo_total, 2),
        "margem_bruta": round(nova_bruta, 2),
        "margem_liquida": round(nova_liquida, 2),
        "margem_liquida_pct": round(nova_liquida / nova_receita * 100, 1) if nova_receita else 0.0,
    }


def tabela_cenarios(ciclo_id: int,
                    passos_preco: list[float] = None,
                    passos_racao: list[float] = None) -> list[dict]:
    """Devolve lista com cenários (grelha preço_venda × preço_ração)."""
    passos_preco = passos_preco or [-10, -5, 0, 5, 10]
    passos_racao = passos_racao or [-10, 0, 10, 20]

    cenarios = []
    for dp in passos_preco:
        for dr in passos_racao:
            s = simular(ciclo_id, dp, dr)
            cenarios.append({
                "var_preco_venda": dp,
                "var_preco_racao": dr,
                "margem_liquida": s["margem_liquida"],
                "margem_liquida_pct": s["margem_liquida_pct"],
            })
    return cenarios
