"""
Camada de lógica: cálculo dos indicadores técnicos e económicos.
"""

import statistics
from datetime import date

from database import conectar, obter_referencia
import contextlib
import functools

# Durante um resumo ou relatório, as mesmas contas (peso vivo, custos,
# receitas...) eram repetidas dezenas de vezes. Dentro de 'leitura_unica()'
# cada resultado fica guardado até ao fim dessa leitura.
import threading
_LOCAL = threading.local()   # cada utilizador (fio) tem a sua memória


@contextlib.contextmanager
def leitura_unica():
    dono = getattr(_LOCAL, "memo", None) is None
    if dono:
        _LOCAL.memo = {}
    try:
        yield
    finally:
        if dono:
            _LOCAL.memo = None


def _memo(f):
    @functools.wraps(f)
    def g(*args, **kw):
        memo = getattr(_LOCAL, "memo", None)
        if memo is None:
            return f(*args, **kw)
        chave = (f.__name__, args, tuple(sorted(kw.items())))
        if chave not in memo:
            memo[chave] = f(*args, **kw)
        return memo[chave]
    return g


# ----------------------------------------------------------------------
# Indicadores técnicos (zootécnicos)
# ----------------------------------------------------------------------

@_memo
def mortalidade_acumulada(ciclo_id: int) -> dict:
    """Mortalidade total e percentagem acumulada (sobre as aves alojadas).

    'aves_vivas' são as aves que ainda estão no pavilhão:
    alojadas - mortas - vendidas. As vendidas não contam como mortas,
    mas também já não estão no lote."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
        if row is None:
            return {"total": 0, "pct": 0.0, "aves_vivas": 0, "aves_vendidas": 0}
        n_alojadas = row["n_aves_alojadas"]

        cur.execute("""
            SELECT COALESCE(SUM(mortalidade), 0) AS total
            FROM registo_diario WHERE ciclo_id = %s
        """, (ciclo_id,))
        total = cur.fetchone()["total"]
        cur.execute("SELECT COALESCE(SUM(n_aves), 0) AS v FROM vendas WHERE ciclo_id = %s",
                    (ciclo_id,))
        vendidas = cur.fetchone()["v"]

    pct = (total / n_alojadas * 100) if n_alojadas else 0.0
    return {
        "total": int(total),
        "pct": round(pct, 2),
        "aves_vendidas": int(vendidas),
        "aves_vivas": max(0, int(n_alojadas - total - vendidas)),
    }


@_memo
def consumo_total_racao(ciclo_id: int) -> float:
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(consumo_racao_kg), 0) AS total
            FROM registo_diario WHERE ciclo_id = %s
        """, (ciclo_id,))
        return float(cur.fetchone()["total"])


RENDIMENTO_CARCACA = 0.72   # rendimento típico de carcaça; só se não houver pesagens


@_memo
def _ultima_pesagem(ciclo_id: int, ate: str = None, janela_dias: int = None):
    """Peso médio (g) da pesagem mais recente. Com 'ate', só conta pesagens
    até essa data e, com 'janela_dias', só as feitas nesses últimos dias
    (para não estimar o peso de abate com uma pesagem de semanas antes)."""
    with conectar() as conn:
        cur = conn.cursor()
        if ate:
            cur.execute("""
                SELECT peso_medio_g, data FROM pesagens
                WHERE ciclo_id = %s AND data <= %s
                ORDER BY data DESC, id DESC LIMIT 1
            """, (ciclo_id, ate))
            row = cur.fetchone()
            if row is None:
                return None
            if janela_dias is not None:
                try:
                    dias = (date.fromisoformat(str(ate)[:10])
                            - date.fromisoformat(str(row["data"])[:10])).days
                except ValueError:
                    dias = 0
                if dias > janela_dias:
                    return None
            return float(row["peso_medio_g"])
        cur.execute("""
            SELECT peso_medio_g FROM pesagens
            WHERE ciclo_id = %s
            ORDER BY dia_ciclo DESC, id DESC LIMIT 1
        """, (ciclo_id,))
        row = cur.fetchone()
    return float(row["peso_medio_g"]) if row else None


@_memo
def peso_vivo_pavilhao(ciclo_id: int) -> float:
    """Peso vivo (kg) das aves que ainda estão no pavilhão."""
    peso_g = _ultima_pesagem(ciclo_id)
    if peso_g is None:
        return 0.0
    aves = mortalidade_acumulada(ciclo_id)["aves_vivas"]
    return round(aves * peso_g / 1000.0, 2)


