# config_ejemplo.py
import os
import logging
from logging.handlers import RotatingFileHandler
from sqlalchemy import create_engine

# ============================================
# INSTRUCCIONES PARA EL NUEVO USUARIO
# ============================================
# 1. Renombra este archivo a "config.py"
# 2. Cambia "TU_PASSWORD_AQUI" por la contraseña real de tu PostgreSQL.
# 3. Asegúrate de haber creado la base de datos y las tablas antes de correr el ETL.

# ============================================
# BASE DE DATOS (PostgreSQL)
# ============================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "finanzas_personales")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "TU_PASSWORD_AQUI")  # <-- CAMBIAR ESTO
DB_SCHEMA = os.getenv("DB_SCHEMA", "dwh")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={"options": f"-csearch_path={DB_SCHEMA},public"}
)

# ============================================
# LOGGING
# ============================================
logger = logging.getLogger("ETL_STRICT")
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))

file_handler = RotatingFileHandler(
    "etl.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s"
))

logger.addHandler(console)
logger.addHandler(file_handler)

# ============================================
# CONSTANTES DE NEGOCIO
# ============================================
MONTO_MAXIMO_TRANSACCION = 1_000_000
DIAS_MAXIMOS_FUTURO = 1
TICKERS_VALIDOS = r"^[A-Z0-9.]{1,10}$"
CARACTERES_PROHIBIDOS = r"[<>\"'%;()&+]"
FECHA_MINIMA = "2000-01-01"