"""
Camada de persistência: PostgreSQL hospedado no Supabase.
A URL de conexão é lida primeiro de st.secrets (deploy em Streamlit
Cloud) e, se não existir, de uma variável de ambiente SUPABASE_DB_URL
carregada do ficheiro .env (desenvolvimento local).
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def _obter_url_conexao() -> str:
    """Devolve a URL de conexão, preferindo st.secrets (produção)."""
    # Tenta ler de st.secrets (Streamlit Cloud)
    try:
        import streamlit as st
        if "SUPABASE_DB_URL" in st.secrets:
            return st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass
    # Fallback para variável de ambiente (desenvolvimento local)
    return os.getenv("SUPABASE_DB_URL", "")


SUPABASE_DB_URL = _obter_url_conexao()

if not SUPABASE_DB_URL:
    raise RuntimeError(
        "Variável SUPABASE_DB_URL não definida. "
        "Em desenvolvimento local, copie .env.example para .env e preencha "
        "com a connection string do Supabase. Em Streamlit Cloud, defina "
        "SUPABASE_DB_URL nas Secrets da aplicação."
    )


def conectar():
    conn = psycopg2.connect(SUPABASE_DB_URL, cursor_factory=RealDictCursor)
    return conn


def ler_df(sql: str, conn, params=None):
    """Executa uma consulta e devolve um DataFrame.

    Substitui pd.read_sql_query, que com o RealDictCursor devolvia o nome
    das colunas em vez dos valores.
    """
    import pandas as pd
    with conn.cursor() as cur:
        cur.execute(sql, params)
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchall()
    df = pd.DataFrame([[l[c] for c in colunas] for l in linhas], columns=colunas)
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("str"):
            df[c] = df[c].fillna("")
    return df


def inicializar_bd():
    """Cria todas as tabelas se ainda não existirem."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS utilizadores (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                nome_completo TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                papel TEXT NOT NULL DEFAULT 'operador',
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ciclos (
                id SERIAL PRIMARY KEY,
                utilizador_id INTEGER NOT NULL REFERENCES utilizadores(id),
                codigo TEXT NOT NULL,
                data_inicio TEXT NOT NULL,
                data_fim TEXT,
                n_aves_alojadas INTEGER NOT NULL,
                linhagem TEXT NOT NULL,
                sexo TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activo',
                observacoes TEXT
            );

            CREATE TABLE IF NOT EXISTS registo_diario (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                dia_ciclo INTEGER NOT NULL,
                mortalidade INTEGER NOT NULL DEFAULT 0,
                consumo_racao_kg REAL NOT NULL DEFAULT 0,
                temp_max REAL,
                temp_min REAL,
                humidade REAL,
                estado_agua TEXT DEFAULT 'normal',
                estado_electricidade TEXT DEFAULT 'normal',
                n_bebedouros INTEGER,
                n_comedouros INTEGER,
                area_m2 REAL,
                observacoes TEXT,
                UNIQUE (ciclo_id, data)
            );

            CREATE TABLE IF NOT EXISTS alertas (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                nivel TEXT NOT NULL,
                titulo TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                recomendacao TEXT,
                resolvido BOOLEAN NOT NULL DEFAULT FALSE,
                accao_tomada TEXT,
                resolvido_em TIMESTAMP,
                criado_em TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS pesagens (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                dia_ciclo INTEGER NOT NULL,
                n_aves_amostra INTEGER NOT NULL,
                peso_medio_g REAL NOT NULL,
                peso_total_kg REAL
            );

            CREATE TABLE IF NOT EXISTS custos (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                categoria TEXT NOT NULL,
                tipo TEXT NOT NULL,
                descricao TEXT,
                valor_mzn REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                n_aves INTEGER NOT NULL,
                peso_total_kg REAL NOT NULL,
                preco_por_kg REAL NOT NULL,
                cliente TEXT
            );

            CREATE TABLE IF NOT EXISTS parametros_referencia (
                id SERIAL PRIMARY KEY,
                linhagem TEXT NOT NULL,
                dia INTEGER NOT NULL,
                peso_medio_g REAL,
                ica_acumulado REAL,
                mortalidade_acumulada_pct REAL,
                UNIQUE (linhagem, dia)
            );

            -- Registo sanitário: vacinas e medicamentos aplicados ao lote
            CREATE TABLE IF NOT EXISTS sanitario (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                dia_ciclo INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                produto TEXT NOT NULL,
                finalidade TEXT,
                dose TEXT,
                via TEXT,
                n_aves INTEGER,
                observacoes TEXT
            );

            -- Parâmetros gerais do sistema (chave/valor)
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );

            -- Colunas acrescentadas depois do pré-teste (seguras para bases antigas)
            ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_tipo TEXT NOT NULL DEFAULT 'idade';
            ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_idade INTEGER NOT NULL DEFAULT 42;
            ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_peso_g REAL;
            ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS uniformidade_pct REAL;
            ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS cv_pct REAL;
            ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS pesos_individuais TEXT;
            ALTER TABLE vendas ADD COLUMN IF NOT EXISTS destino TEXT;
            ALTER TABLE parametros_referencia ADD COLUMN IF NOT EXISTS fonte TEXT;

            -- Stock de insumos de cada lote (entradas = compras, saídas = usos)
            CREATE TABLE IF NOT EXISTS stock_movimentos (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                tipo TEXT NOT NULL,              -- 'entrada' ou 'saida'
                categoria TEXT NOT NULL,
                item TEXT NOT NULL,
                quantidade REAL NOT NULL,
                unidade TEXT NOT NULL,
                preco_total REAL,
                custo_id INTEGER,
                origem TEXT,                     -- 'compra', 'uso', 'sanitario'
                observacoes TEXT
            );

            -- Doenças e anomalias observadas no lote
            CREATE TABLE IF NOT EXISTS ocorrencias (
                id SERIAL PRIMARY KEY,
                ciclo_id INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                dia_ciclo INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                sinais TEXT NOT NULL,
                suspeita TEXT,
                n_aves INTEGER,
                accao TEXT,
                observacoes TEXT
            );

            ALTER TABLE sanitario ADD COLUMN IF NOT EXISTS custo_mzn REAL;
            ALTER TABLE sanitario ADD COLUMN IF NOT EXISTS custo_id INTEGER;

            -- Perfis: o antigo 'operador' passa a 'tecnico'
            UPDATE utilizadores SET papel = 'tecnico' WHERE papel = 'operador';

            -- v7: tipo de peso das vendas e peso do pinto ao alojamento
            ALTER TABLE vendas ADD COLUMN IF NOT EXISTS tipo_peso TEXT NOT NULL DEFAULT 'vivo';
            ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS peso_pinto_g REAL;
            """)
            _popular_parametros_ross308(cur)
            _popular_parametros_cobb500(cur)
            cur.execute("""
                INSERT INTO configuracoes (chave, valor) VALUES
                    ('uniformidade_min', '80'), ('stock_min_pct', '20')
                ON CONFLICT (chave) DO NOTHING
            """)
        conn.commit()


def _popular_parametros_ross308(cur):
    cur.execute("SELECT COUNT(*) AS n FROM parametros_referencia WHERE linhagem=%s",
                ("Ross 308",))
    if cur.fetchone()["n"] > 0:
        return

    dados = [
        (0, 42, 0.00, 0.0),
        (7, 196, 0.90, 1.0),
        (14, 490, 1.20, 2.0),
        (21, 942, 1.33, 3.0),
        (28, 1521, 1.47, 3.5),
        (35, 2200, 1.60, 4.0),
        (42, 2902, 1.73, 5.0),
    ]
    for dia, peso, ica, mort in dados:
        cur.execute("""
            INSERT INTO parametros_referencia
                (linhagem, dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct)
            VALUES (%s, %s, %s, %s, %s)
        """, ("Ross 308", dia, peso, ica, mort))


FONTE_COBB500 = ("Cobb500 Broiler Performance & Nutrition Supplement (2022), "
                  "objectivos de desempenho, sexos misturados (as hatched)")


def _popular_parametros_cobb500(cur):
    """Referência Cobb 500 (sexos misturados). Peso e ICA acumulado retirados
    do suplemento oficial da Cobb (2022). O suplemento não indica
    mortalidade acumulada, por isso esse campo fica vazio."""
    cur.execute("SELECT COUNT(*) AS n FROM parametros_referencia WHERE linhagem=%s",
                ("Cobb 500",))
    if cur.fetchone()["n"] > 0:
        return
    dados = [
        (0, 42, None),
        (7, 202, 0.891),
        (14, 570, 1.029),
        (21, 1116, 1.182),
        (28, 1783, 1.322),
        (35, 2521, 1.441),
        (42, 3278, 1.555),
    ]
    for dia, peso, ica in dados:
        cur.execute("""
            INSERT INTO parametros_referencia
                (linhagem, dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct, fonte)
            VALUES (%s, %s, %s, %s, NULL, %s)
        """, ("Cobb 500", dia, peso, ica, FONTE_COBB500))


# ----------------------------------------------------------------------
# Linhagens de referência
# ----------------------------------------------------------------------
def listar_linhagens() -> list[str]:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT linhagem FROM parametros_referencia ORDER BY linhagem")
            return [r["linhagem"] for r in cur.fetchall()]


def guardar_linhagem(nome: str, linhas: list[dict], fonte: str | None = None):
    """Substitui a tabela de referência de uma linhagem pelas linhas dadas
    (cada linha: dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM parametros_referencia WHERE linhagem = %s", (nome,))
            for l in linhas:
                cur.execute("""
                    INSERT INTO parametros_referencia
                        (linhagem, dia, peso_medio_g, ica_acumulado,
                         mortalidade_acumulada_pct, fonte)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (nome, int(l["dia"]), l.get("peso_medio_g"), l.get("ica_acumulado"),
                      l.get("mortalidade_acumulada_pct"), fonte))
        conn.commit()


def apagar_linhagem(nome: str):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM parametros_referencia WHERE linhagem = %s", (nome,))
        conn.commit()


# ----------------------------------------------------------------------
# Configurações
# ----------------------------------------------------------------------
def obter_config(chave: str, padrao: str | None = None) -> str | None:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
            row = cur.fetchone()
    return row["valor"] if row else padrao


def definir_config(chave: str, valor: str):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO configuracoes (chave, valor) VALUES (%s, %s)
                ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
            """, (chave, str(valor)))
        conn.commit()


def uniformidade_minima() -> float:
    try:
        return float(obter_config("uniformidade_min", "80"))
    except (TypeError, ValueError):
        return 80.0


def _interp(a, b, frac):
    """Interpola entre dois valores; devolve None se algum faltar."""
    if a is None or b is None:
        return None
    return a + frac * (b - a)


def obter_referencia(linhagem: str, dia: int) -> dict | None:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct
                FROM parametros_referencia
                WHERE linhagem = %s
                ORDER BY dia ASC
            """, (linhagem,))
            rows = cur.fetchall()

    if not rows:
        return None

    campos = ("peso_medio_g", "ica_acumulado", "mortalidade_acumulada_pct")
    anterior = rows[0]
    for row in rows:
        if row["dia"] == dia:
            return dict(row)
        if row["dia"] > dia:
            d1, d2 = anterior["dia"], row["dia"]
            if d2 == d1:
                return dict(row)
            frac = (dia - d1) / (d2 - d1)
            resultado = {"dia": dia}
            for c in campos:
                resultado[c] = _interp(anterior[c], row[c], frac)
            return resultado
        anterior = row
    return dict(rows[-1])
