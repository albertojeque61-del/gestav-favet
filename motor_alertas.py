"""
Motor de alertas e apoio à decisão diária.

Avalia um registo diário contra um conjunto de regras pré-definidas e
devolve a lista de alertas gerados (nível + mensagem + recomendação).
"""

from database import conectar


def _v(valor, casas=1):
    """Número com vírgula decimal (ex.: 30,1)."""
    return f"{valor:.{casas}f}".replace(".", ",")


# ---------------- Regras ----------------

def _mortalidade_anormal(ciclo_id, reg):
    """Mortalidade do dia superior a 0,5% das aves vivas."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT n_aves_alojadas,
                       COALESCE((SELECT SUM(mortalidade) FROM registo_diario
                                 WHERE ciclo_id = %s AND data < %s), 0) AS mortes_antes
                FROM ciclos WHERE id = %s
            """, (ciclo_id, reg["data"], ciclo_id))
            row = cur.fetchone()
    aves_vivas = row["n_aves_alojadas"] - row["mortes_antes"]
    if aves_vivas <= 0:
        return None
    pct_dia = (reg["mortalidade"] / aves_vivas) * 100
    if pct_dia >= 0.5:
        return {
            "nivel": "critico",
            "titulo": "Mortalidade anormal",
            "mensagem": f"Morreram {reg['mortalidade']} aves hoje ({_v(pct_dia, 2)}% das aves vivas).",
            "recomendacao": "Investigar imediatamente a causa: avaliar sinais de doença, verificar temperatura, disponibilidade de água, estado da ração e densidade. Contactar médico veterinário se o padrão persistir no dia seguinte.",
        }
    return None


def _stress_termico(ciclo_id, reg):
    temp = reg.get("temp_max")
    humid = reg.get("humidade")
    if temp is None:
        return None
    if temp >= 32:
        rec = ("Reforçar imediatamente a ventilação, molhar o chão e as "
               "paredes, aumentar o número de bebedouros, verificar se "
               "todas as aves têm acesso à água e redistribuir as aves "
               "por zonas de sombra. Em casos extremos, considerar "
               "retirar parte do lote para zona exterior com sombra.")
        if humid and humid >= 70:
            rec = "Humidade também elevada, com risco de golpe de calor. " + rec
        return {
            "nivel": "critico",
            "titulo": "Stress térmico severo",
            "mensagem": f"Temperatura máxima registada: {_v(temp, 1)} °C" +
                        (f" (humidade {humid:.0f}%)" if humid else "") + ".",
            "recomendacao": rec,
        }
    if temp >= 30:
        return {
            "nivel": "aviso",
            "titulo": "Temperatura elevada",
            "mensagem": f"Temperatura máxima: {_v(temp, 1)} °C, acima do conforto térmico.",
            "recomendacao": "Reforçar ventilação e verificar se o número de bebedouros é suficiente para a densidade actual. Monitorizar comportamento das aves.",
        }
    return None


def _queda_consumo_racao(ciclo_id, reg):
    """Queda do consumo diário acima de 15% face à média móvel dos
    7 dias anteriores."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(consumo_racao_kg) AS media
                FROM (
                    SELECT consumo_racao_kg FROM registo_diario
                    WHERE ciclo_id = %s AND data < %s
                    ORDER BY data DESC LIMIT 7
                ) sub
            """, (ciclo_id, reg["data"]))
            row = cur.fetchone()
    media = row["media"] or 0
    if media < 1:
        return None
    queda_pct = (media - reg["consumo_racao_kg"]) / media * 100
    if queda_pct >= 15:
        return {
            "nivel": "aviso",
            "titulo": "Queda no consumo de ração",
            "mensagem": f"Consumo de hoje ({_v(reg['consumo_racao_kg'], 1)} kg) está {queda_pct:.0f}% abaixo da média dos últimos 7 dias ({_v(media, 1)} kg).",
            "recomendacao": "Verificar disponibilidade e qualidade da água, estado dos comedouros, temperatura ambiente e eventuais sinais de doença. Pode ser prenúncio de problema sanitário.",
        }
    return None


def _falha_agua_ou_luz(ciclo_id, reg):
    alertas = []
    if reg.get("estado_agua") == "corte":
        alertas.append({
            "nivel": "critico",
            "titulo": "Corte de água",
            "mensagem": "Falha total de água registada hoje.",
            "recomendacao": "Repor imediatamente o abastecimento. Enquanto durar, trazer água de outra fonte para encher os bebedouros manualmente. Em período quente, a prioridade é absoluta.",
        })
    elif reg.get("estado_agua") == "escassa":
        alertas.append({
            "nivel": "aviso",
            "titulo": "Água escassa",
            "mensagem": "Abastecimento de água irregular ou insuficiente.",
            "recomendacao": "Verificar reservatórios, canalização e bebedouros. Garantir reserva adicional para 24 horas.",
        })
    if reg.get("estado_electricidade") == "falhas":
        alertas.append({
            "nivel": "aviso",
            "titulo": "Falhas de electricidade",
            "mensagem": "Falhas de electricidade registadas no dia.",
            "recomendacao": "Verificar ventilação alternativa (manual ou gerador) e sistema de iluminação. Em período quente, ventilação é prioritária.",
        })
    return alertas


