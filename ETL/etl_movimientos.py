# etl_movimientos.py
import pandas as pd
import unicodedata
import re
from config import engine, logger
from sqlalchemy import text
from validators import (
    ValidationError, ETLAbortError,
    validar_entero, validar_decimal, validar_texto, validar_fecha,
    validar_booleano, validar_fk, validar_monto_alto,
    validar_reglas_negocio_inversion,
    detectar_duplicados_staging, detectar_duplicados_bd
)

_dim_cache = {}

def cargar_dimensiones():
    global _dim_cache
    if _dim_cache:
        return _dim_cache
    tablas = [
        "dimfecha", "dimmoneda", "dimcuenta", "dimcategoriafinanciera",
        "dimdetalle", "dimobjetivo", "dimtipotransaccion", "dimsegmentopresupuesto",
        "diminversion", "dimcasabolsa", "dimtipoorden",
        "dimtipotransaccioninversion", "diminstitucion", "dimtipopresupuesto", "dim_reglas_clasificacion"
    ]
    for t in tablas:
        try:
            _dim_cache[t] = pd.read_sql(f"SELECT * FROM {t}", engine)
        except Exception:
            logger.warning(f"Dimensión {t} no disponible")
            _dim_cache[t] = pd.DataFrame()
    return _dim_cache


def resolver_llaves(df, dimensiones):
    def normalizar(texto):
        if pd.isna(texto):
            return texto
        texto_limpio = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
        texto_limpio = re.sub(r'[^a-zA-Z0-9]', '', texto_limpio)
        return texto_limpio.lower()

    # --- LÓGICA DE REGLAS ---
    df_reglas = dimensiones.get("dim_reglas_clasificacion", pd.DataFrame())
    reglas_dict = {}
    if not df_reglas.empty:
        for _, row in df_reglas.iterrows():
            reglas_dict[normalizar(row['texto_origen'])] = normalizar(row['categoria_destino'])
            
    if "Categoria" in df.columns:
        def aplicar_regla(texto_categoria):
            cat_original = normalizar(texto_categoria)
            if cat_original in reglas_dict:
                return reglas_dict[cat_original]
            return cat_original 
            
        df["Categoria"] = df["Categoria"].apply(aplicar_regla)
    # -------------------------

    mapeos = {
        "Cuenta": ("dimcuenta", "nombrecuenta", "cuentakey"),
        "Categoria": ("dimcategoriafinanciera", "nombrecategoriafinanciera", "categoriafinancierakey"),
        "Detalle": ("dimdetalle", "nombredetalle", "detallekey"),
        "Objetivo": ("dimobjetivo", "nombreobjetivo", "objetivokey"),
        "TipoTransaccion": ("dimtipotransaccion", "tipotransaccion", "tipotransaccionkey"),
        "Moneda": ("dimmoneda", "nombremoneda", "monedakey"),
        "Inversion": ("diminversion", "nombreinversion", "inversionkey"),
        "CasaBolsa": ("dimcasabolsa", "nombrecasabolsa", "casabolsakey"),
        "TipoOrden": ("dimtipoorden", "tipoorden", "tipoordenkey"),
        "TipoTransaccionInversion": ("dimtipotransaccioninversion", "tipotransaccion", "tipotransaccioninversionkey"),
        "Institucion": ("diminstitucion", "tipoinstitucion", "institucionkey"),
        "TipoPresupuesto": ("dimtipopresupuesto", "nombretipopresupuesto", "tipopresupuestokey"),
        "SegmentoPresupuesto": ("dimsegmentopresupuesto", "nombresegmentopresupuesto", "segmentopresupuestokey"),
    }
    
    for col_form, (tabla, col_dim, col_fk) in mapeos.items():
        if col_form in df.columns:
            dim = dimensiones.get(tabla, pd.DataFrame())
            if not dim.empty:
                llaves_dim = dim[col_dim].apply(normalizar)
                mapa = dict(zip(llaves_dim, dim[col_fk]))
                df[col_fk] = df[col_form].apply(normalizar).map(mapa)
                
    return df


