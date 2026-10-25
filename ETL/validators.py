# validators.py
import re
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from config import (
    logger, MONTO_MAXIMO_TRANSACCION, DIAS_MAXIMOS_FUTURO,
    TICKERS_VALIDOS, CARACTERES_PROHIBIDOS, FECHA_MINIMA
)

# ============================================
# EXCEPCIÓN DE VALIDACIÓN (detiene todo)
# ============================================
class ValidationError(Exception):
    def __init__(self, fila, campo, mensaje, valor=None):
        self.fila = fila
        self.campo = campo
        self.mensaje = mensaje
        self.valor = valor
        super().__init__(f"[Fila {fila} | {campo}] {mensaje} (valor: {valor!r})")


class ETLAbortError(Exception):
    """Se lanza cuando hay errores acumulados y se debe abortar TODO."""
    def __init__(self, errores):
        self.errores = errores
        super().__init__(f"ETL ABORTADO: {len(errores)} errores detectados")


# ============================================
# VALIDADORES DE TIPO (estrictos)
# ============================================
def validar_entero(valor, campo, fila, min_val=None, max_val=None):
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        raise ValidationError(fila, campo, "Valor vacío o nulo")
    try:
        if isinstance(valor, float) and not valor.is_integer():
            raise ValidationError(fila, campo, "Se esperaba entero, se recibió decimal", valor)
        num = int(float(valor))
    except (ValueError, TypeError):
        raise ValidationError(fila, campo, "No es un entero válido", valor)
    if min_val is not None and num < min_val:
        raise ValidationError(fila, campo, f"Menor al mínimo ({min_val})", valor)
    if max_val is not None and num > max_val:
        raise ValidationError(fila, campo, f"Mayor al máximo ({max_val})", valor)
    return num


def validar_decimal(valor, campo, fila, min_val=None, max_val=None, decimales=2):
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        raise ValidationError(fila, campo, "Valor vacío o nulo")
    try:
        num = round(float(valor), decimales)
    except (ValueError, TypeError):
        raise ValidationError(fila, campo, "No es numérico", valor)
    if min_val is not None and num < min_val:
        raise ValidationError(fila, campo, f"Menor al mínimo ({min_val})", valor)
    if max_val is not None and num > max_val:
        raise ValidationError(fila, campo, f"Mayor al máximo ({max_val})", valor)
    return num


def validar_texto(valor, campo, fila, min_len=1, max_len=255, patron=None, permitir_vacio=False):
    if pd.isna(valor) or valor is None:
        if permitir_vacio:
            return None
        raise ValidationError(fila, campo, "Valor vacío o nulo")
    texto = str(valor).strip()
    if not permitir_vacio and len(texto) == 0:
        raise ValidationError(fila, campo, "Texto vacío")
    if len(texto) < min_len:
        raise ValidationError(fila, campo, f"Menor a {min_len} caracteres", valor)
    if len(texto) > max_len:
        raise ValidationError(fila, campo, f"Excede {max_len} caracteres", valor)
    if re.search(CARACTERES_PROHIBIDOS, texto):
        raise ValidationError(fila, campo, "Contiene caracteres prohibidos", valor)
    if patron and not re.match(patron, texto):
        raise ValidationError(fila, campo, f"No cumple el patrón {patron}", valor)
    return texto


def validar_fecha(valor, campo, fila, formato=None, no_futuro=True):
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        raise ValidationError(fila, campo, "Fecha vacía o nula")
    
    valor_str = str(valor).strip()
    
    # Lista de formatos que el ETL aceptará (ISO, Día/Mes/Año, Año/Mes/Día, etc.)
    formatos_posibles = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]
    
    fecha = None
    for fmt in formatos_posibles:
        try:
            fecha = datetime.strptime(valor_str, fmt)
            break # Si logra convertirlo, se detiene el bucle
        except (ValueError, TypeError):
            continue # Si falla, prueba con el siguiente formato
            
    if fecha is None:
        raise ValidationError(fila, campo, f"Fecha inválida. Formatos aceptados: YYYY-MM-DD o DD/MM/YYYY (valor: {valor_str})", valor)
        
    if no_futuro and fecha > datetime.now() + timedelta(days=DIAS_MAXIMOS_FUTURO):
        raise ValidationError(fila, campo, "Fecha futura no permitida", valor)
    if fecha < datetime.strptime(FECHA_MINIMA, "%Y-%m-%d"):
        raise ValidationError(fila, campo, f"Fecha anterior a {FECHA_MINIMA}", valor)
        
    # Al final, siempre devolvemos la fecha en el formato que PostgreSQL espera (YYYYMMDD)
    return fecha.strftime("%Y%m%d")


