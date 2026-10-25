import os
import subprocess
from datetime import datetime
import logging

# ============================================
# CONFIGURACIÓN DEL BACKUP
# ============================================
RUTA_PG_DUMP = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" # <-- Ajusta tu versión si es 15 o 17
CARPETA_BACKUPS = r"C:\Users\zabu\Desktop\ETL\backups"           # <-- Se creará sola si no existe

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "finanzas_personales"
DB_USER = "postgres"
DB_PASSWORD = "TMHzabusito88"  # <-- Pon tu contraseña real

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BACKUP")

def realizar_backup():
    # 1. Crear la carpeta de backups si no existe
    if not os.path.exists(CARPETA_BACKUPS):
        os.makedirs(CARPETA_BACKUPS)
        logger.info(f"Carpeta creada: {CARPETA_BACKUPS}")

    # 2. Generar el nombre del archivo con la fecha actual
    fecha_actual = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_archivo = f"backup_finanzas_{fecha_actual}.backup"
    ruta_completa = os.path.join(CARPETA_BACKUPS, nombre_archivo)

    # 3. Preparar las variables de entorno (para no meter la contraseña en el comando)
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    # 4. Construir el comando de pg_dump
    comando = [
        RUTA_PG_DUMP,
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "-F", "c",           # Formato Custom (comprimido)
        "-f", ruta_completa
    ]

    logger.info(f"⏳ Iniciando respaldo de la base de datos '{DB_NAME}'...")

    try:
        # 5. Ejecutar el comando
        resultado = subprocess.run(comando, env=env, capture_output=True, text=True, cwd=CARPETA_BACKUPS)
        
        if resultado.returncode == 0:
            logger.info(f"✅ Backup exitoso: {nombre_archivo}")
        else:
            logger.error(f"❌ Error en pg_dump: {resultado.stderr}")
            
    except FileNotFoundError:
        logger.error(f"❌ No se encontró pg_dump en la ruta: {RUTA_PG_DUMP}")
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    realizar_backup()