# ============================================
# VALIDACIÓN DE FILA
# ============================================
def validar_fila_financiera(row, dims, fila):
    r = {}
    r["FechaKey"] = validar_fecha(row.get("Fecha"), "Fecha", fila)
    validar_fk(r["FechaKey"], "FechaKey", fila, dims, "dimfecha", "fechakey")
    r["CuentaKey"] = validar_fk(row.get("cuentakey"), "CuentaKey", fila, dims, "dimcuenta", "cuentakey")
    r["CategoriaFinancieraKey"] = validar_fk(row.get("categoriafinancierakey"), "CategoriaFinancieraKey", fila, dims, "dimcategoriafinanciera", "categoriafinancierakey")
    r["DetalleKey"] = validar_fk(row.get("detallekey"), "DetalleKey", fila, dims, "dimdetalle", "detallekey", nullable=True)
    r["ObjetivoKey"] = validar_fk(row.get("objetivokey"), "ObjetivoKey", fila, dims, "dimobjetivo", "objetivokey", nullable=True)
    r["TipoTransaccionKey"] = validar_fk(row.get("tipotransaccionkey"), "TipoTransaccionKey", fila, dims, "dimtipotransaccion", "tipotransaccionkey")
    r["SegmentoPresupuestoKey"] = validar_fk(row.get("segmentopresupuestokey"), "SegmentoPresupuestoKey", fila, dims, "dimsegmentopresupuesto", "segmentopresupuestokey", nullable=True)
    r["MonedaKey"] = validar_fk(row.get("monedakey"), "MonedaKey", fila, dims, "dimmoneda", "monedakey")
    r["Monto"] = validar_decimal(row.get("Monto"), "Monto", fila)
    validar_monto_alto(r["Monto"], fila, "Monto")
    r["TieneFacturaCFDI"] = validar_booleano(row.get("TieneFacturaCFDI", 0), "TieneFacturaCFDI", fila)
    return r


def validar_fila_inversion(row, dims, fila):
    r = {}
    r["FechaKey"] = validar_fecha(row.get("Fecha"), "Fecha", fila)
    validar_fk(r["FechaKey"], "FechaKey", fila, dims, "dimfecha", "fechakey")
    r["CuentaKey"] = validar_fk(row.get("cuentakey"), "CuentaKey", fila, dims, "dimcuenta", "cuentakey")
    r["ObjetivoKey"] = validar_fk(row.get("objetivokey"), "ObjetivoKey", fila, dims, "dimobjetivo", "objetivokey", nullable=True)
    r["MonedaKey"] = validar_fk(row.get("monedakey"), "MonedaKey", fila, dims, "dimmoneda", "monedakey")
    r["InversionKey"] = validar_fk(row.get("inversionkey"), "InversionKey", fila, dims, "diminversion", "inversionkey")
    r["CasaBolsaKey"] = validar_fk(row.get("casabolsakey"), "CasaBolsaKey", fila, dims, "dimcasabolsa", "casabolsakey", nullable=True)
    r["TipoOrdenKey"] = validar_fk(row.get("tipoordenkey"), "TipoOrdenKey", fila, dims, "dimtipoorden", "tipoordenkey", nullable=True)
    r["TipoTransaccionInversionKey"] = validar_fk(row.get("tipotransaccioninversionkey"), "TipoTransaccionInversionKey", fila, dims, "dimtipotransaccioninversion", "tipotransaccioninversionkey")
    r["InstitucionKey"] = validar_fk(row.get("institucionkey"), "InstitucionKey", fila, dims, "diminstitucion", "institucionkey", nullable=True)
    r["Cantidad"] = validar_decimal(row.get("Cantidad"), "Cantidad", fila, min_val=0.00000001)
    r["PrecioUnitario"] = validar_decimal(row.get("PrecioUnitario"), "PrecioUnitario", fila, min_val=0.00000001)
    mb = row.get("MontoBruto")
    if pd.isna(mb) or mb is None or str(mb).strip() == "":
        mb = r["Cantidad"] * r["PrecioUnitario"]
    r["MontoBruto"] = validar_decimal(mb, "MontoBruto", fila, min_val=0)
    com = row.get("Comision", 0)
    r["Comision"] = validar_decimal(com, "Comision", fila, min_val=0) if not pd.isna(com) and str(com).strip() != "" else 0.0
    imp = row.get("Impuestos", 0)
    r["Impuestos"] = validar_decimal(imp, "Impuestos", fila, min_val=0) if not pd.isna(imp) and str(imp).strip() != "" else 0.0
    r["MontoNeto"] = round(r["MontoBruto"] + r["Comision"] + r["Impuestos"], 2)
    validar_monto_alto(r["MontoNeto"], fila, "MontoNeto")
    r["EsFraccion"] = validar_booleano(row.get("EsFraccion", 0), "EsFraccion", fila)
    validar_reglas_negocio_inversion(r, fila)
    return r


