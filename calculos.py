"""
Camada de lógica: cálculo dos indicadores técnicos e económicos.
"""

from database import conectar, obter_referencia


# ----------------------------------------------------------------------
# Indicadores técnicos (zootécnicos)
# ----------------------------------------------------------------------

def mortalidade_acumulada(ciclo_id: int) -> dict:
    """Devolve mortalidade total e percentagem acumulada."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
        if row is None:
            return {"total": 0, "pct": 0.0, "aves_vivas": 0}
        n_alojadas = row["n_aves_alojadas"]

        cur.execute("""
            SELECT COALESCE(SUM(mortalidade), 0) AS total
            FROM registo_diario WHERE ciclo_id = %s
        """, (ciclo_id,))
        total = cur.fetchone()["total"]

    pct = (total / n_alojadas * 100) if n_alojadas else 0.0
    return {
        "total": int(total),
        "pct": round(pct, 2),
        "aves_vivas": int(n_alojadas - total),
    }


def consumo_total_racao(ciclo_id: int) -> float:
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(consumo_racao_kg), 0) AS total
            FROM registo_diario WHERE ciclo_id = %s
        """, (ciclo_id,))
        return float(cur.fetchone()["total"])


def peso_vivo_total(ciclo_id: int) -> float:
    """Devolve o peso vivo total actual (kg), usando a pesagem mais recente
    e as aves vivas."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT peso_medio_g FROM pesagens
            WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC, id DESC LIMIT 1
        """, (ciclo_id,))
        row = cur.fetchone()

    if row is None:
        return 0.0

    aves_vivas = mortalidade_acumulada(ciclo_id)["aves_vivas"]
    peso_medio_kg = row["peso_medio_g"] / 1000.0
    return round(aves_vivas * peso_medio_kg, 2)


def conversao_alimentar(ciclo_id: int) -> float:
    """ICA = consumo total de ração / peso vivo total actual."""
    peso = peso_vivo_total(ciclo_id)
    if peso == 0:
        return 0.0
    consumo = consumo_total_racao(ciclo_id)
    return round(consumo / peso, 3)


def ganho_medio_diario(ciclo_id: int) -> dict:
    """GMD em g/dia desde o alojamento, usando a última pesagem."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT peso_medio_g, dia_ciclo FROM pesagens
            WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC, id DESC LIMIT 1
        """, (ciclo_id,))
        row = cur.fetchone()

    if row is None or row["dia_ciclo"] == 0:
        return {"gmd": 0.0, "peso_actual_g": 0, "dia": 0}

    # Peso inicial padrão: 42g (pinto de 1 dia)
    peso_inicial = 42.0
    gmd = (row["peso_medio_g"] - peso_inicial) / row["dia_ciclo"]
    return {
        "gmd": round(gmd, 2),
        "peso_actual_g": round(row["peso_medio_g"], 1),
        "dia": int(row["dia_ciclo"]),
    }


def viabilidade(ciclo_id: int) -> float:
    """Viabilidade = 100% - mortalidade acumulada%."""
    m = mortalidade_acumulada(ciclo_id)
    return round(100 - m["pct"], 2)


def iep(ciclo_id: int) -> float:
    """Índice de Eficiência Produtiva (European Production Index).
    IEP = (viabilidade × peso_vivo_médio_kg) / (idade_dias × ICA) × 100
    """
    viab = viabilidade(ciclo_id)
    gmd_info = ganho_medio_diario(ciclo_id)
    ica = conversao_alimentar(ciclo_id)

    if gmd_info["dia"] == 0 or ica == 0:
        return 0.0

    peso_kg = gmd_info["peso_actual_g"] / 1000.0
    idade = gmd_info["dia"]
    valor = (viab / 100 * peso_kg) / (idade * ica) * 100
    return round(valor * 100, 1)  # escala habitual


# ----------------------------------------------------------------------
# Indicadores económicos
# ----------------------------------------------------------------------

