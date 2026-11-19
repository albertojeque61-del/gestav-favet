"""
Módulo de importação de ciclos históricos a partir de ficheiros Excel.

Permite carregar um Excel com várias abas (ciclo, registo_diario, pesagens,
custos, vendas) e inserir todos os dados de uma vez, para analisar ciclos
que já aconteceram e aprender com eles.
"""

import io
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st

from database import conectar
import estilo as ui


# ----------------------------------------------------------------------
# Template Excel (gerado em memória para o utilizador descarregar)
# ----------------------------------------------------------------------

def gerar_template_excel() -> bytes:
    """Devolve um Excel-modelo com as abas preenchidas com exemplos."""
    buffer = io.BytesIO()

    hoje = date.today()
    inicio = hoje - timedelta(days=42)

    aba_ciclo = pd.DataFrame([{
        "codigo": "C-EXEMPLO-01",
        "data_inicio": inicio.strftime("%Y-%m-%d"),
        "n_aves_alojadas": 1000,
        "linhagem": "Ross 308",
        "sexo": "Misto",
        "observacoes": "Ciclo de exemplo importado via Excel",
    }])

    # Exemplo com 3 dias para o utilizador perceber o formato
    aba_registo = pd.DataFrame([
        {
            "data": (inicio + timedelta(days=i)).strftime("%Y-%m-%d"),
            "mortalidade": 2 if i < 2 else 1,
            "consumo_racao_kg": 15 + i * 2,
            "temp_max": 30.0,
            "temp_min": 24.0,
            "humidade": 65.0,
            "estado_agua": "normal",
            "estado_electricidade": "normal",
            "n_bebedouros": 20,
            "n_comedouros": 15,
            "area_m2": 100.0,
            "observacoes": "",
        }
        for i in range(3)
    ])

    aba_pesagens = pd.DataFrame([
        {
            "data": (inicio + timedelta(days=7)).strftime("%Y-%m-%d"),
            "n_aves_amostra": 20,
            "peso_total_kg": 3.92,
        },
        {
            "data": (inicio + timedelta(days=14)).strftime("%Y-%m-%d"),
            "n_aves_amostra": 20,
            "peso_total_kg": 9.80,
        },
    ])

    aba_custos = pd.DataFrame([
        {
            "data": inicio.strftime("%Y-%m-%d"),
            "categoria": "Pintos do dia",
            "tipo": "variável",
            "descricao": "Compra 1000 pintos Ross 308",
            "valor_mzn": 35000.0,
        },
        {
            "data": (inicio + timedelta(days=1)).strftime("%Y-%m-%d"),
            "categoria": "Ração",
            "tipo": "variável",
            "descricao": "Ração inicial 25kg",
            "valor_mzn": 1800.0,
        },
    ])

    aba_vendas = pd.DataFrame([
        {
            "data": (inicio + timedelta(days=42)).strftime("%Y-%m-%d"),
            "n_aves": 950,
            "peso_total_kg": 2375.0,
            "preco_por_kg": 380.0,
            "cliente": "Mercado da Malanga",
        },
    ])

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        aba_ciclo.to_excel(writer, sheet_name="ciclo", index=False)
        aba_registo.to_excel(writer, sheet_name="registo_diario", index=False)
        aba_pesagens.to_excel(writer, sheet_name="pesagens", index=False)
        aba_custos.to_excel(writer, sheet_name="custos", index=False)
        aba_vendas.to_excel(writer, sheet_name="vendas", index=False)

    buffer.seek(0)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Leitura e validação do Excel enviado
# ----------------------------------------------------------------------

COLUNAS_OBRIGATORIAS = {
    "ciclo": ["codigo", "data_inicio", "n_aves_alojadas", "linhagem", "sexo"],
    "registo_diario": ["data", "mortalidade", "consumo_racao_kg"],
    "pesagens": ["data", "n_aves_amostra", "peso_total_kg"],
    "custos": ["data", "categoria", "tipo", "valor_mzn"],
    "vendas": ["data", "n_aves", "peso_total_kg", "preco_por_kg"],
}


