#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 GENERADOR DE DATOS DE DEMOSTRACIÓN (SINTÉTICOS, NO REALES)
 SENA - Centro ASTIN · Coordinación de Etapa Productiva
=============================================================================
Crea un archivo "BASE DE DATOS ETAPA PRODUCTIVA_DEMO.csv" con columnas
similares a las de los reportes reales (Ficha, Programa, Nombres, Documentos,
Correos, Teléfonos, Jefes, Estados, Fechas) pero con datos 100 % ficticios,
para probar el Anonimizador Universal de forma segura.

Uso:
    python generar_datos_demo.py
=============================================================================
"""

import os

import numpy as np
import pandas as pd

NOMBRES = [
    "María José", "Andrés Felipe", "Ñusta Pacha", "Julián David", "Ana Lucía",
    "Carlos Alberto", "Pedro Luis", "Rosa Elvira", "Camila Andrea", "Santiago",
    "Valentina", "Sebastián", "Laura Daniela", "Diego Fernando", "Paola Andrea",
    "Esteban", "Gabriela", "Felipe Andrés", "Daniela Sofía", "Mateo",
]
APELLIDO1 = ["García", "Rodríguez", "Muñoz", "Ñañez", "Pérez", "López",
             "Martínez", "González", "Cárdenas", "Ospina"]
APELLIDO2 = ["Cifuentes", "Ortiz", "Mora", "Díaz", "Rojas", "Vargas", None, None]
PROGRAMAS = [
    "Análisis y Desarrollo de Software", "Gestión Administrativa",
    "Contabilidad y Finanzas", "Producción Multimedia",
    "Gestión Logística", "Mercadeo",
]
MODALIDADES = ["Virtual", "Presencial", "Bimodal"]
ESTADOS = ["En formación", "Certificado", "En proceso de certificación",
           "Cancelado", None]
JEFES = ["Lina Torres", "Óscar Peña", "Martha Cepeda", "Ricardo Andrade",
         "Sofía Beltrán", "Jaime Cuéllar"]


def main() -> int:
    rng = np.random.default_rng(2026)
    n = 60
    docs = [int(rng.integers(1000000000, 1999999999)) for _ in range(n)]
    docs[5] = docs[0]   # duplicado: prueba de consistencia de cruces
    docs[8] = docs[2]

    datos = {
        "FICHA": [int(rng.integers(2500000, 2900000)) for _ in range(n)],
        "PROGRAMA_FORMACION": rng.choice(PROGRAMAS, n),
        "MODALIDAD": rng.choice(MODALIDADES, n),
        "ESTADO_ETAPA": rng.choice(ESTADOS, n),
        "FECHA_INICIO_ETAPA": pd.date_range("2025-01-15", periods=n, freq="5D").strftime("%d/%m/%Y"),
        "FECHA_FIN_ETAPA": pd.date_range("2025-07-15", periods=n, freq="5D").strftime("%d/%m/%Y"),
        "NOMBRE_APRENDIZ": rng.choice(NOMBRES, n),
        "PRIMER_APELLIDO": rng.choice(APELLIDO1, n),
        "SEGUNDO_APELLIDO": rng.choice(APELLIDO2, n),
        "TIPO_DOCUMENTO": rng.choice(["CC", "TI", "CE"], n),
        "NUMERO_DOCUMENTO": docs,
        "CORREO_ELECTRONICO": [f"aprendiz{i}@misena.edu.co" for i in range(n)],
        "TELEFONO_CELULAR": [
            f"3{int(rng.integers(100000000, 399999999))}" for _ in range(n)
        ],
        "JEFE_INMEDIATO": rng.choice(JEFES, n),
        "CORREO_JEFE": [f"jefe{rng.integers(1, 9)}@sena.edu.co" for _ in range(n)],
        "DIRECCION_RESIDENCIA": [
            f"Cra {int(rng.integers(1, 90))} # {int(rng.integers(1, 99))}-{int(rng.integers(1, 90))}"
            f" Cali" for _ in range(n)
        ],
    }
    df = pd.DataFrame(datos)
    # Nulos deliberados
    df.loc[[3, 17, 29], "TELEFONO_CELULAR"] = np.nan
    df.loc[[7, 21], "SEGUNDO_APELLIDO"] = np.nan
    df.loc[[12, 33], "CORREO_ELECTRONICO"] = np.nan

    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "BASE DE DATOS ETAPA PRODUCTIVA_DEMO.csv")
    # Separador ';' a propósito: demuestra la auto-detección de separadores.
    df.to_csv(ruta, index=False, encoding="utf-8-sig", sep=";")
    print(f"[OK] Archivo de demostración generado ({n} filas x {df.shape[1]} columnas):")
    print(f"     {ruta}")
    print()
    print("Pruebe el flujo completo:")
    print("  1. python app_anonimizador_universal.py            (abre la GUI)")
    print("  2. python app_anonimizador_universal.py cifrar \"BASE DE DATOS ETAPA PRODUCTIVA_DEMO.csv\" --si")
    print("  3. python app_anonimizador_universal.py rehidratar \"BASE DE DATOS ETAPA PRODUCTIVA_DEMO_cifrado.xlsx\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
