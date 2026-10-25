# orquestador.py
import sys
import os
from sqlalchemy import text
from config import engine, logger
from validators import ETLAbortError, ValidationError
from etl_movimientos import preparar_movimientos, cargar_movimientos
from etl_presupuesto import preparar_presupuesto, cargar_presupuesto


def registrar_log(conn, proceso, estado, filas, mensaje=""):
    """Registra la ejecución en etl_log para auditoría."""
    try:
        conn.execute(text("""
            INSERT INTO etl_log (proceso, estado, filascargadas, mensaje)
            VALUES (:proceso, :estado, :filas, :mensaje)
        """), {"proceso": proceso, "estado": estado, "filas": filas, "mensaje": mensaje})
    except Exception as e:
        logger.warning(f"No se pudo registrar en etl_log: {e}")


def main():
    logger.info("╔" + "═" * 68 + "╗")
    logger.info("║" + " " * 15 + "SISTEMA ETL ESTRICTO - FINANZAS" + " " * 22 + "║")
    logger.info("║" + " " * 15 + "MODO: TODO O NADA (ROLLBACK GLOBAL)" + " " * 17 + "║")
    logger.info("╚" + "═" * 68 + "╝")
    
    total_cargado = 0
    
    # ========================================
    # DEFINIR LA RUTA DEL ARCHIVO ÚNICO EXCEL
    # ========================================
    # Usamos "r" antes de las comillas para que Windows no se confunda con las barras invertidas "\"
    ruta_excel = r"C:\Users\zabu\Desktop\ETL\tabla plana\Tabla_operativa_con_datos.xlsx"
    
    if not os.path.exists(ruta_excel):
        logger.critical(f"❌ ARCHIVO NO ENCONTRADO: No existe el archivo en la ruta: {ruta_excel}")
        sys.exit(1)

    try:
        # ========================================
        # FASE 1: PREPARAR TODO (sin tocar BD)
        # ========================================
        logger.info(f"📄 Procesando archivo maestro: {os.path.basename(ruta_excel)}")
        
        # Le pasamos la misma ruta a ambas funciones.
        # Ellas internamente saben qué hoja del Excel deben leer.
        df_fin, df_inv = preparar_movimientos(ruta_excel)
        df_pres = preparar_presupuesto(ruta_excel)
        
        # ========================================
        # FASE 2: CARGAR TODO EN UNA SOLA TRANSACCIÓN
        # ========================================
        logger.info("\n" + "=" * 70)
        logger.info("FASE 2: CARGA EN TRANSACCIÓN GLOBAL")
        logger.info("=" * 70)
        
        with engine.begin() as conn:
            # Cargar Hoja 1 y 3
            cargar_movimientos(conn, df_fin, df_inv)
            # Cargar Hoja 2
            cargar_presupuesto(conn, df_pres)
            
            total_cargado = len(df_fin) + len(df_inv) + len(df_pres)
            registrar_log(conn, "ETL_COMPLETO", "OK", total_cargado, "Carga desde Excel maestro exitosa")
        
        logger.info("\n" + "╔" + "═" * 68 + "╗")
        logger.info("║" + " " * 22 + "✅ ETL COMPLETADO EXITOSAMENTE" + " " * 15 + "║")
        logger.info(f"║ Filas procesadas/cargadas: {total_cargado:<39}║")
        logger.info("╚" + "═" * 68 + "╝")
        
    except ETLAbortError as e:
        logger.critical("\n" + "╔" + "═" * 68 + "╗")
        logger.critical("║" + " " * 18 + "🛑 ETL ABORTADO - ROLLBACK GLOBAL" + " " * 16 + "║")
        logger.critical("╚" + "═" * 68 + "╝")
        logger.critical(f"\nTotal de errores: {len(e.errores)}")
        for err in e.errores:
            logger.critical(f"  • {err}")
        logger.critical("\n❌ NO SE CARGÓ NINGÚN DATO. Corrige los errores y vuelve a intentar.")
        
        try:
            with engine.begin() as conn:
                registrar_log(conn, "ETL_COMPLETO", "ABORTADO", 0, "\n".join(e.errores)[:500])
        except Exception:
            pass
        
        sys.exit(1)
        
    except ValidationError as e:
        logger.critical(f"\n🛑 ERROR DE VALIDACIÓN: {e}")
        logger.critical("❌ NO SE CARGÓ NINGÚN DATO.")
        sys.exit(1)
        
    except Exception as e:
        logger.critical(f"\n🛑 ERROR INESPERADO: {e}")
        logger.critical("❌ ROLLBACK GLOBAL EJECUTADO.")
        sys.exit(1)


if __name__ == "__main__":
    main()