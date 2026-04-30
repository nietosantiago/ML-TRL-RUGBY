"""
Inicializa la base de datos TRL ejecutando el schema SQL.
Crea la DB y el usuario si no existen (requiere permisos de superusuario).

USO:
  python scripts/setup_db.py
  python scripts/setup_db.py --reset   # Borra y recrea (DESTRUCTIVO)
"""

import os
import sys
import argparse
import logging
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_db")

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 5432))
DB_NAME     = os.getenv("DB_NAME", "trl_db")
DB_USER     = os.getenv("DB_USER", "trl_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "trl_password")
DB_ADMIN    = os.getenv("DB_ADMIN_USER", "postgres")
DB_ADMIN_PW = os.getenv("DB_ADMIN_PASSWORD", "")

SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schemas" / "init.sql"


def admin_connection(dbname: str = "postgres"):
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=dbname,
        user=DB_ADMIN, password=DB_ADMIN_PW,
    )


def app_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )


def create_user_and_db():
    """Crea el usuario y la base de datos si no existen."""
    conn = admin_connection()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (DB_USER,))
        if not cur.fetchone():
            cur.execute(
                f"CREATE USER {DB_USER} WITH PASSWORD %s",
                (DB_PASSWORD,)
            )
            logger.info(f"Usuario '{DB_USER}' creado.")
        else:
            logger.info(f"Usuario '{DB_USER}' ya existe.")

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {DB_NAME} OWNER {DB_USER} ENCODING 'UTF8'")
            logger.info(f"Base de datos '{DB_NAME}' creada.")
        else:
            logger.info(f"Base de datos '{DB_NAME}' ya existe.")

        cur.execute(f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER}")
    finally:
        cur.close()
        conn.close()


def apply_schema():
    """Aplica el schema SQL al database."""
    if not SCHEMA_PATH.exists():
        logger.error(f"Schema no encontrado: {SCHEMA_PATH}")
        sys.exit(1)

    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    conn = admin_connection(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Schema aplicado correctamente.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error aplicando schema: {e}")
        raise
    finally:
        conn.close()


def grant_permissions():
    """Otorga permisos al usuario de aplicación sobre todas las tablas."""
    conn = admin_connection(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                GRANT SELECT, INSERT, UPDATE, DELETE
                ON ALL TABLES IN SCHEMA public TO {DB_USER};
            """)
            cur.execute(f"""
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {DB_USER};
            """)
            cur.execute(f"""
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {DB_USER};
            """)
        conn.commit()
        logger.info(f"Permisos otorgados a '{DB_USER}'.")
    finally:
        conn.close()


def drop_db():
    """Elimina la base de datos (DESTRUCTIVO)."""
    conn = admin_connection()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
    conn.close()
    logger.warning(f"Base de datos '{DB_NAME}' eliminada.")


def verify_connection():
    """Verifica que la conexión de aplicación funciona."""
    try:
        conn = app_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
        conn.close()
        logger.info(f"Conexión verificada: {version}")
        return True
    except Exception as e:
        logger.error(f"Verificación fallida: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Setup DB TRL")
    parser.add_argument("--reset", action="store_true",
                        help="Eliminar y recrear la DB (DESTRUCTIVO)")
    parser.add_argument("--schema-only", action="store_true",
                        help="Solo aplicar schema (DB ya existe)")
    args = parser.parse_args()

    if args.reset:
        confirm = input(f"¿Estás seguro de que quieres ELIMINAR '{DB_NAME}'? (escribí 'si'): ")
        if confirm.lower() != "si":
            print("Operación cancelada.")
            sys.exit(0)
        drop_db()

    if not args.schema_only:
        create_user_and_db()

    apply_schema()
    grant_permissions()

    if verify_connection():
        print("\n✓ Base de datos lista. Podés ejecutar: python scripts/seed_data.py")
    else:
        print("\n✗ Error en la verificación de conexión.")
        sys.exit(1)


if __name__ == "__main__":
    main()
