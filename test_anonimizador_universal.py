# -*- coding: utf-8 -*-
"""
=============================================================================
 PRUEBAS UNITARIAS · SISTEMA UNIVERSAL DE ANONIMIZACIÓN Y REHIDRATACIÓN
 Demostración matemática de biyectividad: f_K^-1(f_K(x)) = x  para todo x
=============================================================================
Ejecución:
    python -m unittest test_anonimizador_universal -v
    (o) python test_anonimizador_universal.py
=============================================================================
"""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app_anonimizador_universal as app  # noqa: E402

# ---------------------------------------------------------------------------
# Datos sintéticos de prueba (simulan la base real de Etapa Productiva)
# ---------------------------------------------------------------------------
COLUMNAS_PII = [
    "NOMBRE_APRENDIZ", "PRIMER_APELLIDO", "SEGUNDO_APELLIDO",
    "TIPO_DOCUMENTO", "NUMERO_DOCUMENTO", "CORREO_ELECTRONICO",
    "TELEFONO_CELULAR", "JEFE_INMEDIATO", "CORREO_JEFE",
]
COLUMNAS_NO_PII = [
    "FICHA", "PROGRAMA_FORMACION", "MODALIDAD", "ESTADO_ETAPA",
    "FECHA_INICIO", "FECHA_FIN",
]