# ============================================
# FUNCIÓN AUXILIAR PARA AUTOCREAR DIMENSIONES
# ============================================
def autocrear_dimensiones_faltantes(df, col_nombre, col_key, tabla, columna_db_nombre, columna_db_key, columna_extra=None, valor_extra=None, dims=None):
    if col_key in df.columns:
        faltantes = df[df[col_key].isna()][col_nombre].dropna().unique()
        for val_nuevo in faltantes:
            if str(val_nuevo).strip() != "":
                logger.warning(f"⚠️ '{val_nuevo}' no existe en {tabla}. Creándolo...")
                with engine.begin() as conn:
                    if columna_extra:
                        query = text(f"INSERT INTO {tabla} ({columna_db_key}, {columna_db_nombre}, {columna_extra}) VALUES (DEFAULT, :nombre, :extra) RETURNING {columna_db_key}")
                        nuevo_id = conn.execute(query, {"nombre": str(val_nuevo).title(), "extra": valor_extra}).scalar()
                    else:
                        if tabla == "dimcuenta":
                            query = text(f"INSERT INTO {tabla} ({columna_db_key}, {columna_db_nombre}, tipocuenta, estatuscuenta) VALUES (DEFAULT, :nombre, 'Desconocido', 'Activa') RETURNING {columna_db_key}")
                        else:
                            query = text(f"INSERT INTO {tabla} ({columna_db_key}, {columna_db_nombre}) VALUES (DEFAULT, :nombre) RETURNING {columna_db_key}")
                        nuevo_id = conn.execute(query, {"nombre": str(val_nuevo).title()}).scalar()
                
                def norm(t): return str(t).strip().lower()
                df.loc[df[col_nombre].apply(norm) == norm(val_nuevo), col_key] = nuevo_id
                
                if dims is not None:
                    _dim_cache[tabla] = pd.read_sql(f"SELECT * FROM {tabla}", engine)
                    dims[tabla] = _dim_cache[tabla]


# ============================================
# FASE 1: PREPARAR (Leer Excel de 3 hojas)
# ============================================
def preparar_movimientos(ruta_excel):
    logger.info("=" * 70)
    logger.info("FASE 1: PREPARACIÓN DE TRANSACCIONES E INVERSIONES")
    logger.info("=" * 70)
    
    dims = cargar_dimensiones()
    
    # ==========================================
    # 1. PROCESAR HOJA 1: TRANSACCIONES FINANCIERAS
    # ==========================================
    logger.info("📥 Leyendo Hoja 1: 'Operativa fact transaccion'...")
    df_fin = pd.read_excel(ruta_excel, sheet_name="Operativa fact transaccion")
    
    df_fin.columns = df_fin.columns.str.strip()
    logger.info(f"Columnas exactas detectadas en Python: {df_fin.columns.tolist()}")
    
    df_fin = df_fin.rename(columns={
        "Categoria Financiera": "Categoria",
        "Modena": "Moneda",
        "Tipo Transaccion": "TipoTransaccion",
        "Segmento presupuesto": "SegmentoPresupuesto",
        "Factura CFDI": "TieneFacturaCFDI"
    })
    
    requeridas_fin = ["Fecha", "Monto", "Cuenta", "TipoTransaccion"]
    faltantes_fin = [c for c in requeridas_fin if c not in df_fin.columns]
    if faltantes_fin:
        raise ValidationError(0, "ESTRUCTURA", f"Faltan columnas en la hoja de transacciones: {faltantes_fin}. (¿Olvidaste agregar la columna 'Monto'?)")
        
    df_fin = df_fin.dropna(how="all").reset_index(drop=True)
    df_fin = resolver_llaves(df_fin, dims)
    
    # Autocreación de categorías en Hoja 1
    if "categoriafinancierakey" in df_fin.columns:
        faltantes_cat = df_fin[df_fin["categoriafinancierakey"].isna()]["Categoria"].dropna().unique()
        for cat_nueva in faltantes_cat:
            if str(cat_nueva).strip() != "":
                logger.warning(f"⚠️ Categoría '{cat_nueva}' no existe en BD. Creándola...")
                with engine.begin() as conn:
                    query = text("INSERT INTO dimcategoriafinanciera (categoriafinancierakey, nombrecategoriafinanciera) VALUES (DEFAULT, :nombre) RETURNING categoriafinancierakey")
                    nuevo_id = conn.execute(query, {"nombre": str(cat_nueva).title()}).scalar()
                df_fin.loc[df_fin["Categoria"].str.lower() == str(cat_nueva).lower(), "categoriafinancierakey"] = nuevo_id
                dims["dimcategoriafinanciera"] = pd.read_sql("SELECT * FROM dimcategoriafinanciera", engine)

    # Autocrear otras dimensiones para Hoja 1
    autocrear_dimensiones_faltantes(df_fin, "Cuenta", "cuentakey", "dimcuenta", "nombrecuenta", "cuentakey", dims=dims)
    autocrear_dimensiones_faltantes(df_fin, "Moneda", "monedakey", "dimmoneda", "nombremoneda", "monedakey", "simbolomoneda", "N/A", dims=dims)
    autocrear_dimensiones_faltantes(df_fin, "TipoTransaccion", "tipotransaccionkey", "dimtipotransaccion", "tipotransaccion", "tipotransaccionkey", dims=dims)


    # ==========================================
    # 2. PROCESAR HOJA 3: INVERSIONES
    # ==========================================
    logger.info("📥 Leyendo Hoja 3: 'Operativa fact inversion'...")
    df_inv = pd.read_excel(ruta_excel, sheet_name="Operativa fact inversion")
    
    df_inv = df_inv.rename(columns={
        "Casa de bolsa": "CasaBolsa",
        "Tipo de orden": "TipoOrden",
        "Tipo de transaccion inversion": "TipoTransaccionInversion",
        "Institución": "Institucion",
        "Precio unitario": "PrecioUnitario",
        "Es fraccion (split)": "EsFraccion",
        "Comisión": "Comision"
    })
    
    df_inv = df_inv.dropna(how="all").reset_index(drop=True)
    df_inv = resolver_llaves(df_inv, dims)

    # Autocrear dimensiones para Hoja 3
    autocrear_dimensiones_faltantes(df_inv, "Cuenta", "cuentakey", "dimcuenta", "nombrecuenta", "cuentakey", dims=dims)

    # ==========================================
    # 3. VALIDAR FILAS
    # ==========================================
    errores = []
    filas_ok_fin = []
    filas_ok_inv = []
    
    logger.info("\n📌 Validando FactTransaccionFinanciera...")
    for idx, row in df_fin.iterrows():
        fila = idx + 2
        try:
            filas_ok_fin.append(validar_fila_financiera(row, dims, fila))
        except ValidationError as e:
            errores.append(str(e))
            logger.error(f"   ❌ {e}")
    
    logger.info("\n📌 Validando FactTransaccionInversion...")
    for idx, row in df_inv.iterrows():
        fila = idx + 2
        try:
            filas_ok_inv.append(validar_fila_inversion(row, dims, fila))
        except ValidationError as e:
            errores.append(str(e))
            logger.error(f"   ❌ {e}")
    
    if errores:
        logger.critical(f"🛑 {len(errores)} errores detectados. ABORTANDO ETL.")
        raise ETLAbortError(errores)
    
    logger.info(f"✅ Validación completa: {len(filas_ok_fin)} financieras, {len(filas_ok_inv)} inversiones")
    
    df_fin_out = pd.DataFrame(filas_ok_fin) if filas_ok_fin else pd.DataFrame()
    df_inv_out = pd.DataFrame(filas_ok_inv) if filas_ok_inv else pd.DataFrame()
    
    return df_fin_out, df_inv_out