def custos_totais(ciclo_id: int) -> dict:
    """Custos totais por tipo (variável/fixo) e por categoria."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT tipo, categoria, COALESCE(SUM(valor_mzn), 0) AS total
            FROM custos
            WHERE ciclo_id = %s
            GROUP BY tipo, categoria
        """, (ciclo_id,))
        rows = cur.fetchall()

    por_categoria = {}
    por_tipo = {"variável": 0.0, "fixo": 0.0}
    total = 0.0
    for r in rows:
        por_categoria[r["categoria"]] = por_categoria.get(r["categoria"], 0) + r["total"]
        por_tipo[r["tipo"]] = por_tipo.get(r["tipo"], 0) + r["total"]
        total += r["total"]

    return {
        "total": round(total, 2),
        "variavel": round(por_tipo.get("variável", 0), 2),
        "fixo": round(por_tipo.get("fixo", 0), 2),
        "por_categoria": {k: round(v, 2) for k, v in por_categoria.items()},
    }


def receitas_totais(ciclo_id: int) -> dict:
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(peso_total_kg * preco_por_kg), 0) AS receita,
                COALESCE(SUM(peso_total_kg), 0) AS kg,
                COALESCE(SUM(n_aves), 0) AS aves
            FROM vendas WHERE ciclo_id = %s
        """, (ciclo_id,))
        row = cur.fetchone()
    return {
        "receita": round(row["receita"], 2),
        "kg_vendidos": round(row["kg"], 2),
        "aves_vendidas": int(row["aves"]),
    }


def custo_por_kg(ciclo_id: int) -> float:
    """Custo por kg produzido. Usa kg vendidos se houver vendas, caso
    contrário o peso vivo total actual."""
    c = custos_totais(ciclo_id)["total"]
    r = receitas_totais(ciclo_id)
    kg = r["kg_vendidos"] if r["kg_vendidos"] > 0 else peso_vivo_total(ciclo_id)
    if kg == 0:
        return 0.0
    return round(c / kg, 2)


def custo_por_ave(ciclo_id: int) -> float:
    c = custos_totais(ciclo_id)["total"]
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
    if row is None or row["n_aves_alojadas"] == 0:
        return 0.0
    return round(c / row["n_aves_alojadas"], 2)


def margens(ciclo_id: int) -> dict:
    r = receitas_totais(ciclo_id)["receita"]
    c = custos_totais(ciclo_id)
    bruta = r - c["variavel"]
    liquida = r - c["total"]
    pct_bruta = (bruta / r * 100) if r else 0.0
    pct_liquida = (liquida / r * 100) if r else 0.0
    return {
        "margem_bruta": round(bruta, 2),
        "margem_liquida": round(liquida, 2),
        "margem_bruta_pct": round(pct_bruta, 1),
        "margem_liquida_pct": round(pct_liquida, 1),
    }


def ponto_equilibrio(ciclo_id: int, preco_kg_assumido: float = None) -> dict:
    """Ponto de equilíbrio em kg: custos_fixos / (preco_kg - custo_variavel_por_kg).
    Assume preço médio das vendas registadas se não indicado."""
    c = custos_totais(ciclo_id)
    r = receitas_totais(ciclo_id)

    if preco_kg_assumido is None:
        if r["kg_vendidos"] > 0:
            preco_kg_assumido = r["receita"] / r["kg_vendidos"]
        else:
            return {"kg": 0.0, "aves": 0, "preco_usado": 0.0}

    kg_prod = r["kg_vendidos"] if r["kg_vendidos"] > 0 else peso_vivo_total(ciclo_id)
    custo_variavel_kg = c["variavel"] / kg_prod if kg_prod else 0.0
    margem_contrib = preco_kg_assumido - custo_variavel_kg

    if margem_contrib <= 0:
        return {"kg": float("inf"), "aves": 0, "preco_usado": preco_kg_assumido}

    kg_pe = c["fixo"] / margem_contrib
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
    peso_medio = (kg_prod / row["n_aves_alojadas"]) if row and row["n_aves_alojadas"] else 1.5
    aves_pe = int(kg_pe / peso_medio) if peso_medio else 0

    return {
        "kg": round(kg_pe, 1),
        "aves": aves_pe,
        "preco_usado": round(preco_kg_assumido, 2),
    }


# ----------------------------------------------------------------------
# Comparação com referência Ross 308: semáforos
# ----------------------------------------------------------------------

def semaforos(ciclo_id: int) -> dict:
    """Compara indicadores actuais com referência Ross 308. Devolve
    dicionário com {indicador: ("verde"/"amarelo"/"vermelho", desvio_pct)}."""
    gmd_info = ganho_medio_diario(ciclo_id)
    dia = gmd_info["dia"]
    if dia == 0:
        return {}

    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT linhagem FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
    linhagem = row["linhagem"] if row else "Ross 308"

    ref = obter_referencia(linhagem, dia)
    if ref is None:
        return {}

    resultado = {}

    def avaliar(valor_actual, valor_ref, menor_melhor=False):
        if valor_ref == 0:
            return ("cinzento", 0)
        desvio = (valor_actual - valor_ref) / valor_ref * 100
        if menor_melhor:
            desvio = -desvio
        if desvio >= -3:
            return ("verde", round(desvio, 1))
        if desvio >= -10:
            return ("amarelo", round(desvio, 1))
        return ("vermelho", round(desvio, 1))

    # Peso médio: maior ou igual à referência é bom
    resultado["Peso médio (g)"] = (
        gmd_info["peso_actual_g"],
        ref["peso_medio_g"],
        avaliar(gmd_info["peso_actual_g"], ref["peso_medio_g"]),
    )

    # ICA: menor é melhor
    ica_actual = conversao_alimentar(ciclo_id)
    resultado["ICA"] = (
        ica_actual,
        ref["ica_acumulado"],
        avaliar(ica_actual, ref["ica_acumulado"], menor_melhor=True),
    )

    # Mortalidade: menor é melhor
    mort_pct = mortalidade_acumulada(ciclo_id)["pct"]
    resultado["Mortalidade acumulada (%)"] = (
        mort_pct,
        ref["mortalidade_acumulada_pct"],
        avaliar(mort_pct, ref["mortalidade_acumulada_pct"], menor_melhor=True),
    )

    return resultado


def resumo_ciclo(ciclo_id: int) -> dict:
    """Resumo completo para dashboard, cartões e PDF."""
    mort = mortalidade_acumulada(ciclo_id)
    gmd_info = ganho_medio_diario(ciclo_id)
    c = custos_totais(ciclo_id)
    r = receitas_totais(ciclo_id)
    m = margens(ciclo_id)

    return {
        "aves_vivas": mort["aves_vivas"],
        "mortalidade_total": mort["total"],
        "mortalidade_pct": mort["pct"],
        "viabilidade_pct": viabilidade(ciclo_id),
        "peso_actual_g": gmd_info["peso_actual_g"],
        "gmd": gmd_info["gmd"],
        "dia_ciclo": gmd_info["dia"],
        "consumo_racao_kg": round(consumo_total_racao(ciclo_id), 2),
        "ica": conversao_alimentar(ciclo_id),
        "iep": iep(ciclo_id),
        "peso_vivo_total_kg": peso_vivo_total(ciclo_id),
        "custo_total": c["total"],
        "custo_variavel": c["variavel"],
        "custo_fixo": c["fixo"],
        "custo_por_kg": custo_por_kg(ciclo_id),
        "custo_por_ave": custo_por_ave(ciclo_id),
        "receita": r["receita"],
        "kg_vendidos": r["kg_vendidos"],
        "margem_bruta": m["margem_bruta"],
        "margem_liquida": m["margem_liquida"],
        "margem_bruta_pct": m["margem_bruta_pct"],
        "margem_liquida_pct": m["margem_liquida_pct"],
        "ponto_equilibrio_kg": ponto_equilibrio(ciclo_id)["kg"],
    }