@_memo
def peso_vivo_vendido(ciclo_id: int) -> float:
    """Peso vivo (kg) das aves já vendidas. Nas vendas a peso vivo usa o peso
    da balança. Nas vendas em carcaça estima o peso vivo com a pesagem feita
    até 7 dias antes da venda (n.º de aves × peso médio); sem essa pesagem,
    divide o peso da carcaça pelo rendimento típico."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT data, n_aves, peso_total_kg, COALESCE(tipo_peso, 'vivo') AS tipo_peso
            FROM vendas WHERE ciclo_id = %s
        """, (ciclo_id,))
        vendas = cur.fetchall()
    total = 0.0
    for v in vendas:
        if v["tipo_peso"] == "carcaça":
            peso_g = _ultima_pesagem(ciclo_id, v["data"], janela_dias=7)
            if peso_g:
                total += v["n_aves"] * peso_g / 1000.0
            else:
                total += (v["peso_total_kg"] or 0) / RENDIMENTO_CARCACA
        else:
            total += v["peso_total_kg"] or 0
    return round(total, 2)


@_memo
def peso_vivo_total(ciclo_id: int) -> float:
    """Peso vivo produzido no ciclo (kg): aves no pavilhão + aves vendidas.
    É a base da conversão alimentar e do custo por kg."""
    return round(peso_vivo_pavilhao(ciclo_id) + peso_vivo_vendido(ciclo_id), 2)


@_memo
def conversao_alimentar(ciclo_id: int) -> float:
    """CA = consumo total de ração / peso vivo produzido (Aviagen, 2018)."""
    peso = peso_vivo_total(ciclo_id)
    if peso == 0:
        return 0.0
    consumo = consumo_total_racao(ciclo_id)
    return round(consumo / peso, 3)


@_memo
def peso_inicial_pinto(ciclo_id: int) -> tuple[float, str]:
    """Peso do pinto ao alojamento: o valor registado no ciclo, senão a
    pesagem do dia 0, senão 42 g (valor típico de um pinto de 1 dia)."""
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT peso_pinto_g FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
        if row and row["peso_pinto_g"]:
            return float(row["peso_pinto_g"]), "registado"
        cur.execute("""
            SELECT peso_medio_g FROM pesagens
            WHERE ciclo_id = %s AND dia_ciclo = 0 ORDER BY id DESC LIMIT 1
        """, (ciclo_id,))
        row = cur.fetchone()
    if row and row["peso_medio_g"]:
        return float(row["peso_medio_g"]), "pesagem do dia 0"
    return 42.0, "valor padrão"


@_memo
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

    peso_inicial, _ = peso_inicial_pinto(ciclo_id)
    gmd = (row["peso_medio_g"] - peso_inicial) / row["dia_ciclo"]
    return {
        "gmd": round(gmd, 2),
        "peso_actual_g": round(row["peso_medio_g"], 1),
        "dia": int(row["dia_ciclo"]),
    }


@_memo
def viabilidade(ciclo_id: int) -> float:
    """Viabilidade = 100% - mortalidade acumulada%."""
    m = mortalidade_acumulada(ciclo_id)
    return round(100 - m["pct"], 2)


@_memo
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

@_memo
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


