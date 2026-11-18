"""
Camada de persistência — PostgreSQL hospedado no Supabase.
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
            """)
            _popular_parametros_ross308(cur)
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

    anterior = rows[0]
    for row in rows:
        if row["dia"] == dia:
            return dict(row)
        if row["dia"] > dia:
            d1, d2 = anterior["dia"], row["dia"]
            if d2 == d1:
                return dict(row)
            frac = (dia - d1) / (d2 - d1)
            return {
                "dia": dia,
                "peso_medio_g": anterior["peso_medio_g"] + frac * (row["peso_medio_g"] - anterior["peso_medio_g"]),
                "ica_acumulado": anterior["ica_acumulado"] + frac * (row["ica_acumulado"] - anterior["ica_acumulado"]),
                "mortalidade_acumulada_pct": anterior["mortalidade_acumulada_pct"] + frac * (row["mortalidade_acumulada_pct"] - anterior["mortalidade_acumulada_pct"]),
            }
        anterior = row
    return dict(rows[-1])
