from config import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        r1 = conn.execute(text("SELECT current_database(), current_schema();")).fetchone()
        print(f"✅ BD: {r1[0]}")
        print(f"✅ Esquema: {r1[1]}")
        
        r2 = conn.execute(text("SELECT COUNT(*) FROM dimfecha;")).scalar()
        print(f"✅ dimfecha: {r2} filas")
        
        r3 = conn.execute(text("SELECT COUNT(*) FROM dimcuenta;")).scalar()
        print(f"✅ dimcuenta: {r3} filas")
        
        r4 = conn.execute(text("SELECT COUNT(*) FROM diminversion;")).scalar()
        print(f"✅ diminversion: {r4} filas")
        
        r5 = conn.execute(text("SELECT COUNT(*) FROM dimcategoriafinanciera;")).scalar()
        print(f"✅ dimcategoriafinanciera: {r5} filas")
        
        print("\n🎉 Conexión y dimensiones OK")
except Exception as e:
    print(f"❌ Error: {e}")