"""
Nota técnica do ciclo: o que correu bem, as falhas que os dados mostram e o
que melhorar no ciclo seguinte. Cada ponto nasce de uma regra aplicada aos
registos do próprio ciclo (nada é escrito à mão), para que a nota possa ser
gerada no fim de qualquer lote e comparada entre lotes.
"""

import unicodedata

from database import conectar, obter_referencia
from calculos import (resumo_ciclo, semaforos, leitura_unica, mortalidade_acumulada,
                      peso_inicial_pinto)

LIMIAR_PICO_MORT = 0.5      # % das aves no pavilhão num só dia (igual ao alerta)
LIMIAR_MORT_1SEM = 1.0      # % das alojadas na primeira semana
LIMIAR_CONSUMO = 15         # % de desvio face aos dias vizinhos
DENSIDADE_MAX = 12          # aves/m² (igual ao alerta)
AVES_POR_BEBEDOURO = 80     # igual ao alerta

CUSTOS_ESSENCIAIS = {
    "pintos do dia": "pintos",
    "racao": "ração",
    "medicamentos e vacinas": "medicamentos e vacinas",
    "mao de obra": "mão-de-obra",
    "agua e electricidade": "água e electricidade",
    "cama": "cama",
}


def _norm(txt) -> str:
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().replace("-", " ").split())


def _n(v, casas=0) -> str:
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _dias(lista, maximo=6) -> str:
    lista = sorted(lista)
    txt = ", ".join(str(d) for d in lista[:maximo])
    return txt + (" e outros" if len(lista) > maximo else "")