# ============================================
# FASE 2: CARGAR (dentro de la transacción global)
# ============================================
def cargar_movimientos(conn, df_fin, df_inv):
    if not df_fin.empty:
        df_fin.columns = df_fin.columns.str.lower()
        df_fin['fechakey'] = df_fin['fechakey'].astype(int)
        
        df_existente = pd.read_sql("SELECT fechakey, cuentakey, categoriafinancierakey, monto FROM facttransaccionfinanciera", conn)
        
        if not df_existente.empty:
            df_fin = df_fin.merge(df_existente, on=["fechakey", "cuentakey", "categoriafinancierakey", "monto"], how="left", indicator=True)
            df_fin = df_fin[df_fin["_merge"] == "left_only"].drop(columns=["_merge"])
            
        if not df_fin.empty:
            df_fin.to_sql("facttransaccionfinanciera", conn, if_exists="append", index=False, method="multi", chunksize=1000)
            logger.info(f"   ✅ {len(df_fin)} filas NUEVAS en facttransaccionfinanciera")
        else:
            logger.info("   ℹ️ No hay filas nuevas en facttransaccionfinanciera (todas ya existían)")
    
    if not df_inv.empty:
        df_inv.columns = df_inv.columns.str.lower()
        df_inv['fechakey'] = df_inv['fechakey'].astype(int)
   
        df_existente_inv = pd.read_sql("SELECT fechakey, inversionkey, montoneto FROM facttransaccioninversion", conn)
        if not df_existente_inv.empty:
            df_inv = df_inv.merge(df_existente_inv, on=["fechakey", "inversionkey", "montoneto"], how="left", indicator=True)
            df_inv = df_inv[df_inv["_merge"] == "left_only"].drop(columns=["_merge"])
            
        if not df_inv.empty:
            df_inv.to_sql("facttransaccioninversion", conn, if_exists="append", index=False, method="multi", chunksize=1000)
            logger.info(f"   ✅ {len(df_inv)} filas NUEVAS en facttransaccioninversion")
        else:
            logger.info("   ℹ️ No hay filas nuevas en facttransaccioninversion (todas ya existían)")