@_memo
def receitas_totais(ciclo_id: int) -> dict:
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(peso_total_kg * preco_por_kg), 0) AS receita,
                COALESCE(SUM(peso_total_kg), 0) AS kg,
                COALESCE(SUM(n_aves), 0) AS aves,
                COALESCE(SUM(CASE WHEN tipo_peso = 'carcaça' THEN peso_total_kg END), 0) AS kg_carcaca
            FROM vendas WHERE ciclo_id = %s
        """, (ciclo_id,))
        row = cur.fetchone()
    return {
        "kg_carcaca": round(row["kg_carcaca"], 2),
        "receita": round(row["receita"], 2),
        "kg_vendidos": round(row["kg"], 2),
        "aves_vendidas": int(row["aves"]),
    }


def custo_por_kg(ciclo_id: int) -> float:
    """Custo por kg de peso vivo produzido (aves no pavilhão + vendidas)."""
    c = custos_totais(ciclo_id)["total"]
    kg = peso_vivo_total(ciclo_id)
    if kg == 0:
        return 0.0
    return round(c / kg, 2)


def custo_por_kg_vendido(ciclo_id: int) -> float:
    """Custo por kg vendido, na unidade em que se vendeu (vivo ou carcaça)."""
    c = custos_totais(ciclo_id)["total"]
    kg = receitas_totais(ciclo_id)["kg_vendidos"]
    return round(c / kg, 2) if kg else 0.0


def custo_por_ave(ciclo_id: int) -> float:
    c = custos_totais(ciclo_id)["total"]
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_aves_alojadas FROM ciclos WHERE id = %s", (ciclo_id,))
        row = cur.fetchone()
    if row is None or row["n_aves_alojadas"] == 0:
        return 0.0
    return round(c / row["n_aves_alojadas"], 2)


@_memo
def margens(ciclo_id: int) -> dict:
    r = receitas_totais(ciclo_id)["receita"]
    c = custos_totais(ciclo_id)
    bruta = r - c["variavel"]
    liquida = r - c["total"]
    pct_bruta = (bruta / r * 100) if r else 0.0
    pct_liquida = (liquida / r * 100) if r else 0.0
    # Retorno sobre o investimento: lucro líquido por cada metical gasto
    roi = (liquida / c["total"] * 100) if (r and c["total"]) else None
    return {
        "margem_bruta": round(bruta, 2),
        "margem_liquida": round(liquida, 2),
        "margem_bruta_pct": round(pct_bruta, 1),
        "margem_liquida_pct": round(pct_liquida, 1),
        "roi_pct": round(roi, 1) if roi is not None else None,
    }


@_memo
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

    # Tudo na mesma unidade: kg vendidos (vivo ou carcaça, como na venda)
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
    aves_base = r["aves_vendidas"] or (row["n_aves_alojadas"] if row else 0)
    peso_medio = (kg_prod / aves_base) if aves_base else 1.5
    aves_pe = int(kg_pe / peso_medio) if peso_medio else 0

    return {
        "kg": round(kg_pe, 1),
        "aves": aves_pe,
        "preco_usado": round(preco_kg_assumido, 2),
    }


# ----------------------------------------------------------------------
# Comparação com a referência da linhagem: semáforos
# ----------------------------------------------------------------------

def semaforos(ciclo_id: int) -> dict:
    with leitura_unica():
        return _semaforos(ciclo_id)


def _semaforos(ciclo_id: int) -> dict:
    """Compara indicadores actuais com a referência da linhagem do ciclo.
    Devolve {indicador: (actual, referência, (cor, desvio_pct))}. Os
    indicadores sem valor de referência para essa linhagem são omitidos."""
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
    if ref.get("peso_medio_g"):
        resultado["Peso médio (g)"] = (
            gmd_info["peso_actual_g"],
            ref["peso_medio_g"],
            avaliar(gmd_info["peso_actual_g"], ref["peso_medio_g"]),
        )

    # ICA: menor é melhor
    if ref.get("ica_acumulado"):
        ica_actual = conversao_alimentar(ciclo_id)
        resultado["ICA"] = (
            ica_actual,
            ref["ica_acumulado"],
            avaliar(ica_actual, ref["ica_acumulado"], menor_melhor=True),
        )

    # Mortalidade: menor é melhor
    if ref.get("mortalidade_acumulada_pct"):
        mort_pct = mortalidade_acumulada(ciclo_id)["pct"]
        resultado["Mortalidade acumulada (%)"] = (
            mort_pct,
            ref["mortalidade_acumulada_pct"],
            avaliar(mort_pct, ref["mortalidade_acumulada_pct"], menor_melhor=True),
        )

    return resultado


def resumo_ciclo(ciclo_id: int) -> dict:
    """Resumo completo para dashboard, cartões e PDF."""
    with leitura_unica():
        return _resumo_ciclo(ciclo_id)


def _resumo_ciclo(ciclo_id: int) -> dict:
    mort = mortalidade_acumulada(ciclo_id)
    gmd_info = ganho_medio_diario(ciclo_id)
    c = custos_totais(ciclo_id)
    r = receitas_totais(ciclo_id)
    m = margens(ciclo_id)

    return {
        "aves_vivas": mort["aves_vivas"],
        "aves_vendidas": mort["aves_vendidas"],
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
        "peso_vivo_pavilhao_kg": peso_vivo_pavilhao(ciclo_id),
        "peso_pinto_g": peso_inicial_pinto(ciclo_id)[0],
        "peso_pinto_origem": peso_inicial_pinto(ciclo_id)[1],
        "custo_total": c["total"],
        "custo_variavel": c["variavel"],
        "custo_fixo": c["fixo"],
        "custo_por_kg": custo_por_kg(ciclo_id),
        "custo_por_ave": custo_por_ave(ciclo_id),
        "receita": r["receita"],
        "kg_vendidos": r["kg_vendidos"],
        "kg_carcaca": r["kg_carcaca"],
        "custo_por_kg_vendido": custo_por_kg_vendido(ciclo_id),
        "margem_bruta": m["margem_bruta"],
        "margem_liquida": m["margem_liquida"],
        "margem_bruta_pct": m["margem_bruta_pct"],
        "margem_liquida_pct": m["margem_liquida_pct"],
        "roi_pct": m["roi_pct"],
        "ponto_equilibrio_kg": ponto_equilibrio(ciclo_id)["kg"],
        **ultima_uniformidade(ciclo_id),
    }


# ----------------------------------------------------------------------
# Uniformidade do lote (pesagem individual)
# ----------------------------------------------------------------------

def ler_pesos(texto: str) -> list[float]:
    """Converte o texto escrito pelo utilizador numa lista de pesos (g).
    Aceita números separados por espaços, quebras de linha, ponto e vírgula
    ou vírgula seguida de espaço; a vírgula entre algarismos é decimal."""
    if not texto:
        return []
    t = texto.replace(";", " ").replace(", ", " ").replace("\n", " ")
    pesos = []
    for parte in t.split():
        parte = parte.strip().strip(",")
        if not parte:
            continue
        try:
            pesos.append(float(parte.replace(",", ".")))
        except ValueError:
            raise ValueError(f"Valor não reconhecido: «{parte}»")
    return [p for p in pesos if p > 0]


def calcular_uniformidade(pesos: list[float], faixa_pct: float = 10.0) -> dict:
    """Uniformidade = % de aves com peso dentro de ±faixa% do peso médio.
    CV = desvio-padrão / média × 100."""
    if not pesos:
        return {"n": 0, "media": 0.0, "uniformidade_pct": None, "cv_pct": None}
    media = sum(pesos) / len(pesos)
    lim_inf, lim_sup = media * (1 - faixa_pct / 100), media * (1 + faixa_pct / 100)
    dentro = sum(1 for p in pesos if lim_inf <= p <= lim_sup)
    cv = (statistics.stdev(pesos) / media * 100) if len(pesos) > 1 and media else None
    return {
        "n": len(pesos),
        "media": round(media, 1),
        "uniformidade_pct": round(dentro / len(pesos) * 100, 1),
        "cv_pct": round(cv, 1) if cv is not None else None,
    }


def ultima_uniformidade(ciclo_id: int) -> dict:
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT uniformidade_pct, cv_pct FROM pesagens
            WHERE ciclo_id = %s AND uniformidade_pct IS NOT NULL
            ORDER BY dia_ciclo DESC, id DESC LIMIT 1
        """, (ciclo_id,))
        row = cur.fetchone()
    return {
        "uniformidade_pct": row["uniformidade_pct"] if row else None,
        "cv_pct": row["cv_pct"] if row else None,
    }