def validar_booleano(valor, campo, fila, default=False):
    """Devuelve booleanos reales para PostgreSQL."""
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        return default
    if isinstance(valor, bool):
        return valor
    s = str(valor).strip().lower()
    if s in ("1", "true", "si", "sí", "yes", "y", "verdadero"):
        return True
    if s in ("0", "false", "no", "n", "falso"):
        return False
    raise ValidationError(fila, campo, "No es booleano válido", valor)


def validar_fk(valor, campo, fila, dimensiones, tabla_dim, col_dim, nullable=False):
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        if nullable:
            return None
        raise ValidationError(fila, campo, f"FK obligatoria hacia {tabla_dim}")
    try:
        valor = int(float(valor))
    except (ValueError, TypeError):
        raise ValidationError(fila, campo, f"FK debe ser entero para {tabla_dim}", valor)
    df_dim = dimensiones.get(tabla_dim, pd.DataFrame())
    if df_dim.empty:
        raise ValidationError(fila, campo, f"Dimensión {tabla_dim} vacía o no cargada")
    if valor not in df_dim[col_dim].values:
        raise ValidationError(fila, campo, f"FK {valor} no existe en {tabla_dim}.{col_dim}", valor)
    return valor


# ============================================
# VALIDADORES DE DUPLICADOS
# ============================================
def detectar_duplicados_staging(df, columnas_clave, nombre_tabla):
    """Si hay duplicados en el staging, lanza excepción."""
    if df.empty:
        return
    dup_mask = df.duplicated(subset=columnas_clave, keep=False)
    if dup_mask.any():
        filas_dup = df[dup_mask].index.tolist()
        raise ValidationError(
            filas_dup[0] + 2, "DUPLICADO",
            f"Duplicados detectados en {nombre_tabla} por columnas {columnas_clave}. "
            f"Filas: {[i+2 for i in filas_dup]}"
        )


def detectar_duplicados_bd(df_staging, tabla_destino, columnas_clave, conn):
    """Si un registro ya existe en BD (PostgreSQL), lanza excepción."""
    if df_staging.empty:
        return
    try:
        condiciones = []
        params = {}
        for i, row in df_staging.iterrows():
            sub = []
            for c in columnas_clave:
                pname = f"{c}_{i}"
                sub.append(f"{c} = :{pname}")
                params[pname] = row[c]
            condiciones.append("(" + " AND ".join(sub) + ")")
        query = f"SELECT COUNT(*) FROM {tabla_destino} WHERE " + " OR ".join(condiciones)
        resultado = conn.execute(text(query), params).scalar()
        if resultado and resultado > 0:
            raise ValidationError(
                0, "DUPLICADO_BD",
                f"{resultado} registros ya existen en {tabla_destino} con {columnas_clave}"
            )
    except ValidationError:
        raise
    except Exception as e:
        logger.warning(f"No se pudo verificar duplicados en {tabla_destino}: {e}")


# ============================================
# VALIDADORES DE REGLAS DE NEGOCIO
# ============================================
def validar_reglas_negocio_inversion(row, fila):
    tipo = str(row.get("TipoTransaccionInversion", "")).lower()
    cantidad = row.get("Cantidad")
    if "venta" in tipo and cantidad and float(cantidad) > 0:
        raise ValidationError(fila, "Cantidad", "Venta con cantidad positiva", cantidad)
    
    try:
        bruto = float(row.get("MontoBruto", 0))
        comision = float(row.get("Comision", 0))
        impuestos = float(row.get("Impuestos", 0))
        neto = float(row.get("MontoNeto", 0))
        esperado = round(bruto + comision + impuestos, 2)
        if abs(neto - esperado) > 0.01:
            raise ValidationError(
                fila, "MontoNeto",
                f"Incoherente: esperado {esperado}, recibido {neto}"
            )
    except (ValueError, TypeError):
        pass


def validar_monto_alto(monto, fila, campo):
    if abs(float(monto)) > MONTO_MAXIMO_TRANSACCION:
        raise ValidationError(fila, campo, f"Monto excede el máximo permitido ({MONTO_MAXIMO_TRANSACCION})", monto)