def _dados(ciclo_id):
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ciclos WHERE id = %s", (ciclo_id,))
        ciclo = dict(cur.fetchone())
        cur.execute("""SELECT data, dia_ciclo, mortalidade, consumo_racao_kg, temp_max,
                              estado_agua, estado_electricidade, n_bebedouros, area_m2
                       FROM registo_diario WHERE ciclo_id = %s ORDER BY dia_ciclo""", (ciclo_id,))
        reg = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT dia_ciclo FROM pesagens WHERE ciclo_id = %s", (ciclo_id,))
        pes = [r["dia_ciclo"] for r in cur.fetchall()]
        cur.execute("SELECT tipo FROM sanitario WHERE ciclo_id = %s", (ciclo_id,))
        san = [r["tipo"] for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS n FROM ocorrencias WHERE ciclo_id = %s", (ciclo_id,))
        n_oc = cur.fetchone()["n"]
        cur.execute("""SELECT categoria, SUM(valor_mzn) AS v FROM custos
                       WHERE ciclo_id = %s GROUP BY categoria""", (ciclo_id,))
        custos = {r["categoria"]: float(r["v"] or 0) for r in cur.fetchall()}
        cur.execute("""SELECT nivel, COUNT(*) AS n FROM alertas
                       WHERE ciclo_id = %s AND NOT resolvido GROUP BY nivel""", (ciclo_id,))
        alertas_abertos = {r["nivel"]: r["n"] for r in cur.fetchall()}
        cur.execute("""SELECT data, n_aves FROM vendas WHERE ciclo_id = %s""", (ciclo_id,))
        vendas = [dict(r) for r in cur.fetchall()]
    return ciclo, reg, pes, san, n_oc, custos, alertas_abertos, vendas


def analisar_ciclo(ciclo_id: int) -> dict:
    """Devolve {'pontos_fortes': [...], 'falhas': [{'area','falha','melhorar'}]}."""
    with leitura_unica():
        return _analisar(ciclo_id)


def _analisar(ciclo_id):
    ciclo, reg, pes, san, n_oc, custos, alertas_abertos, vendas = _dados(ciclo_id)
    r = resumo_ciclo(ciclo_id)
    semas = semaforos(ciclo_id)
    alojadas = ciclo["n_aves_alojadas"] or 0
    encerrado = ciclo.get("estado") == "encerrado"
    fortes, falhas = [], []

    def falha(area, txt, melhorar):
        falhas.append({"area": area, "falha": txt, "melhorar": melhorar})

    # ---------------- Desempenho face à referência da linhagem -----------
    dia_ref = r.get("dia_ciclo") or 0
    for nome, (actual, ref, (cor, desvio)) in semas.items():
        if cor == "verde":
            fortes.append(f"{nome} dentro da referência {ciclo['linhagem']} "
                          f"({_n(actual, 2 if 'ICA' in nome else 1)} contra {_n(ref, 2 if 'ICA' in nome else 1)}).")
            continue
        if nome.startswith("Peso"):
            falha("Crescimento",
                  f"O peso médio ficou {_n(abs(desvio), 1)}% abaixo da referência "
                  f"({_n(actual)} g contra {_n(ref)} g).",
                  "Confirmar que as aves têm sempre ração e água à vontade, ajustar a altura dos "
                  "comedouros e bebedouros ao tamanho das aves, cumprir as fases de ração "
                  "(inicial, crescimento e acabamento) e controlar a temperatura nas primeiras semanas.")
        elif nome == "ICA":
            falha("Conversão alimentar",
                  f"A conversão alimentar ficou {_n(abs(desvio), 1)}% pior do que a referência "
                  f"({_n(actual, 2)} contra {_n(ref, 2)} kg de ração por kg de peso).",
                  "Reduzir o desperdício de ração (não encher os comedouros acima de um terço, "
                  "regular a altura), guardar os sacos em local seco, pesar a ração realmente "
                  "consumida todos os dias e não prolongar o ciclo para além da idade de abate.")
        elif nome.startswith("Mortalidade"):
            falha("Mortalidade",
                  f"A mortalidade acumulada ({_n(actual, 1)}%) ficou acima do valor esperado "
                  f"para a idade ({_n(ref, 1)}%).",
                  "Registar a causa provável de cada morte no menu Saúde do lote, retirar as aves "
                  "mortas todos os dias e rever biossegurança, vacinação e ambiente do pavilhão.")
    n_pes = len([p for p in pes if p and p > 0])
    if not semas and n_pes == 0:
        falha("Pesagens",
              "Não há pesagens registadas no sistema, por isso não foi possível comparar o "
              "crescimento do lote com a referência da linhagem.",
              "Pesar uma amostra de pelo menos 50 aves uma vez por semana e lançar a pesagem "
              "no menu Pesagens.")

    # ---------------- Pinto ao alojamento --------------------------------
    peso_pinto, origem = peso_inicial_pinto(ciclo_id)
    ref0 = obter_referencia(ciclo["linhagem"], 0) or {}
    if origem != "valor padrão" and ref0.get("peso_medio_g"):
        if peso_pinto < ref0["peso_medio_g"] * 0.9:
            falha("Qualidade do pinto",
                  f"Os pintos chegaram com {_n(peso_pinto, 1)} g, abaixo dos "
                  f"{_n(ref0['peso_medio_g'])} g esperados para a linhagem.",
                  "Pesar uma amostra à chegada de cada lote, reclamar ao fornecedor quando o peso "
                  "vier baixo e garantir água e ração logo nas primeiras horas.")
    elif origem == "valor padrão":
        falha("Registos", "O peso dos pintos à chegada não foi registado; o ganho médio diário "
              "usou o valor padrão de 42 g.",
              "Pesar uma amostra de pintos no dia do alojamento e lançar o valor em Ciclos.")

    # ---------------- Mortalidade ao longo do ciclo ----------------------
    mort_1sem = sum(x["mortalidade"] or 0 for x in reg if 0 <= (x["dia_ciclo"] or 0) <= 7)
    if alojadas and mort_1sem / alojadas * 100 > LIMIAR_MORT_1SEM:
        falha("Primeira semana",
              f"Morreram {_n(mort_1sem)} aves nos primeiros 7 dias "
              f"({_n(mort_1sem / alojadas * 100, 1)}% das alojadas).",
              "Pré-aquecer o pavilhão antes da chegada dos pintos, ter água e ração prontas à "
              "chegada, vigiar a temperatura sob as campânulas e separar os pintos fracos.")
    vend_por_data = {}
    for v in vendas:
        vend_por_data[str(v["data"])] = vend_por_data.get(str(v["data"]), 0) + (v["n_aves"] or 0)
    picos, mortos, vendidas = [], 0, 0
    for x in reg:
        no_pav = alojadas - mortos - vendidas
        m = x["mortalidade"] or 0
        if no_pav > 0 and m / no_pav * 100 > LIMIAR_PICO_MORT:
            picos.append(x["dia_ciclo"])
        mortos += m
        vendidas += vend_por_data.get(str(x["data"]), 0)
    if picos:
        txt = (f"Houve {len(picos)} dia(s) com mortalidade acima de {_n(LIMIAR_PICO_MORT, 1)}% "
               f"das aves no pavilhão (dias {_dias(picos)}).")
        if n_oc == 0:
            txt += " Nenhuma doença ou anomalia ficou registada para explicar esses picos."
        falha("Picos de mortalidade", txt,
              "No próprio dia de cada pico, examinar as aves mortas, anotar sinais e suspeita em "
              "Saúde do lote e chamar o veterinário se o pico se repetir no dia seguinte.")
    elif reg and r.get("mortalidade_pct", 0) > 0:
        fortes.append("Não houve dias com picos de mortalidade.")

    # ---------------- Ambiente e instalações -----------------------------
    quentes = [x["dia_ciclo"] for x in reg if x["temp_max"] is not None and x["temp_max"] >= 30]
    muito = [x["dia_ciclo"] for x in reg if x["temp_max"] is not None and x["temp_max"] >= 32]
    if quentes:
        falha("Temperatura",
              f"A temperatura máxima chegou a 30 °C ou mais em {len(quentes)} dia(s)"
              + (f", dos quais {len(muito)} com 32 °C ou mais" if muito else "")
              + f" (dias {_dias(quentes)}).",
              "Abrir cortinas e reforçar a ventilação nas horas de calor, molhar o telhado, "
              "acrescentar bebedouros e não incomodar as aves nas horas mais quentes.")
    sem_temp = sum(1 for x in reg if x["temp_max"] is None)
    if reg and sem_temp > len(reg) / 2:
        falha("Registos",
              f"A temperatura não foi registada em {sem_temp} de {len(reg)} dias.",
              "Ler o termómetro de máximas e mínimas todos os dias à mesma hora e lançar no registo diário.")

    agua = [x["dia_ciclo"] for x in reg if x["estado_agua"] in ("corte", "escassa")]
    luz = [x["dia_ciclo"] for x in reg if x["estado_electricidade"] == "falhas"]
    if agua:
        falha("Água", f"Houve falta ou corte de água em {len(agua)} dia(s) (dias {_dias(agua)}).",
              "Manter uma reserva de água para pelo menos 24 horas e verificar bebedouros e "
              "canalização no início de cada dia.")
    if luz:
        falha("Electricidade", f"Houve falhas de electricidade em {len(luz)} dia(s) (dias {_dias(luz)}).",
              "Ter um plano para ventilar e iluminar sem corrente (gerador ou abertura manual "
              "das cortinas), sobretudo nos dias quentes.")

    dens, beb = [], []
    mortos = vendidas = 0
    for x in reg:
        mortos += x["mortalidade"] or 0
        vendidas += vend_por_data.get(str(x["data"]), 0)
        no_pav = max(0, alojadas - mortos - vendidas)
        if x["area_m2"] and no_pav / x["area_m2"] > DENSIDADE_MAX:
            dens.append(x["dia_ciclo"])
        if x["n_bebedouros"] is not None and no_pav > 0 and \
                (x["n_bebedouros"] == 0 or no_pav / x["n_bebedouros"] > AVES_POR_BEBEDOURO):
            beb.append(x["dia_ciclo"])
    if dens:
        falha("Densidade", f"A densidade passou de {DENSIDADE_MAX} aves/m² em {len(dens)} dia(s).",
              "Alojar menos aves por pavilhão ou abrir mais área à medida que as aves crescem.")
    if beb:
        falha("Bebedouros", f"Houve mais de {AVES_POR_BEBEDOURO} aves por bebedouro em {len(beb)} dia(s).",
              "Acrescentar bebedouros antes do lote crescer e reparar logo os avariados.")

    # Consumo de ração fora do normal (comparado com os dias vizinhos)
    por_dia = {x["dia_ciclo"]: float(x["consumo_racao_kg"] or 0) for x in reg}
    anormais = []
    for d, kg in por_dia.items():
        antes = [por_dia[k] for k in (d - 2, d - 1) if por_dia.get(k, 0) > 0]
        depois = [por_dia[k] for k in (d + 1, d + 2) if por_dia.get(k, 0) > 0]
        n = min(len(antes), len(depois))
        if not n:
            continue
        m = sum(antes[-n:] + depois[:n]) / (2 * n)
        if m and abs(kg - m) / m * 100 >= LIMIAR_CONSUMO:
            anormais.append(d)
    if anormais:
        falha("Consumo de ração",
              f"O consumo de ração saiu do normal em {len(anormais)} dia(s) (dias {_dias(anormais)}).",
              "Nesses dias, verificar se faltou ração ou água, se houve calor ou doença, e confirmar "
              "se a quantidade foi bem anotada (sacos abertos e sobras).")

    # ---------------- Saúde do lote --------------------------------------
    if not any(_norm(t).startswith("vacina") for t in san):
        falha("Vacinação", "Não há nenhuma vacina registada neste ciclo.",
              "Seguir o programa de vacinação da granja e lançar cada vacina no menu Saúde do lote, "
              "com data, produto e via.")
    else:
        fortes.append("As vacinas ficaram registadas no sistema.")
    abertos = sum(alertas_abertos.values())
    if abertos:
        falha("Alertas", f"Ficaram {abertos} alerta(s) sem resolução registada.",
              "Ao tratar um alerta, escrever no sistema a acção tomada; isso mostra o que funcionou "
              "e ajuda no lote seguinte.")

    # ---------------- Registos -------------------------------------------
    ultimo = max([x["dia_ciclo"] for x in reg] + [0])
    if reg:
        feitos = {x["dia_ciclo"] for x in reg}
        em_falta = [d for d in range(1, ultimo + 1) if d not in feitos]
        if em_falta:
            falha("Registos", f"Faltam registos diários em {len(em_falta)} dia(s) (dias {_dias(em_falta)}).",
                  "Fazer o registo diário todos os dias, mesmo sem mortes, para que os indicadores "
                  "e os alertas fiquem completos.")
        else:
            fortes.append("O registo diário ficou completo, sem dias em falta.")
    else:
        falha("Registos", "O ciclo não tem registos diários no sistema.",
              "Lançar todos os dias a mortalidade, a ração consumida e a temperatura.")
    semanas = max(1, ultimo // 7)
    if ultimo >= 14 and 0 < n_pes < semanas:
        falha("Pesagens", f"Foram feitas {n_pes} pesagem(ns) em {ultimo} dias; o ideal é uma por semana.",
              "Pesar uma amostra todas as semanas, à mesma hora, para acompanhar o crescimento "
              "e decidir a data de abate.")

    aves_sem_destino = mortalidade_acumulada(ciclo_id)["aves_vivas"]
    if encerrado and aves_sem_destino > 0:
        falha("Contagem das aves",
              f"O ciclo está encerrado mas {_n(aves_sem_destino)} aves não têm destino registado "
              "(nem mortas nem vendidas).",
              "Registar todas as saídas: vendas internas e ofertas como vendas, e refugos ou aves "
              "desaparecidas como mortalidade, com a explicação nas observações.")

    # ---------------- Custos e resultado ---------------------------------
    lancadas = {_norm(c) for c, v in custos.items() if v > 0}
    faltam = [rot for chave, rot in CUSTOS_ESSENCIAIS.items() if chave not in lancadas]
    if faltam:
        falha("Custos",
              "Não foram lançados custos de: " + ", ".join(faltam) + ". Sem eles, o custo por kg "
              "e as margens parecem melhores do que a realidade.",
              "Lançar no menu Custos todas as despesas do lote, incluindo salários, água, energia "
              "e transporte, mesmo que sejam pagas pela faculdade.")
    total = r.get("custo_total") or 0
    racao = sum(v for c, v in custos.items() if _norm(c) == "racao")
    if total and racao:
        fortes.append(f"A ração representou {_n(racao / total * 100)}% dos custos do lote, "
                      "por isso é aí que qualquer poupança pesa mais.")
    if encerrado and not r.get("receita"):
        falha("Vendas", "O ciclo está encerrado mas não tem vendas registadas.",
              "Lançar todas as vendas no menu Vendas, com número de aves, peso e preço.")
    if r.get("receita") and total:
        if r["margem_liquida"] < 0:
            falha("Resultado",
                  f"O lote deu prejuízo de {_n(abs(r['margem_liquida']), 2)} MZN.",
                  "Ver no menu Sensibilidade que preço de venda ou de ração faria o lote dar lucro "
                  "e negociar a compra de ração e pintos antes do próximo lote.")
        else:
            fortes.append(f"O lote deu lucro de {_n(r['margem_liquida'], 2)} MZN "
                          f"({_n(r['margem_liquida_pct'], 1)}% da receita).")
        if r.get("custo_por_kg_vendido") and r.get("kg_vendidos"):
            preco_medio = r["receita"] / r["kg_vendidos"]
            if r["custo_por_kg_vendido"] > preco_medio:
                falha("Preço de venda",
                      f"Cada kg vendido custou {_n(r['custo_por_kg_vendido'], 2)} MZN a produzir, "
                      f"mais do que o preço médio de venda ({_n(preco_medio, 2)} MZN/kg).",
                      "Rever o preço de venda ou baixar custos, sobretudo a ração e a mortalidade.")
    if r.get("kg_carcaca"):
        falha("Peso das vendas",
              "Parte das vendas foi registada em peso de carcaça, por isso o peso vivo dessas "
              "aves foi estimado e a conversão alimentar fica menos exacta.",
              "Pesar as aves vivas antes de saírem para o matadouro e registar esse peso.")

    return {"pontos_fortes": fortes, "falhas": falhas}