def crear_df_prueba(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(2026)
    nombres = ["María José", "Andrés Felipe", "Ñusta Pacha", "Julián David",
               "Ana Lucía", "Carlos Alberto", "Pedro Luis", "Rosa Elvira"]
    apellido1 = ["García", "Rodríguez", "Muñoz", "Ñañez", "Pérez", "López"]
    apellido2 = ["Cifuentes", "Ortiz", None, "Mora", None, "Díaz"]
    programas = ["ADSI", "Gestión Administrativa", "Contabilidad", "Multimedia"]
    estados = ["En formación", "Certificado", "En proceso de certificación", None]
    jefes = ["Lina Torres", "Óscar Peña", "Martha Cepeda"]

    datos = {
        "FICHA": [int(rng.integers(2500000, 2900000)) for _ in range(n)],
        "PROGRAMA_FORMACION": rng.choice(programas, n),
        "MODALIDAD": rng.choice(["Virtual", "Presencial", "Bimodal"], n),
        "ESTADO_ETAPA": rng.choice(estados, n),
        "FECHA_INICIO": pd.date_range("2025-01-01", periods=n, freq="7D").strftime("%Y-%m-%d"),
        "FECHA_FIN": pd.date_range("2025-04-01", periods=n, freq="7D").strftime("%Y-%m-%d"),
        "NOMBRE_APRENDIZ": rng.choice(nombres, n),
        "PRIMER_APELLIDO": rng.choice(apellido1, n),
        "SEGUNDO_APELLIDO": rng.choice(apellido2, n),
        "TIPO_DOCUMENTO": rng.choice(["CC", "TI", "CE"], n),
        "NUMERO_DOCUMENTO": [int(rng.integers(1000000000, 1999999999)) for _ in range(n)],
        "CORREO_ELECTRONICO": [
            f"aprendiz{i}@misena.edu.co" for i in range(n)
        ],
        "TELEFONO_CELULAR": [
            f"3{int(rng.integers(100000000, 399999999))}" for _ in range(n)
        ],
        "JEFE_INMEDIATO": rng.choice(jefes, n),
        "CORREO_JEFE": [
            f"jefe{rng.integers(1, 9)}@sena.edu.co" for _ in range(n)
        ],
    }
    df = pd.DataFrame(datos)
    # Duplicados deliberados (prueba de consistencia de cruces)
    df.loc[3, "NUMERO_DOCUMENTO"] = df.loc[0, "NUMERO_DOCUMENTO"]
    df.loc[5, "NOMBRE_APRENDIZ"] = df.loc[1, "NOMBRE_APRENDIZ"]
    # Nulos deliberados (prueba de preservación de vacíos)
    df.loc[7, "TELEFONO_CELULAR"] = np.nan
    df.loc[9, "SEGUNDO_APELLIDO"] = np.nan
    df.loc[11, "CORREO_ELECTRONICO"] = np.nan
    return df


def comparar_pii(orig: pd.DataFrame, real: pd.DataFrame, columnas):
    """Compara columnas PII valor a valor (incluye tildes, ceros y nulos)."""
    for c in columnas:
        s1 = [app.valor_a_texto(v) for v in orig[c]]
        s2 = [app.valor_a_texto(v) for v in real[c]]
        assert s1 == s2, f"Columna '{c}': valores PII no coinciden.\n  orig={s1[:5]}\n  real={s2[:5]}"
        assert orig[c].isna().equals(real[c].isna()), f"Columna '{c}': máscara de nulos difiere."


def comparar_multiconjunto_pii(orig: pd.DataFrame, real: pd.DataFrame, columnas):
    """Compara como multiconjunto (permite filas reordenadas)."""
    for c in columnas:
        s1 = sorted(app.valor_a_texto(v) for v in orig[c])
        s2 = sorted(app.valor_a_texto(v) for v in real[c])
        assert s1 == s2, f"Columna '{c}': multiconjunto difiere."


# ---------------------------------------------------------------------------
# Casos de prueba
# ---------------------------------------------------------------------------
class TestDeteccionPII(unittest.TestCase):
    """Detección heurística por palabras clave + regex."""

    @classmethod
    def setUpClass(cls):
        cls.df = crear_df_prueba()

    def test_detecta_columnas_pii(self):
        deteccion = app.detectar_columnas_pii(self.df)
        detectadas = {c for c, d in deteccion.items() if d["puntaje"] >= 2}
        for col in COLUMNAS_PII:
            self.assertIn(col, detectadas, f"Debió detectarse PII: {col}")

    def test_no_marca_no_sensibles(self):
        deteccion = app.detectar_columnas_pii(self.df)
        detectadas = {c for c, d in deteccion.items() if d["puntaje"] >= 2}
        for col in COLUMNAS_NO_PII:
            self.assertNotIn(col, detectadas, f"No debió detectarse PII: {col}")

    def test_categorias_correctas(self):
        deteccion = app.detectar_columnas_pii(self.df)
        self.assertEqual(deteccion["NOMBRE_APRENDIZ"]["categoria"], "Nombre")
        self.assertEqual(deteccion["NUMERO_DOCUMENTO"]["categoria"], "Documento")
        self.assertEqual(deteccion["CORREO_ELECTRONICO"]["categoria"], "Contacto")


class TestCifradoDirecto(unittest.TestCase):
    """Núcleo criptográfico: determinismo, cero fuga, unicidad."""

    def setUp(self):
        self.df = crear_df_prueba(25)

    def test_determinismo_tokens_hmac(self):
        """Mismo valor -> mismo token (consistencia de cruces)."""
        key1 = app.Fernet.generate_key().decode()
        key2 = app.Fernet.generate_key().decode()
        cif1, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key1)
        cif2, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key1)
        for c in COLUMNAS_PII:
            self.assertTrue(cif1[c].equals(cif2[c]),
                            f"Tokens no deterministas en columna {c}")

    def test_misma_llave_mismo_token_across_files(self):
        """Con la misma llave maestra, dos archivos distintos producen el mismo
        token para el mismo valor (permite cruces entre archivos cifrados)."""
        key = app.Fernet.generate_key().decode()
        df_a = self.df.iloc[:10]
        df_b = self.df.iloc[5:15]
        cif_a, _ = app.cifrar_columnas(df_a, COLUMNAS_PII, app.MODO_HMAC, key)
        cif_b, _ = app.cifrar_columnas(df_b, COLUMNAS_PII, app.MODO_HMAC, key)
        tokens_a = set(cif_a["NUMERO_DOCUMENTO"].dropna())
        tokens_b = set(cif_b["NUMERO_DOCUMENTO"].dropna())
        comunes = tokens_a & tokens_b
        self.assertGreaterEqual(
            len(comunes), 5,
            "Los documentos compartidos deben producir tokens idénticos.",
        )

    def test_cero_fuga_invariante_i1(self):
        """Ningún valor en claro puede aparecer en las columnas cifradas."""
        key = app.Fernet.generate_key().decode()
        cif, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key)
        planos = {
            app.valor_a_texto(v)
            for c in COLUMNAS_PII
            for v in self.df[c]
            if not app.es_valor_nulo(v)
        }
        tokens = {
            app.valor_a_texto(v)
            for v in cif[COLUMNAS_PII].stack()
            if not app.es_valor_nulo(v)
        }
        self.assertTrue(planos.isdisjoint(tokens),
                        "VIOLACIÓN I1: valores en claro presentes en la salida cifrada.")

    def test_valores_duplicados_mismo_token(self):
        key = app.Fernet.generate_key().decode()
        cif, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key)
        self.assertEqual(
            cif.loc[0, "NUMERO_DOCUMENTO"], cif.loc[3, "NUMERO_DOCUMENTO"],
            "Documentos duplicados deben compartir token (consistencia de cruces).",
        )

    def test_nulos_preservados(self):
        key = app.Fernet.generate_key().decode()
        cif, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key)
        for c in COLUMNAS_PII:
            self.assertTrue(self.df[c].isna().equals(cif[c].isna()),
                            f"Nulos alterados en columna {c}")

    def test_no_pii_intactas(self):
        key = app.Fernet.generate_key().decode()
        cif, _ = app.cifrar_columnas(self.df, COLUMNAS_PII, app.MODO_HMAC, key)
        for c in COLUMNAS_NO_PII:
            self.assertTrue(self.df[c].equals(cif[c]),
                            f"Columna no sensible alterada: {c}")