def _densidade_elevada(ciclo_id, reg):
    """Verifica se a densidade é > 12 aves/m² (limiar comum para corte)."""
    area = reg.get("area_m2")
    if not area:
        return None
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT n_aves_alojadas,
                       COALESCE((SELECT SUM(mortalidade) FROM registo_diario
                                 WHERE ciclo_id = %s), 0) AS mortes
                FROM ciclos WHERE id = %s
            """, (ciclo_id, ciclo_id))
            row = cur.fetchone()
    aves_vivas = row["n_aves_alojadas"] - row["mortes"]
    densidade = aves_vivas / area
    if densidade > 12:
        return {
            "nivel": "aviso",
            "titulo": "Densidade elevada",
            "mensagem": f"Densidade actual: {_v(densidade, 1)} aves/m² (limite recomendado: 12 aves/m²).",
            "recomendacao": "Considerar divisão do lote por mais compartimentos, reforço de ventilação e aumento proporcional do nº de bebedouros e comedouros.",
        }
    return None


def _bebedouros_insuficientes(ciclo_id, reg):
    """Verificar se o nº de bebedouros é adequado ao nº de aves."""
    n_beb = reg.get("n_bebedouros")
    if n_beb is None:
        return None
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT n_aves_alojadas,
                       COALESCE((SELECT SUM(mortalidade) FROM registo_diario
                                 WHERE ciclo_id = %s), 0) AS mortes
                FROM ciclos WHERE id = %s
            """, (ciclo_id, ciclo_id))
            row = cur.fetchone()
    aves_vivas = row["n_aves_alojadas"] - row["mortes"]
    # Rácio comum: 1 bebedouro nipple por 10-15 aves; 1 bebedouro linear por 80 aves
    if n_beb == 0 or aves_vivas / max(n_beb, 1) > 80:
        return {
            "nivel": "critico",
            "titulo": "Bebedouros insuficientes",
            "mensagem": f"{aves_vivas} aves para apenas {n_beb} bebedouros funcionais.",
            "recomendacao": "Aumentar imediatamente o nº de bebedouros ou reparar os avariados. Em período quente, a disponibilidade de água é vital.",
        }
    return None


REGRAS = [
    _mortalidade_anormal,
    _stress_termico,
    _queda_consumo_racao,
    _falha_agua_ou_luz,
    _densidade_elevada,
    _bebedouros_insuficientes,
]


def avaliar(ciclo_id: int, registo: dict) -> list[dict]:
    """Executa todas as regras sobre o registo e devolve lista de alertas."""
    alertas = []
    for regra in REGRAS:
        resultado = regra(ciclo_id, registo)
        if resultado is None:
            continue
        if isinstance(resultado, list):
            alertas.extend(resultado)
        else:
            alertas.append(resultado)
    return alertas


def guardar_alertas(ciclo_id: int, data: str, alertas: list[dict]):
    """Grava os alertas na tabela alertas."""
    if not alertas:
        return
    with conectar() as conn:
        with conn.cursor() as cur:
            for a in alertas:
                cur.execute("""
                    INSERT INTO alertas (ciclo_id, data, nivel, titulo,
                        mensagem, recomendacao, resolvido)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """, (ciclo_id, data, a["nivel"], a["titulo"],
                      a["mensagem"], a["recomendacao"]))
        conn.commit()


def listar_alertas_abertos(ciclo_id: int = None) -> list[dict]:
    with conectar() as conn:
        with conn.cursor() as cur:
            if ciclo_id:
                cur.execute("""
                    SELECT a.*, c.codigo AS ciclo_codigo
                    FROM alertas a JOIN ciclos c ON c.id = a.ciclo_id
                    WHERE a.ciclo_id = %s AND a.resolvido = FALSE
                    ORDER BY
                        CASE a.nivel WHEN 'critico' THEN 1 WHEN 'aviso' THEN 2 ELSE 3 END,
                        a.data DESC
                """, (ciclo_id,))
            else:
                cur.execute("""
                    SELECT a.*, c.codigo AS ciclo_codigo
                    FROM alertas a JOIN ciclos c ON c.id = a.ciclo_id
                    WHERE a.resolvido = FALSE
                    ORDER BY
                        CASE a.nivel WHEN 'critico' THEN 1 WHEN 'aviso' THEN 2 ELSE 3 END,
                        a.data DESC
                """)
            return [dict(r) for r in cur.fetchall()]


def resolver_alerta(alerta_id: int, accao_tomada: str):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE alertas
                SET resolvido = TRUE,
                    accao_tomada = %s,
                    resolvido_em = NOW()
                WHERE id = %s
            """, (accao_tomada, alerta_id))
        conn.commit()
