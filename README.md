# GESTAV v2 — Sistema de Gestão Técnico-Económica da Unidade Avícola

Protótipo funcional com backend em **Supabase (PostgreSQL)** e frontend em **Streamlit**.

**Autor:** Alberto Jeque Júnior · Licenciatura em Ciência e Tecnologia Animal, FAVET-UEM.

## Arquitectura

- **Camada de apresentação:** Streamlit (`app.py`)
- **Camada de lógica:** Python (`calculos.py`, `sensibilidade.py`, `relatorios.py`)
- **Camada de persistência:** PostgreSQL hospedado no Supabase (`database.py`, via `psycopg2`)
- **Autenticação:** PBKDF2-SHA256 (`auth.py`), 120 000 iterações, com credenciais e salt armazenados no PostgreSQL

## Setup inicial (uma vez)

### 1. Criar projecto no Supabase

1. Entrar em https://supabase.com e criar conta (gratuita).
2. Clicar em **New project**.
3. Preencher: nome do projecto (`gestav-favet`), palavra-passe da base de dados (guardar bem), região (recomendado `West Europe (eu-west-1)` para menor latência de Moçambique).
4. Aguardar cerca de dois minutos pela criação do projecto.

### 2. Obter a connection string

1. No projecto criado, abrir **Project Settings** → **Database**.
2. Secção **Connection string**, separador **URI**.
3. Copiar a linha (começa por `postgresql://postgres:...`).
4. Substituir `[YOUR-PASSWORD]` pela palavra-passe definida no passo 1.

### 3. Configurar o `.env`

```bash
cp .env.example .env
# abrir .env e colar a connection string na variável SUPABASE_DB_URL
```

### 4. Instalar dependências

```bash
pip install -r requirements.txt
```

### 5. Inicializar as tabelas

Duas opções:

**Opção A (automática):** Correr a aplicação. Na primeira execução, `database.inicializar_bd()` cria todas as tabelas e carrega os parâmetros Ross 308.

**Opção B (manual, via SQL Editor):** Abrir o Supabase → SQL Editor → New query → colar o conteúdo de `schema.sql` → **Run**.

### 6. Correr a aplicação

```bash
streamlit run app.py
```

Abrir no navegador em http://localhost:8501.

**Credenciais padrão** (criadas automaticamente):
- Utilizador: `admin`
- Palavra-passe: `admin123`

**Alterar imediatamente após o primeiro acesso.**

## Vantagens do Supabase (vs. SQLite local)

- Base de dados acessível a partir de qualquer computador com acesso à internet
- Múltiplos utilizadores em simultâneo, em locais diferentes
- Backups automáticos geridos pelo Supabase
- Painel web para consultar e editar os dados directamente
- Base para evoluir, no futuro, para integração com outras unidades universitárias

## Módulos

1. Autenticação
2. Dashboard
3. Novo ciclo
4. Ver ciclos
5. Registo diário
6. Pesagens
7. Custos
8. Vendas
9. Indicadores (síntese + semáforos Ross 308)
10. Análise de sensibilidade
11. Relatórios (PDF)
12. Gestão de utilizadores