def ler_abas(ficheiro) -> dict:
    """Lê todas as abas do Excel e devolve um dicionário aba→DataFrame."""
    xls = pd.ExcelFile(ficheiro)
    abas = {}
    for nome in ["ciclo", "registo_diario", "pesagens", "custos", "vendas"]:
        if nome in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=nome)
            # Remover linhas totalmente vazias
            df = df.dropna(how="all")
            abas[nome] = df
    return abas


def validar_abas(abas: dict) -> list:
    """Verifica se as colunas obrigatórias estão presentes em cada aba."""
    erros = []
    if "ciclo" not in abas or abas["ciclo"].empty:
        erros.append("A aba 'ciclo' é obrigatória e não pode estar vazia.")
        return erros

    for nome, colunas_obrig in COLUNAS_OBRIGATORIAS.items():
        if nome not in abas or abas[nome].empty:
            continue
        faltam = [c for c in colunas_obrig if c not in abas[nome].columns]
        if faltam:
            erros.append(f"Aba '{nome}': faltam as colunas {faltam}.")

    return erros


# ----------------------------------------------------------------------
# Inserção na base de dados
# ----------------------------------------------------------------------

def _data_str(valor) -> str:
    """Converte uma data (datetime, Timestamp ou string) para 'YYYY-MM-DD'."""
    if pd.isna(valor):
        return None
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    return str(valor)[:10]


