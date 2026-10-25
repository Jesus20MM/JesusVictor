# etl_presupuesto.py
import pandas as pd
from sqlalchemy import text
from config import engine, logger
from validators import (
    ValidationError, ETLAbortError,
    validar_decimal, validar_fecha, validar_fk,
    detectar_duplicados_staging, detectar_duplicados_bd
)
from etl_movimientos import cargar_dimensiones, resolver_llaves


def validar_fila_presupuesto(row, dims, fila):
    r = {}
    r["FechaKey"] = validar_fecha(row.get("Fecha"), "Fecha", fila)
    validar_fk(r["FechaKey"], "FechaKey", fila, dims, "dimfecha", "fechakey")
    r["TipoPresupuestoKey"] = validar_fk(row.get("tipopresupuestokey"), "TipoPresupuestoKey", fila, dims, "dimtipopresupuesto", "tipopresupuestokey")
    r["SegmentoPresupuestoKey"] = validar_fk(row.get("segmentopresupuestokey"), "SegmentoPresupuestoKey", fila, dims, "dimsegmentopresupuesto", "segmentopresupuestokey")
    r["MontoPlaneado"] = validar_decimal(row.get("MontoPlaneado"), "MontoPlaneado", fila, min_val=0)
    return r


def autocrear_dim_presupuesto(df, col_nombre, col_key, tabla, columna_db_nombre, columna_db_key, dims):
    if col_key in df.columns:
        faltantes = df[df[col_key].isna()][col_nombre].dropna().unique()
        for val_nuevo in faltantes:
            if str(val_nuevo).strip() != "":
                logger.warning(f"⚠️ '{val_nuevo}' no existe en {tabla}. Creándolo...")
                with engine.begin() as conn:
                    query = text(f"INSERT INTO {tabla} ({columna_db_key}, {columna_db_nombre}) VALUES (DEFAULT, :nombre) RETURNING {columna_db_key}")
                    nuevo_id = conn.execute(query, {"nombre": str(val_nuevo).title()}).scalar()
                
                def norm(t): return str(t).strip().lower()
                df.loc[df[col_nombre].apply(norm) == norm(val_nuevo), col_key] = nuevo_id
                
                # Actualizamos el caché global en memoria
                from etl_movimientos import _dim_cache
                _dim_cache[tabla] = pd.read_sql(f"SELECT * FROM {tabla}", engine)
                dims[tabla] = _dim_cache[tabla]


# ============================================
# FASE 1: PREPARAR
# ============================================
def preparar_presupuesto(ruta_excel):
    logger.info("=" * 70)
    logger.info("FASE 1: PREPARACIÓN DE PRESUPUESTO")
    logger.info("=" * 70)
    
    logger.info("📥 Leyendo Hoja 2: 'Operativa fact presupuesto'...")
    df = pd.read_excel(ruta_excel, sheet_name="Operativa fact presupuesto")
    
    # Renombrar columnas
    df = df.rename(columns={
        "Tipo presupuesto": "TipoPresupuesto",
        "Segmento presupuesto": "SegmentoPresupuesto",
        "Monto planeado": "MontoPlaneado"
    })
    
    df.columns = df.columns.str.strip()
    logger.info(f"Columnas detectadas: {df.columns.tolist()}")
    
    requeridas = ["Fecha", "TipoPresupuesto", "SegmentoPresupuesto", "MontoPlaneado"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValidationError(0, "ESTRUCTURA", f"Columnas faltantes en el Excel: {faltantes}")
    
    df = df.dropna(how="all").reset_index(drop=True)
    
    # Resolver llaves
    dims = cargar_dimensiones()
    df = resolver_llaves(df, dims)
    
    # --- AUTO-CREACIÓN DE TIPOS Y SEGMENTOS FALTANTES ---
    autocrear_dim_presupuesto(df, "TipoPresupuesto", "tipopresupuestokey", "dimtipopresupuesto", "nombretipopresupuesto", "tipopresupuestokey", dims)
    autocrear_dim_presupuesto(df, "SegmentoPresupuesto", "segmentopresupuestokey", "dimsegmentopresupuesto", "nombresegmentopresupuesto", "segmentopresupuestokey", dims)
    # ---------------------------------------------------
    
    errores = []
    filas_ok = []
    for idx, row in df.iterrows():
        fila = idx + 2
        try:
            filas_ok.append(validar_fila_presupuesto(row, dims, fila))
        except ValidationError as e:
            errores.append(str(e))
            logger.error(f"   ❌ {e}")
    
    if errores:
        logger.critical(f"🛑 {len(errores)} errores detectados. ABORTANDO ETL.")
        raise ETLAbortError(errores)
    
    logger.info(f"✅ Validación completa: {len(filas_ok)} filas listas")
    return pd.DataFrame(filas_ok) if filas_ok else pd.DataFrame()


# ============================================
# FASE 2: CARGAR
# ============================================
def cargar_presupuesto(conn, df_pres):
    if df_pres.empty:
        return
        
    df_pres.columns = df_pres.columns.str.lower()
    df_pres['fechakey'] = df_pres['fechakey'].astype(int)
    
    df_existente = pd.read_sql("SELECT fechakey, tipopresupuestokey, segmentopresupuestokey FROM factpresupuesto", conn)
    if not df_existente.empty:
        df_pres = df_pres.merge(df_existente, on=["fechakey", "tipopresupuestokey", "segmentopresupuestokey"], how="left", indicator=True)
        df_pres = df_pres[df_pres["_merge"] == "left_only"].drop(columns=["_merge"])
        
    if not df_pres.empty:
        df_pres.to_sql("factpresupuesto", conn, if_exists="append", index=False, method="multi", chunksize=1000)
        logger.info(f"   ✅ {len(df_pres)} filas NUEVAS en factpresupuesto")
    else:
        logger.info("   ℹ️ No hay filas nuevas en factpresupuesto (todas ya existían)")