# ----------------------------------------------------------------------
# Fim do ciclo (por idade ou por peso-alvo)
# ----------------------------------------------------------------------

def descrever_fim(ciclo: dict) -> str:
    if ciclo.get("fim_tipo") == "peso" and ciclo.get("fim_peso_g"):
        return f"peso-alvo de {ciclo['fim_peso_g']:.0f} g".replace(".", ",")
    return f"{int(ciclo.get('fim_idade') or 42)} dias"


def progresso_fim(ciclo: dict, dia_actual: int, peso_actual_g: float) -> dict:
    """Quanto falta para o fim do ciclo. Devolve valor, unidade, nota e se já
    foi atingido."""
    if ciclo.get("fim_tipo") == "peso" and ciclo.get("fim_peso_g"):
        alvo = float(ciclo["fim_peso_g"])
        if not peso_actual_g:
            return {"valor": None, "unidade": "g", "atingido": False,
                    "nota": f"peso-alvo {alvo:.0f} g · ainda sem pesagens"}
        falta = alvo - peso_actual_g
        return {"valor": max(0.0, falta), "unidade": "g", "atingido": falta <= 0,
                "nota": f"para o peso-alvo de {alvo:.0f} g"}
    idade = int(ciclo.get("fim_idade") or 42)
    falta = idade - int(dia_actual)
    return {"valor": max(0, falta), "unidade": "dias", "atingido": falta <= 0,
            "nota": f"abate previsto aos {idade} dias"}
