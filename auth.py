"""
Autenticação local (PBKDF2-SHA256).
Os utilizadores ficam armazenados no PostgreSQL do Supabase, mas a
validação da palavra-passe faz-se do lado da aplicação, mantendo o
requisito RNF4 (hash + salt).
"""

import hashlib
import secrets
from datetime import datetime
from database import conectar

ITERATIONS = 120_000


def _hash_pw(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
    )
    return dk.hex()


def registar_utilizador(username: str, nome_completo: str, password: str,
                         papel: str = "operador") -> bool:
    salt = secrets.token_hex(16)
    pw_hash = _hash_pw(password, salt)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM utilizadores WHERE username = %s", (username,))
            if cur.fetchone():
                return False
            cur.execute("""
                INSERT INTO utilizadores
                    (username, nome_completo, password_hash, salt, papel, criado_em)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, nome_completo, pw_hash, salt, papel,
                  datetime.now().isoformat()))
        conn.commit()
    return True


def validar_credenciais(username: str, password: str) -> dict | None:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, nome_completo, password_hash, salt, papel
                FROM utilizadores WHERE username = %s
            """, (username,))
            row = cur.fetchone()

    if row is None:
        return None

    tentativa = _hash_pw(password, row["salt"])
    if secrets.compare_digest(tentativa, row["password_hash"]):
        return {
            "id": row["id"],
            "username": row["username"],
            "nome_completo": row["nome_completo"],
            "papel": row["papel"],
        }
    return None


SENHA_PADRAO = "admin123"


def definir_palavra_passe(username: str, nova: str):
    """Grava uma nova palavra-passe (novo salt) para o utilizador."""
    salt = secrets.token_hex(16)
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE utilizadores SET password_hash = %s, salt = %s
                WHERE username = %s
            """, (_hash_pw(nova, salt), salt, username))
        conn.commit()


def mudar_palavra_passe(username: str, actual: str, nova: str) -> tuple[bool, str]:
    if validar_credenciais(username, actual) is None:
        return False, "A palavra-passe actual não está correcta."
    if len(nova) < 6:
        return False, "A nova palavra-passe deve ter pelo menos 6 caracteres."
    if nova == actual:
        return False, "A nova palavra-passe tem de ser diferente da actual."
    definir_palavra_passe(username, nova)
    return True, "Palavra-passe alterada."


def admin_com_senha_padrao() -> bool:
    """Verdadeiro se a conta admin ainda usa a palavra-passe de origem."""
    return validar_credenciais("admin", SENHA_PADRAO) is not None


def criar_admin_padrao():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM utilizadores")
            existe_algum = cur.fetchone()["n"] > 0
    if existe_algum:
        return False
    registar_utilizador("admin", "Administrador do Sistema",
                        "admin123", papel="administrador")
    return True