class TestRoundtripArchivos(unittest.TestCase):
    """Ciclo completo: original -> cifrado (archivos reales) -> rehidratado.

    Demostración matemática: f_K^-1(f_K(x)) = x con 100 % de coincidencia.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.df = crear_df_prueba(40)
        self.ruta_orig = os.path.join(self.tmp.name, "BASE DE DATOS ETAPA PRODUCTIVA.csv")
        self.df.to_csv(self.ruta_orig, index=False, encoding="utf-8-sig")

    def tearDown(self):
        self.tmp.cleanup()

    def _cifrar_y_rehidratar(self, modo=app.MODO_HMAC, formato="xlsx"):
        resumen = app.procesar_cifrado(
            self.ruta_orig, columnas_sel=COLUMNAS_PII, modo=modo,
            dir_salida=self.tmp.name, formato=formato, forzar=False,
        )
        df_real, informe = app.procesar_rehidratacion(
            resumen["ruta_cifrado"], resumen["ruta_llave"],
            dir_salida=self.tmp.name, formato="xlsx", forzar=False,
        )
        return resumen, df_real, informe

    def test_roundtrip_hmac_100_porciento(self):
        resumen, df_real, informe = self._cifrar_y_rehidratar(modo=app.MODO_HMAC)
        self.assertTrue(informe["coincidencia_100"],
                        "La rehidratación debe verificar 100 % de coincidencia.")
        comparar_pii(self.df, df_real, COLUMNAS_PII)
        for c in COLUMNAS_NO_PII:
            pd.testing.assert_series_equal(
                self.df[c].reset_index(drop=True),
                df_real[c].reset_index(drop=True),
                obj=f"columna no sensible {c}",
            )

    def test_roundtrip_fernet_100_porciento(self):
        _, df_real, informe = self._cifrar_y_rehidratar(modo=app.MODO_FERNET)
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(self.df, df_real, COLUMNAS_PII)

    def test_filas_reordenadas_siguen_verificando(self):
        """OpenCode puede reordenar filas; la verificación multiconjunto sigue al 100 %."""
        resumen = app.procesar_cifrado(
            self.ruta_orig, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, formato="xlsx", forzar=False,
        )
        df_cifrado = pd.read_excel(resumen["ruta_cifrado"], sheet_name="Datos_Protegidos")
        df_reordenado = df_cifrado.sample(frac=1.0, random_state=7).reset_index(drop=True)
        ruta_reord = os.path.join(self.tmp.name, "PROCESADO_REORDENADO.xlsx")
        df_reordenado.to_excel(ruta_reord, index=False, sheet_name="Datos_Protegidos")
        df_real, informe = app.procesar_rehidratacion(
            ruta_reord, resumen["ruta_llave"],
            dir_salida=self.tmp.name, formato="xlsx", forzar=False,
        )
        self.assertTrue(informe["coincidencia_100"],
                        "Filas reordenadas deben verificar al 100 %.")
        comparar_multiconjunto_pii(self.df, df_real, COLUMNAS_PII)

    def test_llave_no_expone_texto_claro(self):
        resumen = app.procesar_cifrado(
            self.ruta_orig, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, formato="xlsx", forzar=False,
        )
        with open(resumen["ruta_llave"], "r", encoding="utf-8") as f:
            texto_llave = f.read()
        for valor in ["María José", "misena.edu.co", "García", "Ñusta"]:
            self.assertNotIn(valor, texto_llave,
                             f"El .key expone texto claro: '{valor}'")

    def test_archivos_salida_existen(self):
        resumen, df_real, informe = self._cifrar_y_rehidratar()
        self.assertTrue(os.path.isfile(resumen["ruta_cifrado"]))
        self.assertTrue(os.path.isfile(resumen["ruta_llave"]))
        self.assertTrue(os.path.isfile(informe["ruta_salida"]))

    def test_hoja_datos_protegidos_sin_pii(self):
        resumen = app.procesar_cifrado(
            self.ruta_orig, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, formato="xlsx", forzar=False,
        )
        df_cifrado = pd.read_excel(resumen["ruta_cifrado"], sheet_name="Datos_Protegidos")
        planos = {
            app.valor_a_texto(v)
            for c in COLUMNAS_PII
            for v in self.df[c]
            if not app.es_valor_nulo(v)
        }
        for c in COLUMNAS_PII:
            for v in df_cifrado[c]:
                if not app.es_valor_nulo(v):
                    self.assertNotIn(app.valor_a_texto(v), planos,
                                     f"Fuga detectada en hoja Datos_Protegidos: {v}")

    def test_reutilizacion_llave_maestra(self):
        """Dos cifrados con la misma llave maestra: tokens idénticos para valores
        compartidos (cruces consistentes entre archivos)."""
        df_a = self.df.iloc[:15]
        df_b = self.df.iloc[10:25]
        ruta_a = os.path.join(self.tmp.name, "REPORTE_PE04.csv")
        ruta_b = os.path.join(self.tmp.name, "REPORTE_PE14.csv")
        df_a.to_csv(ruta_a, index=False, encoding="utf-8-sig")
        df_b.to_csv(ruta_b, index=False, encoding="utf-8-sig")
        res_a = app.procesar_cifrado(
            ruta_a, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        res_b = app.procesar_cifrado(
            ruta_b, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, ruta_llave_maestra=res_a["ruta_llave"],
            forzar=False,
        )
        cif_a = pd.read_excel(res_a["ruta_cifrado"], sheet_name="Datos_Protegidos")
        cif_b = pd.read_excel(res_b["ruta_cifrado"], sheet_name="Datos_Protegidos")
        comunes = set(cif_a["NUMERO_DOCUMENTO"]) & set(cif_b["NUMERO_DOCUMENTO"])
        self.assertGreaterEqual(len(comunes), 5)


class TestCLI(unittest.TestCase):
    """Pruebas de extremo a extremo por línea de comandos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.df = crear_df_prueba(20)
        self.ruta_orig = os.path.join(self.tmp.name, "BASE_CLI.csv")
        self.df.to_csv(self.ruta_orig, index=False, encoding="utf-8-sig")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_cifrar_rehidratar(self):
        codigo = app.main(["cifrar", self.ruta_orig, "--si",
                           "--salida", self.tmp.name])
        self.assertEqual(codigo, 0, "cifrar CLI falló")
        ruta_cifrada = os.path.join(self.tmp.name, "BASE_CLI_cifrado.xlsx")
        ruta_llave = os.path.join(self.tmp.name, "BASE_CLI_llave.key")
        self.assertTrue(os.path.isfile(ruta_cifrada))
        self.assertTrue(os.path.isfile(ruta_llave))

        codigo = app.main(["rehidratar", ruta_cifrada, "--llave", ruta_llave,
                           "--salida", self.tmp.name, "--formato", "csv"])
        self.assertEqual(codigo, 0, "rehidratar CLI falló")
        ruta_reh = os.path.join(self.tmp.name, "BASE_CLI_rehidratado.csv")
        self.assertTrue(os.path.isfile(ruta_reh))
        df_real = pd.read_csv(ruta_reh, encoding="utf-8-sig", dtype=str,
                              keep_default_na=False)
        df_real = df_real.replace("", np.nan)
        comparar_multiconjunto_pii(self.df, df_real, COLUMNAS_PII)

    def test_cli_detectar(self):
        codigo = app.main(["detectar", self.ruta_orig])
        self.assertEqual(codigo, 0)

    def test_protege_sobreescritura(self):
        app.main(["cifrar", self.ruta_orig, "--si", "--salida", self.tmp.name])
        with self.assertRaises(FileExistsError):
            app.procesar_cifrado(
                self.ruta_orig, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
                dir_salida=self.tmp.name, forzar=False,
            )