def importar_para_bd(abas: dict, utilizador_id: int) -> dict:
    """
    Insere os dados do Excel na base de dados.
    Devolve um resumo com o que foi inserido.
    """
    resumo = {
        "ciclo_id": None,
        "codigo": None,
        "data_inicio": None,
        "registo_diario": 0,
        "pesagens": 0,
        "custos": 0,
        "vendas": 0,
    }

    # ----- Ciclo -----
    linha_ciclo = abas["ciclo"].iloc[0]
    codigo = str(linha_ciclo["codigo"]).strip()
    data_inicio_str = _data_str(linha_ciclo["data_inicio"])
    n_aves = int(linha_ciclo["n_aves_alojadas"])
    linhagem = str(linha_ciclo["linhagem"]).strip()
    sexo = str(linha_ciclo["sexo"]).strip()
    observacoes = str(linha_ciclo.get("observacoes", "") or "")

    with conectar() as conn:
        with conn.cursor() as cur:
            # Verificar se o ciclo já existe
            cur.execute("SELECT id FROM ciclos WHERE codigo = %s", (codigo,))
            existente = cur.fetchone()
            if existente:
                raise ValueError(
                    f"Já existe um ciclo com o código '{codigo}'. "
                    f"Escolha outro código ou apague o ciclo existente primeiro."
                )

            cur.execute("""
                INSERT INTO ciclos
                    (utilizador_id, codigo, data_inicio, n_aves_alojadas,
                     linhagem, sexo, observacoes, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'encerrado')
                RETURNING id
            """, (utilizador_id, codigo, data_inicio_str, n_aves,
                  linhagem, sexo, observacoes))
            ciclo_id = cur.fetchone()["id"]
        conn.commit()

    resumo["ciclo_id"] = ciclo_id
    resumo["codigo"] = codigo
    resumo["data_inicio"] = data_inicio_str

    inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()

    # ----- Registo diário -----
    if "registo_diario" in abas and not abas["registo_diario"].empty:
        df = abas["registo_diario"]
        with conectar() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    data_str = _data_str(row["data"])
                    if not data_str:
                        continue
                    dia = (datetime.strptime(data_str, "%Y-%m-%d").date() - inicio).days
                    cur.execute("""
                        INSERT INTO registo_diario
                            (ciclo_id, data, dia_ciclo, mortalidade,
                             consumo_racao_kg, temp_max, temp_min, humidade,
                             estado_agua, estado_electricidade,
                             n_bebedouros, n_comedouros, area_m2, observacoes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ciclo_id, data) DO NOTHING
                    """, (
                        ciclo_id, data_str, dia,
                        int(row["mortalidade"]) if pd.notna(row["mortalidade"]) else 0,
                        float(row["consumo_racao_kg"]) if pd.notna(row["consumo_racao_kg"]) else 0.0,
                        float(row["temp_max"]) if "temp_max" in row and pd.notna(row["temp_max"]) else None,
                        float(row["temp_min"]) if "temp_min" in row and pd.notna(row["temp_min"]) else None,
                        float(row["humidade"]) if "humidade" in row and pd.notna(row["humidade"]) else None,
                        str(row.get("estado_agua", "normal") or "normal"),
                        str(row.get("estado_electricidade", "normal") or "normal"),
                        int(row["n_bebedouros"]) if "n_bebedouros" in row and pd.notna(row["n_bebedouros"]) else None,
                        int(row["n_comedouros"]) if "n_comedouros" in row and pd.notna(row["n_comedouros"]) else None,
                        float(row["area_m2"]) if "area_m2" in row and pd.notna(row["area_m2"]) else None,
                        str(row.get("observacoes", "") or ""),
                    ))
                    resumo["registo_diario"] += 1
            conn.commit()

    # ----- Pesagens -----
    if "pesagens" in abas and not abas["pesagens"].empty:
        df = abas["pesagens"]
        with conectar() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    data_str = _data_str(row["data"])
                    if not data_str:
                        continue
                    dia = (datetime.strptime(data_str, "%Y-%m-%d").date() - inicio).days
                    n_amostra = int(row["n_aves_amostra"])
                    peso_total = float(row["peso_total_kg"])
                    peso_medio_g = (peso_total * 1000) / n_amostra if n_amostra else 0
                    cur.execute("""
                        INSERT INTO pesagens
                            (ciclo_id, data, dia_ciclo, n_aves_amostra,
                             peso_medio_g, peso_total_kg)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (ciclo_id, data_str, dia, n_amostra, peso_medio_g, peso_total))
                    resumo["pesagens"] += 1
            conn.commit()

    # ----- Custos -----
    if "custos" in abas and not abas["custos"].empty:
        df = abas["custos"]
        with conectar() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    data_str = _data_str(row["data"])
                    if not data_str:
                        continue
                    cur.execute("""
                        INSERT INTO custos
                            (ciclo_id, data, categoria, tipo, descricao, valor_mzn)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        ciclo_id, data_str,
                        str(row["categoria"]).strip(),
                        str(row["tipo"]).strip(),
                        str(row.get("descricao", "") or ""),
                        float(row["valor_mzn"]),
                    ))
                    resumo["custos"] += 1
            conn.commit()

    # ----- Vendas -----
    if "vendas" in abas and not abas["vendas"].empty:
        df = abas["vendas"]
        with conectar() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    data_str = _data_str(row["data"])
                    if not data_str:
                        continue
                    cur.execute("""
                        INSERT INTO vendas
                            (ciclo_id, data, n_aves, peso_total_kg,
                             preco_por_kg, cliente)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        ciclo_id, data_str,
                        int(row["n_aves"]),
                        float(row["peso_total_kg"]),
                        float(row["preco_por_kg"]),
                        str(row.get("cliente", "") or ""),
                    ))
                    resumo["vendas"] += 1
            conn.commit()

    return resumo


# ----------------------------------------------------------------------
# Página Streamlit
# ----------------------------------------------------------------------

def pagina_importar():
    ui.cabecalho(
        "Importar ciclo histórico",
        "Carregue um ciclo passado a partir de um ficheiro Excel para analisar "
        "resultados, custos e mortalidade, e perceber o que se poderia ter feito de diferente.",
        "Ciclos",
    )

    ui.secao("1 · Descarregar o modelo Excel")

    st.markdown(
        "Comece por descarregar o ficheiro-modelo, preencha com os dados "
        "do ciclo passado e volte a carregá-lo mais abaixo."
    )

    template_bytes = gerar_template_excel()
    st.download_button(
        "Descarregar modelo Excel",
        data=template_bytes,
        file_name="GESTAV_modelo_importacao.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
    )

    with st.expander("Como preencher cada aba"):
        st.markdown("""
**Aba `ciclo` (obrigatória, uma só linha)**
- `codigo`: identificador único do ciclo (ex.: `C202510`)
- `data_inicio`: data de alojamento das aves (formato `AAAA-MM-DD`)
- `n_aves_alojadas`: número de pintos no início do ciclo
- `linhagem`: Ross 308, Cobb 500, Hubbard ou Outra
- `sexo`: Misto, Macho ou Fêmea
- `observacoes`: opcional

**Aba `registo_diario` (opcional, uma linha por dia)**
- `data`, `mortalidade`, `consumo_racao_kg`: obrigatórias
- `temp_max`, `temp_min`, `humidade`, `estado_agua`,
  `estado_electricidade`, `n_bebedouros`, `n_comedouros`, `area_m2`,
  `observacoes`: opcionais

**Aba `pesagens` (opcional, uma linha por pesagem)**
- `data`, `n_aves_amostra`, `peso_total_kg`: todas obrigatórias
- O peso médio em gramas é calculado automaticamente

**Aba `custos` (opcional, uma linha por custo)**
- `data`, `categoria`, `tipo` (variável/fixo), `valor_mzn`: obrigatórias
- `descricao`: opcional

**Aba `vendas` (opcional, uma linha por venda)**
- `data`, `n_aves`, `peso_total_kg`, `preco_por_kg`: obrigatórias
- `cliente`: opcional

> O ciclo será importado como **encerrado**, para ficar disponível para
> análise. Pode reactivá-lo em **Ver ciclos** se precisar de continuar
> a lançar dados.
""")

    ui.secao("2 · Carregar o ficheiro preenchido")

    ficheiro = st.file_uploader(
        "Seleccione o ficheiro Excel (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
    )

    if ficheiro is None:
        st.info("Carregue um ficheiro Excel para avançar.")
        return

    try:
        abas = ler_abas(ficheiro)
    except Exception as e:
        st.error(f"Não foi possível ler o ficheiro: {e}")
        return

    erros = validar_abas(abas)
    if erros:
        st.error("Foram encontrados problemas no ficheiro:")
        for e in erros:
            st.markdown(f"- {e}")
        return

    st.success("Ficheiro válido. Pré-visualização das abas carregadas:")

    for nome in ["ciclo", "registo_diario", "pesagens", "custos", "vendas"]:
        if nome in abas and not abas[nome].empty:
            n = len(abas[nome])
            with st.expander(f"Aba `{nome}`: {n} linha(s)"):
                st.dataframe(abas[nome], width="stretch", hide_index=True)

    ui.secao("3 · Confirmar importação")

    st.warning(
        "Verifique que os dados estão correctos antes de importar. "
        "Depois de importado, o ciclo fica gravado na base de dados."
    )

    if st.button("Importar ciclo", type="primary"):
        try:
            resumo = importar_para_bd(abas, st.session_state.user["id"])
        except ValueError as e:
            st.error(str(e))
            return
        except Exception as e:
            st.error(f"Erro ao importar: {e}")
            return

        st.success(f"Ciclo **{resumo['codigo']}** importado com sucesso.")
        st.markdown(f"""
**Resumo da importação:**
- Ciclo: `{resumo['codigo']}` (início em {resumo['data_inicio']})
- Registos diários inseridos: **{resumo['registo_diario']}**
- Pesagens inseridas: **{resumo['pesagens']}**
- Custos inseridos: **{resumo['custos']}**
- Vendas inseridas: **{resumo['vendas']}**

Pode agora ir ao **Dashboard** ou aos **Indicadores** para analisar
o desempenho deste ciclo, ou à **Análise de sensibilidade** para
simular cenários alternativos.
""")
        st.balloons()
