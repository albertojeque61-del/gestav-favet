-- GESTAV — esquema PostgreSQL para o Supabase.
-- Executar este script no SQL Editor do Supabase (menu lateral: SQL Editor
-- -> New query), colar e carregar em "Run".
--
-- Em alternativa, basta executar a aplicação uma vez com o .env configurado
-- que o `database.inicializar_bd()` cria as tabelas automaticamente.

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

-- Parâmetros Ross 308 (misto) — Aviagen Performance Objectives
INSERT INTO parametros_referencia
    (linhagem, dia, peso_medio_g, ica_acumulado, mortalidade_acumulada_pct)
VALUES
    ('Ross 308', 0, 42, 0.00, 0.0),
    ('Ross 308', 7, 196, 0.90, 1.0),
    ('Ross 308', 14, 490, 1.20, 2.0),
    ('Ross 308', 21, 942, 1.33, 3.0),
    ('Ross 308', 28, 1521, 1.47, 3.5),
    ('Ross 308', 35, 2200, 1.60, 4.0),
    ('Ross 308', 42, 2902, 1.73, 5.0)
ON CONFLICT (linhagem, dia) DO NOTHING;

-- ---------------------------------------------------------------
-- Alterações introduzidas depois do pré-teste (Novembro de 2026)
-- ---------------------------------------------------------------
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

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_tipo TEXT NOT NULL DEFAULT 'idade';
ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_idade INTEGER NOT NULL DEFAULT 42;
ALTER TABLE ciclos ADD COLUMN IF NOT EXISTS fim_peso_g REAL;
ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS uniformidade_pct REAL;
ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS cv_pct REAL;
ALTER TABLE pesagens ADD COLUMN IF NOT EXISTS pesos_individuais TEXT;
ALTER TABLE vendas ADD COLUMN IF NOT EXISTS destino TEXT;
ALTER TABLE parametros_referencia ADD COLUMN IF NOT EXISTS fonte TEXT;