class TestResiliencia(unittest.TestCase):
    """Casos límite del mundo real: codificaciones, ceros a la izquierda,
    columnas vacías, tokens corruptos, columnas renombradas por OpenCode,
    y rendimiento con el volumen real (3.540 registros)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.df = crear_df_prueba(30)

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir_y_roundtrip(self, df, nombre="PRUEBA.csv", **kwargs_csv):
        ruta = os.path.join(self.tmp.name, nombre)
        df.to_csv(ruta, index=False, **kwargs_csv)
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_real, informe = app.procesar_rehidratacion(
            resumen["ruta_cifrado"], resumen["ruta_llave"],
            dir_salida=self.tmp.name, forzar=False,
        )
        return df_real, informe, resumen

    def test_csv_latin1_con_tildes(self):
        """CSV en latin-1 (común en exportes de Excel antiguos) con tildes y ';'."""
        df_real, informe, _ = self._escribir_y_roundtrip(
            self.df, "PRUEBA_LATIN1.csv", encoding="latin-1", sep=";"
        )
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(self.df, df_real, COLUMNAS_PII)

    def test_xlsx_entrada_roundtrip(self):
        """Entrada Excel (no CSV): roundtrip 100 % con tipos nativos restaurados."""
        ruta = os.path.join(self.tmp.name, "BASE_XLSX.xlsx")
        self.df.to_excel(ruta, index=False, sheet_name="Base")
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_real, informe = app.procesar_rehidratacion(
            resumen["ruta_cifrado"], resumen["ruta_llave"],
            dir_salida=self.tmp.name, forzar=False,
        )
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(self.df, df_real, COLUMNAS_PII)
        # El tipo numérico nativo del Excel debe restaurarse
        self.assertEqual(
            str(df_real["NUMERO_DOCUMENTO"].dtype),
            str(self.df["NUMERO_DOCUMENTO"].dtype),
            "El dtype int64 de NUMERO_DOCUMENTO debe restaurarse desde Excel.",
        )

    def test_ceros_a_la_izquierda_documentos(self):
        """Documentos con ceros a la izquierda se preservan exactamente."""
        df = self.df.copy()
        df["NUMERO_DOCUMENTO"] = df["NUMERO_DOCUMENTO"].astype(str).str.zfill(11)
        df_real, informe, _ = self._escribir_y_roundtrip(df, "CEROS.csv")
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(df, df_real, ["NUMERO_DOCUMENTO"])
        self.assertEqual(df_real.loc[0, "NUMERO_DOCUMENTO"], df.loc[0, "NUMERO_DOCUMENTO"])

    def test_columna_pii_toda_nula(self):
        """Una columna PII completamente vacía se conserva vacía."""
        df = self.df.copy()
        df["NOMBRE_ACUDIENTE"] = np.nan
        cols = COLUMNAS_PII + ["NOMBRE_ACUDIENTE"]
        ruta = os.path.join(self.tmp.name, "COLUMNA_NULA.csv")
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=cols, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_real, informe = app.procesar_rehidratacion(
            resumen["ruta_cifrado"], resumen["ruta_llave"],
            dir_salida=self.tmp.name, forzar=False,
        )
        self.assertTrue(informe["coincidencia_100"])
        self.assertTrue(df_real["NOMBRE_ACUDIENTE"].isna().all())

    def test_token_desconocido_advertencia(self):
        """Si OpenCode altera un token, se advierte sin perder el resto."""
        ruta = os.path.join(self.tmp.name, "BASE.csv")
        self.df.to_csv(ruta, index=False, encoding="utf-8-sig")
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_cif = pd.read_excel(resumen["ruta_cifrado"], sheet_name="Datos_Protegidos")
        df_cif.loc[0, "NOMBRE_APRENDIZ"] = "TKN_MODIFICADO_POR_ERROR"
        ruta_mod = os.path.join(self.tmp.name, "PROCESADO_MODIFICADO.xlsx")
        df_cif.to_excel(ruta_mod, index=False, sheet_name="Datos_Protegidos")
        df_real, informe = app.procesar_rehidratacion(
            ruta_mod, resumen["ruta_llave"], dir_salida=self.tmp.name, forzar=False,
        )
        self.assertFalse(informe["coincidencia_100"])
        self.assertGreaterEqual(len(informe["tokens_desconocidos"]), 1)
        self.assertEqual(df_real.loc[0, "NOMBRE_APRENDIZ"], "TKN_MODIFICADO_POR_ERROR")
        self.assertEqual(df_real.loc[1, "NOMBRE_APRENDIZ"], self.df.loc[1, "NOMBRE_APRENDIZ"])

    def test_columna_faltante_advertencia(self):
        """Si OpenCode elimina una columna PII, se advierte y se restaura el resto."""
        ruta = os.path.join(self.tmp.name, "BASE.csv")
        self.df.to_csv(ruta, index=False, encoding="utf-8-sig")
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_cif = pd.read_excel(resumen["ruta_cifrado"], sheet_name="Datos_Protegidos")
        df_cif = df_cif.drop(columns=["NOMBRE_APRENDIZ"])
        ruta_mod = os.path.join(self.tmp.name, "PROCESADO_SIN_COLUMNA.xlsx")
        df_cif.to_excel(ruta_mod, index=False, sheet_name="Datos_Protegidos")
        df_real, informe = app.procesar_rehidratacion(
            ruta_mod, resumen["ruta_llave"], dir_salida=self.tmp.name, forzar=False,
        )
        self.assertIn("NOMBRE_APRENDIZ", informe["columnas_faltantes"])
        self.assertFalse(informe["coincidencia_100"])
        comparar_pii(self.df, df_real,
                     [c for c in COLUMNAS_PII if c != "NOMBRE_APRENDIZ"])

    def test_columnas_renombradas_normalizadas(self):
        """OpenCode puede renombrar columnas (minúsculas, espacios): se rehidratan igual."""
        ruta = os.path.join(self.tmp.name, "BASE.csv")
        self.df.to_csv(ruta, index=False, encoding="utf-8-sig")
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        df_cif = pd.read_excel(resumen["ruta_cifrado"], sheet_name="Datos_Protegidos")
        renombres = {c: c.lower().replace("_", " ") for c in COLUMNAS_PII}
        df_cif = df_cif.rename(columns=renombres)
        ruta_mod = os.path.join(self.tmp.name, "PROCESADO_RENOMBRADO.xlsx")
        df_cif.to_excel(ruta_mod, index=False, sheet_name="Datos_Protegidos")
        df_real, informe = app.procesar_rehidratacion(
            ruta_mod, resumen["ruta_llave"], dir_salida=self.tmp.name, forzar=False,
        )
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(self.df, df_real, COLUMNAS_PII)
        # Los nombres originales de las columnas deben restaurarse (estructura I3)
        self.assertEqual(list(df_real.columns), list(self.df.columns),
                         "El rehidratado debe recuperar los nombres originales de columnas.")

    def test_archivo_bloqueado_mensaje_claro(self):
        """Si el destino está abierto en Excel (bloqueado), el error es claro."""
        import stat
        ruta = os.path.join(self.tmp.name, "BASE.csv")
        self.df.to_csv(ruta, index=False, encoding="utf-8-sig")
        ruta_xlsx, _, _ = app.rutas_salida_cifrado(ruta, self.tmp.name)
        with open(ruta_xlsx, "w", encoding="utf-8") as f:
            f.write("")
        os.chmod(ruta_xlsx, stat.S_IREAD)  # simula archivo bloqueado (solo lectura)
        try:
            with self.assertRaises(PermissionError) as ctx:
                app.procesar_cifrado(
                    ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
                    dir_salida=self.tmp.name, forzar=True,
                )
            self.assertIn("abierto en otro programa", str(ctx.exception))
        finally:
            os.chmod(ruta_xlsx, stat.S_IWRITE)

    def test_rendimiento_3540_registros(self):
        """Volumen real de la base (3.540 registros) en tiempo razonable."""
        n = 3540
        rng = np.random.default_rng(42)
        nombres = [
            f"Aprendiz {i % 1000} {['García', 'Rodríguez', 'Ñañez', 'Pérez', 'López'][i % 5]}"
            for i in range(n)
        ]
        telefonos = [f"3{int(rng.integers(100000000, 399999999))}" for _ in range(n)]
        for i in (10, 500, 2200):
            telefonos[i] = np.nan
        df = pd.DataFrame({
            "FICHA": rng.integers(2500000, 2900000, n),
            "PROGRAMA_FORMACION": np.tile(
                ["ADSI", "Contabilidad", "Multimedia", "Gestión Administrativa"],
                n // 4 + 1)[:n],
            "MODALIDAD": np.tile(["Virtual", "Presencial", "Bimodal"], n // 3 + 1)[:n],
            "ESTADO_ETAPA": np.tile(["En formación", "Certificado", None], n // 3 + 1)[:n],
            "NOMBRE_APRENDIZ": nombres,
            "PRIMER_APELLIDO": np.tile(["García", "Rodríguez", "Ñañez", "Pérez"], n // 4 + 1)[:n],
            "SEGUNDO_APELLIDO": np.tile(["Cifuentes", "Ortiz", None, "Mora"], n // 4 + 1)[:n],
            "TIPO_DOCUMENTO": np.tile(["CC", "TI", "CE"], n // 3 + 1)[:n],
            "NUMERO_DOCUMENTO": rng.integers(1000000000, 1999999999, n),
            "CORREO_ELECTRONICO": [f"a{i}@misena.edu.co" for i in range(n)],
            "TELEFONO_CELULAR": telefonos,
            "JEFE_INMEDIATO": np.tile(["Lina Torres", "Óscar Peña", "Martha Cepeda"],
                                      n // 3 + 1)[:n],
            "CORREO_JEFE": [f"jefe{i % 9}@sena.edu.co" for i in range(n)],
        })
        ruta = os.path.join(self.tmp.name, "BASE_3540.csv")
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
        t0 = time.perf_counter()
        resumen = app.procesar_cifrado(
            ruta, columnas_sel=COLUMNAS_PII, modo=app.MODO_HMAC,
            dir_salida=self.tmp.name, forzar=False,
        )
        t_cifrado = time.perf_counter() - t0
        t0 = time.perf_counter()
        df_real, informe = app.procesar_rehidratacion(
            resumen["ruta_cifrado"], resumen["ruta_llave"],
            dir_salida=self.tmp.name, forzar=False,
        )
        t_reh = time.perf_counter() - t0
        self.assertTrue(informe["coincidencia_100"])
        comparar_pii(df, df_real, COLUMNAS_PII)
        self.assertLess(t_cifrado, 120, f"Cifrado muy lento: {t_cifrado:.1f}s")
        self.assertLess(t_reh, 120, f"Rehidratación muy lenta: {t_reh:.1f}s")
        print(f"\n[i] Rendimiento 3.540 filas: cifrado {t_cifrado:.2f}s, "
              f"rehidratación {t_reh:.2f}s")


class TestCLIExtra(unittest.TestCase):
    """Pruebas CLI adicionales: --todas y auto-detección de la llave."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.df = crear_df_prueba(20)
        self.ruta_orig = os.path.join(self.tmp.name, "BASE_CLI2.csv")
        self.df.to_csv(self.ruta_orig, index=False, encoding="utf-8-sig")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_todas_las_columnas(self):
        """--todas protege todas las columnas y la rehidratación las restituye."""
        codigo = app.main(["cifrar", self.ruta_orig, "--todas", "--si",
                           "--salida", self.tmp.name])
        self.assertEqual(codigo, 0)
        ruta_cifrada = os.path.join(self.tmp.name, "BASE_CLI2_cifrado.xlsx")
        ruta_llave = os.path.join(self.tmp.name, "BASE_CLI2_llave.key")
        df_cif = pd.read_excel(ruta_cifrada, sheet_name="Datos_Protegidos")
        # Cero fuga en TODAS las columnas
        for c in self.df.columns:
            planos = {app.valor_a_texto(v) for v in self.df[c] if not app.es_valor_nulo(v)}
            tokens = {app.valor_a_texto(v) for v in df_cif[c] if not app.es_valor_nulo(v)}
            self.assertTrue(planos.isdisjoint(tokens), f"Fuga en columna {c}")
        codigo = app.main(["rehidratar", ruta_cifrada, "--llave", ruta_llave,
                           "--salida", self.tmp.name, "--formato", "csv"])
        self.assertEqual(codigo, 0)
        df_real = pd.read_csv(os.path.join(self.tmp.name, "BASE_CLI2_rehidratado.csv"),
                              encoding="utf-8-sig", dtype=str, keep_default_na=False)
        df_real = df_real.replace("", np.nan)
        for c in self.df.columns:
            self.assertEqual(
                [app.valor_a_texto(v) for v in self.df[c]],
                [app.valor_a_texto(v) for v in df_real[c]],
                f"Columna {c} no restituida con --todas",
            )

    def test_cli_llave_autodetectada(self):
        """rehidratar sin --llave encuentra automáticamente el *_llave.key."""
        app.main(["cifrar", self.ruta_orig, "--si", "--salida", self.tmp.name])
        codigo = app.main(["rehidratar",
                           os.path.join(self.tmp.name, "BASE_CLI2_cifrado.xlsx"),
                           "--salida", self.tmp.name])
        self.assertEqual(codigo, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp.name, "BASE_CLI2_rehidratado.xlsx")))


class TestGUI(unittest.TestCase):
    """La GUI abre automáticamente el diálogo de selección de archivo."""

    def test_dialogo_automatico_y_deteccion(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("tkinter no disponible en este entorno")
        tmp = tempfile.TemporaryDirectory()
        try:
            df = crear_df_prueba(10)
            ruta = os.path.join(tmp.name, "GUI_TEST.csv")
            df.to_csv(ruta, index=False, encoding="utf-8-sig")
            root = tk.Tk()
            root.withdraw()
            with mock.patch.object(tk.Tk, "iconbitmap", autospec=True) as spy_icono:
                a = app.AppAnonimizador(root)
                try:
                    with mock.patch.object(app.filedialog, "askopenfilename",
                                           return_value=ruta):
                        # El temporizador de inicio abre el diálogo automáticamente
                        deadline = time.time() + 15
                        while a.ruta_archivo is None and time.time() < deadline:
                            root.update()
                            time.sleep(0.02)
                        # La auto-detección corre en segundo plano y puebla las casillas
                        deadline = time.time() + 15
                        while (a.df_preview is None or not a.vars_cols) and time.time() < deadline:
                            root.update()
                            time.sleep(0.02)
                    self.assertEqual(a.var_archivo.get(), ruta,
                                     "El diálogo automático debe registrar la ruta elegida.")
                    self.assertIsNotNone(a.df_preview)
                    self.assertGreater(len(a.vars_cols), 0,
                                       "Deben poblarse las casillas de columnas.")
                    detectadas = sum(1 for v in a.vars_cols.values() if v.get())
                    self.assertGreater(detectadas, 0,
                                       "Las columnas PII detectadas deben quedar marcadas.")
                finally:
                    root.destroy()
            # El ícono personalizado (assets/SOFIABOT.ico) debe aplicarse a la ventana
            self.assertTrue(
                any(any("SOFIABOT" in str(arg) for arg in c.args)
                    for c in spy_icono.call_args_list),
                "Debe aplicarse el ícono assets/SOFIABOT.ico a la ventana principal.",
            )
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
