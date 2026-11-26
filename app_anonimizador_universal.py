#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 SISTEMA UNIVERSAL DE ANONIMIZACIÓN Y REHIDRATACIÓN BIYECTIVA
 SENA - Centro ASTIN · Coordinación de Etapa Productiva
 Versión: 1.0.0
=============================================================================

Herramienta local para proteger datos personales (PII) antes de procesar
archivos tabulares (.csv / .xlsx) en herramientas externas (OpenCode, modelos
en la nube) y restituir el 100 % de la información real al regresar.

INVARIANTES FORMALES GARANTIZADOS
---------------------------------
  I1 (Cero fuga):       Ningún valor PII en texto claro queda en el archivo
                        cifrado exportado.
  I2 (Biyectividad):    f_K^-1(f_K(x)) = x  para todo registro. La
                        rehidratación restituye exactamente el original.
  I3 (Estructura):      Columnas no sensibles (Fichas, Programas, Fechas,
                        Estados, Modalidades) y valores nulos (NaN/None)
                        permanecen intactos en su formato original.

ESQUEMA CRIPTOGRÁFICO
---------------------
  * Modo predeterminado "HMAC_DETERMINISTA_SHA256":
      - Subclave por columna: HMAC-SHA256(clave_maestra, nombre_columna).
      - Token determinista por valor: mismo valor -> mismo token
        (preserva consistencia de cruces / joins entre archivos).
      - Formato preservado ligero: valores numéricos -> token numérico,
        correos -> token con forma de correo (dominio ficticio ".tkn").
      - Mapa inverso token->valor cifrado con Fernet dentro del .key
        (biyectividad estricta garantizada por el mapa).
  * Modo opcional "FERNET_AES256_CBC_HMAC":
      - Cifrado simétrico autenticado por valor (cryptography.fernet.Fernet),
        descifrado directo sin mapa (tokens aleatorios, sin joins).

ENTRADAS / SALIDAS
------------------
  Cifrar    :  [Nombre]_cifrado.xlsx   (hoja "Datos_Protegidos" + "Metadatos")
             [Nombre]_llave.key       (clave Fernet + mapa JSON cifrado)
  Rehidratar:  [Nombre]_rehidratado.xlsx  (texto claro 100 % restituido)

USO
---
  GUI :  python app_anonimizador_universal.py            (sin argumentos)
  CLI :  python app_anonimizador_universal.py cifrar BASE.csv
         python app_anonimizador_universal.py detectar BASE.csv
         python app_anonimizador_universal.py rehidratar BASE_cifrado.xlsx --llave BASE_llave.key

Licencia: uso interno SENA. Protección de datos conforme Ley 1581 de 2012.
=============================================================================
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime
import hashlib
import hmac
import json
import os
import queue
import re
import sys
import threading
import unicodedata

import numpy as np
import pandas as pd
from cryptography.fernet import Fernet, InvalidToken

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
FORMATO_KEY = "ANONIMIZADOR_UNIVERSAL_V1"
HOJA_PRINCIPAL = "Datos_Protegidos"
HOJA_METADATOS = "Metadatos"
HOJA_REHIDRATADA = "Datos_Rehidratados"

MODO_HMAC = "HMAC_DETERMINISTA_SHA256"
MODO_FERNET = "FERNET_AES256_CBC_HMAC"

PREFIJO_TOKEN = "TKN_"
LONGITUD_TOKEN_NUMERICO = 12  # 12 dígitos, primer dígito 1-9 (sin ceros líderes)

# Ícono de la aplicación (carpeta assets junto al programa; opcional)
RUTA_ICONO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "SOFIABOT.ico"
)

# Codificaciones y separadores aceptados para CSV
CODIFICACIONES_CSV = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
SEPARADORES_CSV = [",", ";", "\t", "|"]

# ---------------------------------------------------------------------------
# Detección heurística de PII (palabras clave + expresiones regulares)
# ---------------------------------------------------------------------------
PALABRAS_CLAVE_PII = {
    "Nombre": [
        "nombre", "nombres", "primer nombre", "segundo nombre",
        "primer apellido", "segundo apellido", "apellido", "apellidos",
        "aprendiz", "jefe inmediato", "responsable", "tutor", "instructor",
        "nombres y apellidos", "nombre completo",
    ],
    "Documento": [
        "numero documento", "num documento", "no documento", "n documento",
        "documento", "cedula", "identificacion", "dni", "nit", "pasaporte",
        "tarjeta identidad", "numero identificacion",
    ],
    "Contacto": [
        "correo", "email", "e mail", "telefono", "celular", "movil",
        "direccion", "contacto", "tel fijo",
    ],
}

REGEX_EMAIL = re.compile(r"^[\w\.\-\+\']+@[\w\.\-]+\.\w{2,}$")
REGEX_DNI = re.compile(r"^\d{7,10}$")
REGEX_TELEFONO = re.compile(r"^\+?[\d\s\-\(\)]{7,15}$")

# Nombres de columna que NO deben ser evaluadas por regex de valores
# (evita falsos positivos con Fichas, códigos y fechas).
BLOQUEADOS_REGEX = [
    "ficha", "programa", "modalidad", "estado", "fecha", "codigo", "grupo",
    "centro", "sede", "municipio", "departamento", "competencia", "resultado",
    "juicio", "horas", "version", "periodo", "jornada", "etapa", "año", "mes",
]

# ---------------------------------------------------------------------------
# Utilidades de texto y datos
# ---------------------------------------------------------------------------
def normalizar_nombre_columna(nombre: str) -> str:
    """Normaliza el nombre de una columna: minúsculas, sin tildes, espacios simples."""
    s = str(nombre).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def valor_a_texto(v) -> str:
    """Convierte cualquier valor a texto canónico (sin pérdidas de precisión)."""
    if pd.isna(v):
        return ""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    if isinstance(v, str):
        return v
    return str(v)


def es_valor_nulo(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def hash_canonico(df: pd.DataFrame, columnas) -> str:
    """SHA-256 canónico sobre el multiconjunto de valores de las columnas PII.

    Es independiente del orden de las filas: si OpenCode reordena los datos,
    la verificación sigue dando 100 % de coincidencia.
    """
    h = hashlib.sha256()
    for col in sorted(columnas):
        h.update(col.encode("utf-8"))
        h.update(b"\x1f")
        valores = [
            "\x01NULL\x01" if es_valor_nulo(v) else valor_a_texto(v)
            for v in df[col]
        ]
        h.update("\x1e".join(sorted(valores)).encode("utf-8"))
        h.update(b"\x1c")
    return h.hexdigest()


def detectar_separador(muestra: str) -> str:
    """Detecta el separador de un CSV (Sniffer + conteo de columnas)."""
    try:
        dialect = csv.Sniffer().sniff(muestra, delimiters="".join(SEPARADORES_CSV))
        return dialect.delimiter
    except csv.Error:
        pass
    lineas = [l for l in muestra.splitlines()[:8] if l.strip()]
    if not lineas:
        return ","
    mejor, mejor_n = ",", -1
    for sep in SEPARADORES_CSV:
        conteos = [len(l.split(sep)) for l in lineas]
        n = min(conteos) if conteos else 0
        if n > mejor_n:
            mejor, mejor_n = sep, n
    return mejor


def leer_tabular(ruta: str, columnas_como_texto=None, log=print) -> pd.DataFrame:
    """Lee .csv o .xlsx con manejo defensivo de codificación y separadores.

    Para CSV, si se indican `columnas_como_texto` (las PII), se fuerzan como
    texto para preservar ceros a la izquierda en documentos.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            df = pd.read_excel(ruta, engine="openpyxl", sheet_name=0)
        except Exception as e:
            raise ValueError(
                f"No fue posible leer el archivo Excel '{os.path.basename(ruta)}': {e}"
            ) from e
        log(f"[i] Excel leído: {len(df)} filas x {df.shape[1]} columnas.")
        return df
    if ext == ".xls":
        raise ValueError(
            "El formato .xls antiguo no está soportado. Convierta el archivo "
            "a .xlsx o .csv e intente de nuevo."
        )

    ultimo_error = None
    for enc in CODIFICACIONES_CSV:
        try:
            with open(ruta, "r", encoding=enc, newline="") as fh:
                muestra = fh.read(16384)
            sep = detectar_separador(muestra)
            dtype = {c: str for c in columnas_como_texto} if columnas_como_texto else None
            df = pd.read_csv(ruta, encoding=enc, sep=sep, engine="python", dtype=dtype)
            if df.empty or df.shape[1] < 1:
                raise ValueError("el archivo parece estar vacío")
            log(
                f"[i] CSV leído: {len(df)} filas x {df.shape[1]} columnas "
                f"(codificación '{enc}', separador '{sep}')."
            )
            return df
        except UnicodeDecodeError as e:
            ultimo_error = e
            continue
        except Exception as e:
            ultimo_error = e
            continue
    raise ValueError(
        f"No fue posible leer el CSV '{os.path.basename(ruta)}' con ninguna "
        f"codificación soportada. Último error: {ultimo_error}"
    )


# ---------------------------------------------------------------------------
# Detección de columnas PII
# ---------------------------------------------------------------------------
def detectar_columnas_pii(df: pd.DataFrame) -> dict:
    """Auto-detecta columnas PII por heurística (palabras clave + regex).

    Retorna {columna: {"categoria": str, "motivos": [str], "puntaje": int}}.
    """
    deteccion = {}
    for col in df.columns:
        nombre_norm = normalizar_nombre_columna(col)
        categoria, motivos, puntaje = None, [], 0

        for cat, palabras in PALABRAS_CLAVE_PII.items():
            for kw in palabras:
                if nombre_norm == kw:
                    categoria = cat
                    puntaje = max(puntaje, 3)
                    motivos.append(f"el nombre coincide con '{kw}'")
                elif kw in nombre_norm:
                    categoria = categoria or cat
                    puntaje = max(puntaje, 2)
                    motivos.append(f"el nombre contiene '{kw}'")

        nombre_bloqueado = any(b in nombre_norm for b in BLOQUEADOS_REGEX)
        if not nombre_bloqueado:
            valores = [
                valor_a_texto(v)
                for v in df[col].dropna().head(300)
                if valor_a_texto(v) != ""
            ]
            if valores:
                n = len(valores)
                n_email = sum(1 for v in valores if REGEX_EMAIL.fullmatch(v))
                n_dni = sum(1 for v in valores if REGEX_DNI.fullmatch(v))
                n_tel = sum(1 for v in valores if REGEX_TELEFONO.fullmatch(v))
                if n_email / n >= 0.4:
                    categoria = categoria or "Contacto"
                    puntaje = max(puntaje, 3)
                    motivos.append(f"{n_email}/{n} valores con formato de correo")
                if n_dni / n >= 0.5:
                    categoria = categoria or "Documento"
                    puntaje = max(puntaje, 2)
                    motivos.append(f"{n_dni}/{n} valores numéricos de 7-10 dígitos")
                if n_tel / n >= 0.5 and n_dni / n < 0.5:
                    categoria = categoria or "Contacto"
                    puntaje = max(puntaje, 2)
                    motivos.append(f"{n_tel}/{n} valores con formato de teléfono")

        if puntaje >= 2:
            deteccion[str(col)] = {
                "categoria": categoria or "Sin clasificar",
                "motivos": motivos,
                "puntaje": puntaje,
            }
    return deteccion


# ---------------------------------------------------------------------------
# Núcleo criptográfico
# ---------------------------------------------------------------------------
def derivar_subclave(clave_maestra: bytes, contexto: str) -> bytes:
    """Subclave por columna: HMAC-SHA256(clave_maestra, 'subclave' + contexto)."""
    return hmac.new(
        clave_maestra, b"subclave\x00" + contexto.encode("utf-8"), hashlib.sha256
    ).digest()


def clasificar_formato(texto: str) -> str:
    """Decide la forma del token para preservar ligeramente el formato."""
    if re.fullmatch(r"\d{4,}", texto):
        return "numerico"
    if REGEX_EMAIL.fullmatch(texto):
        return "correo"
    return "generico"


def dar_forma_token(digest: bytes, formato: str) -> str:
    """Convierte un digest HMAC en un token con la forma solicitada."""
    if formato == "numerico":
        digitos = [str(digest[0] % 9 + 1)]
        digitos += [str(digest[i] % 10) for i in range(1, LONGITUD_TOKEN_NUMERICO)]
        return "".join(digitos)
    if formato == "correo":
        local = digest[:6].hex()
        dominio = digest[6:10].hex()
        return f"{local}@d{dominio}.tkn"  # dominio ficticio: no filtra el real
    return PREFIJO_TOKEN + base64.urlsafe_b64encode(digest[:16]).decode("ascii").rstrip("=")


def token_hmac(subclave: bytes, texto: str, formato: str,
               planos_globales: set, tokens_usados: set) -> str:
    """Token determinista HMAC-SHA256 con garantías de unicidad y cero fuga.

    I1: el token nunca coincide con ningún valor en texto claro del archivo.
    Unicidad: si hay colisión, se reintenta con contador (determinista).
    """
    base = texto.encode("utf-8")
    contador = 0
    while True:
        if contador == 0:
            digest = hmac.new(subclave, base, hashlib.sha256).digest()
        else:
            digest = hmac.new(
                subclave, base + contador.to_bytes(4, "big"), hashlib.sha256
            ).digest()
        token = dar_forma_token(digest, formato)
        if token not in tokens_usados and token != texto and token not in planos_globales:
            tokens_usados.add(token)
            return token
        contador += 1


def cifrar_columnas(df: pd.DataFrame, columnas, modo: str,
                    fernet_key: str, log=print):
    """Cifra las columnas seleccionadas. Retorna (df_cifrado, mapa_plano).

    df_cifrado : copia del DataFrame con las columnas PII tokenizadas.
    mapa_plano : {columna: {token: valor_original}} para rehidratación.
    """
    clave_maestra = base64.urlsafe_b64decode(fernet_key.encode("ascii"))
    fernet = Fernet(fernet_key)
    df_cifrado = df.copy()
    mapa_plano = {}

    # Conjunto de TODOS los valores en texto claro del archivo (Invariante I1)
    planos_globales = set()
    for col in df.columns:
        for v in df[col]:
            t = valor_a_texto(v)
            if t != "":
                planos_globales.add(t)

    for col in columnas:
        if col not in df.columns:
            raise ValueError(f"La columna '{col}' no existe en el archivo.")
        subclave = derivar_subclave(clave_maestra, col)
        df_cifrado[col] = df_cifrado[col].astype(object)
        cache = {}
        tokens_usados = set()
        mapa = {}
        total = len(df)
        for idx, v in df[col].items():
            if es_valor_nulo(v):
                continue
            texto = valor_a_texto(v)
            if texto in cache:
                token = cache[texto]
            else:
                if modo == MODO_HMAC:
                    formato = clasificar_formato(texto)
                    token = token_hmac(subclave, texto, formato,
                                       planos_globales, tokens_usados)
                else:  # MODO_FERNET
                    token = fernet.encrypt(texto.encode("utf-8")).decode("ascii")
                    tokens_usados.add(token)
                cache[texto] = token
                mapa[token] = texto
            df_cifrado.at[idx, col] = token
            if (idx + 1) % max(total // 10, 1) == 0:
                log(f"    ... cifrada columna '{col}': {idx + 1}/{total} filas")
        mapa_plano[col] = mapa
        log(f"[OK] Columna '{col}' cifrada: {len(mapa)} valores únicos tokenizados.")
    return df_cifrado, mapa_plano


# ---------------------------------------------------------------------------
# Archivo de llave (.key): clave Fernet + mapa JSON cifrado + metadatos
# ---------------------------------------------------------------------------
def construir_llave(ruta_origen: str, df: pd.DataFrame, columnas,
                    modo: str, fernet_key: str, mapa_plano: dict,
                    sha_origen: str, deteccion: dict,
                    llave_reutilizada_de=None) -> dict:
    """Construye el diccionario de metadatos criptográficos (.key)."""
    fernet = Fernet(fernet_key)
    mapa_cifrado = fernet.encrypt(
        json.dumps({"columnas": mapa_plano}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    return {
        "formato": FORMATO_KEY,
        "version_software": __version__,
        "archivo_origen": os.path.basename(ruta_origen),
        "fecha_cifrado": datetime.datetime.now().isoformat(timespec="seconds"),
        "modo": modo,
        "columnas_pii": list(columnas),
        "detalle_columnas": {c: deteccion.get(c, {}) for c in columnas},
        "dtypes_pii": {c: str(df[c].dtype) for c in columnas},
        "fernet_key": fernet_key,
        "mapa_cifrado": mapa_cifrado,
        "sha256_pii_origen": sha_origen,
        "filas_originales": int(len(df)),
        "columnas_originales": [str(c) for c in df.columns],
        "columnas_no_pii": [str(c) for c in df.columns if c not in columnas],
        "llave_reutilizada_de": llave_reutilizada_de,
    }


def guardar_llave(llave: dict, ruta: str, log=print):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(llave, f, ensure_ascii=False, indent=2)
    log(f"[OK] Llave criptográfica guardada: {os.path.basename(ruta)}")


def cargar_llave(ruta: str, log=print) -> dict:
    """Carga y valida el .key; descifra el mapa inverso de columnas."""
    with open(ruta, "r", encoding="utf-8") as f:
        llave = json.load(f)
    if llave.get("formato") != FORMATO_KEY:
        raise ValueError(
            f"'{os.path.basename(ruta)}' no es una llave válida del sistema "
            f"(formato esperado: {FORMATO_KEY})."
        )
    try:
        fernet = Fernet(llave["fernet_key"])
    except Exception as e:
        raise ValueError(f"La llave Fernet del archivo no es válida: {e}") from e
    mapa_plano = {}
    if llave.get("mapa_cifrado"):
        try:
            datos = json.loads(
                fernet.decrypt(llave["mapa_cifrado"].encode("ascii")).decode("utf-8")
            )
            mapa_plano = datos.get("columnas", {})
        except Exception as e:
            raise ValueError(f"No se pudo descifrar el mapa de columnas: {e}") from e
    llave["_fernet"] = fernet
    llave["_mapa_plano"] = mapa_plano
    log(
        f"[i] Llave cargada: modo {llave.get('modo')}, "
        f"{len(llave.get('columnas_pii', []))} columnas PII, "
        f"archivo origen '{llave.get('archivo_origen')}'."
    )
    return llave


# ---------------------------------------------------------------------------
# Rehidratación (descifrado inverso)
# ---------------------------------------------------------------------------
def encontrar_columna(df: pd.DataFrame, col_llave: str):
    """Ubica la columna en el archivo procesado (nombre exacto o normalizado)."""
    if col_llave in df.columns:
        return col_llave
    norm_llave = normalizar_nombre_columna(col_llave)
    candidatas = [c for c in df.columns if normalizar_nombre_columna(c) == norm_llave]
    if len(candidatas) == 1:
        return candidatas[0]
    return None


def rehidratar_dataframe(df_proc: pd.DataFrame, llave: dict, log=print):
    """Restituye los valores reales de las columnas PII. Retorna (df_real, informe)."""
    modo = llave.get("modo", MODO_HMAC)
    columnas_pii = llave.get("columnas_pii", [])
    dtypes_pii = llave.get("dtypes_pii", {})
    mapa_plano = llave.get("_mapa_plano", {})
    fernet = llave.get("_fernet")

    df_real = df_proc.copy()
    informe = {
        "filas": int(len(df_real)),
        "filas_originales": int(llave.get("filas_originales", 0)),
        "tokens_rehidratados": 0,
        "tokens_desconocidos": [],
        "columnas_faltantes": [],
        "nulos_preservados": 0,
        "dtype_no_restaurado": [],
    }

    for col in columnas_pii:
        col_df = encontrar_columna(df_real, col)
        if col_df is None:
            informe["columnas_faltantes"].append(col)
            log(f"[!] ADVERTENCIA: la columna PII '{col}' no está en el archivo procesado.")
            continue
        # Restaurar el nombre original de la columna si OpenCode la renombró
        # (preservación de estructura: el rehidratado refleja el esquema original).
        if col_df != col and col not in df_real.columns:
            df_real = df_real.rename(columns={col_df: col})
            col_df = col
        mapa = mapa_plano.get(col, {})
        df_real[col_df] = df_real[col_df].astype(object)

        for idx, v in df_real[col_df].items():
            if es_valor_nulo(v):
                informe["nulos_preservados"] += 1
                continue
            token = valor_a_texto(v)
            if modo == MODO_HMAC:
                if token in mapa:
                    df_real.at[idx, col_df] = mapa[token]
                    informe["tokens_rehidratados"] += 1
                else:
                    if len(informe["tokens_desconocidos"]) < 20:
                        informe["tokens_desconocidos"].append(
                            {"columna": col, "fila": int(idx) + 2, "token": token[:60]}
                        )
            else:  # MODO_FERNET
                try:
                    texto = fernet.decrypt(token.encode("ascii")).decode("utf-8")
                    df_real.at[idx, col_df] = texto
                    informe["tokens_rehidratados"] += 1
                except Exception:
                    if len(informe["tokens_desconocidos"]) < 20:
                        informe["tokens_desconocidos"].append(
                            {"columna": col, "fila": int(idx) + 2, "token": token[:60]}
                        )

        # Restaurar el tipo de dato original de la columna
        dtype_orig = dtypes_pii.get(col)
        if dtype_orig and dtype_orig not in ("object", "str"):
            try:
                df_real[col_df] = df_real[col_df].astype(dtype_orig)
            except Exception:
                informe["dtype_no_restaurado"].append(col)
                log(f"[!] No se pudo restaurar el tipo '{dtype_orig}' en '{col}'; "
                    f"se conserva como texto.")
        log(f"[OK] Columna '{col}' rehidratada ({len(mapa)} valores mapeados).")

    # Verificación de integridad (demostración matemática de biyectividad)
    presentes = [c for c in columnas_pii if encontrar_columna(df_real, c) is not None]
    if presentes:
        sha_actual = hash_canonico(df_real, presentes)
        sha_origen = llave.get("sha256_pii_origen", "")
        informe["sha256_rehidratado"] = sha_actual
        informe["sha256_origen"] = sha_origen
        informe["coincidencia_100"] = bool(
            sha_actual == sha_origen and not informe["columnas_faltantes"]
        )
    else:
        informe["coincidencia_100"] = False
    return df_real, informe


# ---------------------------------------------------------------------------
# Escritura de resultados Excel/CSV
# ---------------------------------------------------------------------------
def escribir_excel(df: pd.DataFrame, ruta: str, hoja: str,
                   metadatos=None, log=print):
    """Escribe el DataFrame en Excel (openpyxl) con anchos ajustados y pane congelado."""
    try:
        from openpyxl.utils import get_column_letter
    except ImportError:
        get_column_letter = None
    try:
        with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=hoja, index=False)
            if metadatos:
                df_meta = pd.DataFrame(
                    [(str(k), str(v)) for k, v in metadatos.items()],
                    columns=["Campo", "Valor"],
                )
                df_meta.to_excel(writer, sheet_name=HOJA_METADATOS, index=False)
            ws = writer.sheets[hoja]
            ws.freeze_panes = "A2"
            if get_column_letter:
                for i, col in enumerate(df.columns, 1):
                    try:
                        longitudes = [len(str(col))]
                        longitudes += [len(str(s)) for s in df[col].astype(str).head(500)]
                        ancho = max(longitudes) + 2
                    except Exception:
                        ancho = len(str(col)) + 2
                    ws.column_dimensions[get_column_letter(i)].width = min(ancho, 50)
    except PermissionError as e:
        raise PermissionError(
            f"No se pudo escribir '{os.path.basename(ruta)}': el archivo está "
            f"abierto en otro programa (p. ej. Excel). Ciérrelo e intente de nuevo."
        ) from e
    log(f"[OK] Archivo generado: {os.path.basename(ruta)}")


def escribir_csv(df: pd.DataFrame, ruta: str, log=print):
    try:
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
    except PermissionError as e:
        raise PermissionError(
            f"No se pudo escribir '{os.path.basename(ruta)}': el archivo está "
            f"abierto en otro programa. Ciérrelo e intente de nuevo."
        ) from e
    log(f"[OK] Archivo CSV generado: {os.path.basename(ruta)}")


# ---------------------------------------------------------------------------
# Orquestación: cifrado completo
# ---------------------------------------------------------------------------
def rutas_salida_cifrado(ruta_entrada: str, dir_salida=None):
    """Rutas de salida del cifrado: (xlsx_cifrado, llave, csv_cifrado_opcional)."""
    base = os.path.basename(ruta_entrada)
    tallo, _ = os.path.splitext(base)
    dir_salida = dir_salida or os.path.dirname(os.path.abspath(ruta_entrada))
    return (
        os.path.join(dir_salida, f"{tallo}_cifrado.xlsx"),
        os.path.join(dir_salida, f"{tallo}_llave.key"),
        os.path.join(dir_salida, f"{tallo}_cifrado.csv"),
    )


def rutas_salida_rehidratacion(ruta_procesado: str, dir_salida=None):
    tallo, _ = os.path.splitext(os.path.basename(ruta_procesado))
    if tallo.endswith("_cifrado"):
        tallo = tallo[: -len("_cifrado")]
    dir_salida = dir_salida or os.path.dirname(os.path.abspath(ruta_procesado))
    return (
        os.path.join(dir_salida, f"{tallo}_rehidratado.xlsx"),
        os.path.join(dir_salida, f"{tallo}_rehidratado.csv"),
    )


def verificar_no_sobrescribir(rutas, forzar: bool):
    existentes = [r for r in rutas if r and os.path.exists(r)]
    if existentes and not forzar:
        raise FileExistsError(
            "Ya existen archivos de salida:\n  "
            + "\n  ".join(existentes)
            + "\nUse --forzar para sobrescribirlos (¡cuidado: podría perder "
              "una llave anterior!)."
        )


def procesar_cifrado(ruta_entrada: str, columnas_sel=None, modo: str = MODO_HMAC,
                     dir_salida=None, ruta_llave_maestra=None, formato: str = "xlsx",
                     forzar: bool = False, log=print):
    """Flujo completo de cifrado/anomimización. Retorna dict con rutas y resumen."""
    if not os.path.isfile(ruta_entrada):
        raise FileNotFoundError(f"No existe el archivo: {ruta_entrada}")

    log("=" * 72)
    log("FASE 1 · CIFRADO / ANONIMIZACIÓN LOCAL")
    log(f"  Archivo de entrada : {os.path.basename(ruta_entrada)}")
    log(f"  Modo criptográfico  : {modo}")

    # 1) Lectura preliminar y auto-detección de columnas PII
    df_preview = leer_tabular(ruta_entrada, log=log)
    deteccion = detectar_columnas_pii(df_preview)

    if columnas_sel is None:
        columnas_sel = sorted(
            (c for c, d in deteccion.items() if d["puntaje"] >= 2),
            key=lambda c: list(df_preview.columns).index(c),
        )
        log("[i] Columnas PII auto-detectadas:")
        for c in columnas_sel:
            d = deteccion[c]
            log(f"    * {c}  ->  {d['categoria']}  ({'; '.join(d['motivos'])})")
    else:
        columnas_sel = [str(c) for c in columnas_sel]
        faltantes = [c for c in columnas_sel if c not in df_preview.columns]
        if faltantes:
            raise ValueError(
                "Columnas indicadas no existen en el archivo: "
                + ", ".join(faltantes)
            )

    if not columnas_sel:
        raise ValueError(
            "No se seleccionó ninguna columna PII. Use --todas, --columnas o "
            "revise la auto-detección."
        )

    # 2) Relectura con columnas PII como texto (CSV: preserva ceros a la izquierda)
    ext = os.path.splitext(ruta_entrada)[1].lower()
    if ext in (".csv",) and columnas_sel:
        df = leer_tabular(ruta_entrada, columnas_como_texto=columnas_sel, log=log)
    else:
        df = df_preview

    # 3) Clave Fernet (nueva o reutilizada para cruces consistentes entre archivos)
    llave_reutilizada_de = None
    if ruta_llave_maestra:
        llave_previa = cargar_llave(ruta_llave_maestra, log=log)
        fernet_key = llave_previa["fernet_key"]
        if llave_previa.get("modo") and llave_previa["modo"] != modo:
            log("[!] La llave maestra usa otro modo; se respeta el modo de la llave.")
            modo = llave_previa["modo"]
        llave_reutilizada_de = os.path.basename(ruta_llave_maestra)
        log(f"[i] Reutilizando clave de: {llave_reutilizada_de} (cruces consistentes).")
    else:
        fernet_key = Fernet.generate_key().decode("ascii")
        log("[i] Nueva clave Fernet AES-256 generada.")

    # 4) Cifrado biyectivo de las columnas seleccionadas
    log("[i] Cifrando columnas seleccionadas (Invariantes I1 / I2)...")
    df_cifrado, mapa_plano = cifrar_columnas(df, columnas_sel, modo, fernet_key, log=log)

    # 5) Verificación del Invariante I1 (cero fuga) antes de exportar
    planos = {valor_a_texto(v) for c in columnas_sel for v in df[c] if not es_valor_nulo(v)}
    fugas = planos & {valor_a_texto(v) for v in df_cifrado[columnas_sel].stack()}
    if fugas:
        raise RuntimeError(
            f"VIOLACIÓN DEL INVARIANTE I1: valores en claro detectados en la "
            f"salida: {list(fugas)[:5]}"
        )
    log("[OK] Invariante I1 verificado: cero fuga de PII en el archivo cifrado.")

    # 6) Metadatos, llave y archivos de salida
    sha_origen = hash_canonico(df, columnas_sel)
    llave = construir_llave(ruta_entrada, df, columnas_sel, modo, fernet_key,
                            mapa_plano, sha_origen, deteccion, llave_reutilizada_de)

    ruta_xlsx, ruta_llave, ruta_csv = rutas_salida_cifrado(ruta_entrada, dir_salida)
    verificar_no_sobrescribir([ruta_xlsx, ruta_llave] + ([ruta_csv] if formato in ("csv", "ambos") else []), forzar)

    metadatos = {
        "Sistema": "Anonimizador Universal Biyectivo SENA-ASTIN",
        "Archivo original": llave["archivo_origen"],
        "Fecha de cifrado": llave["fecha_cifrado"],
        "Modo criptográfico": modo,
        "Columnas protegidas": ", ".join(columnas_sel),
        "Filas": int(len(df)),
        "Columnas totales": int(df.shape[1]),
        "SHA-256 de columnas PII (verificación)": sha_origen,
        "Llave requerida para rehidratar": os.path.basename(ruta_llave),
    }
    escribir_excel(df_cifrado, ruta_xlsx, HOJA_PRINCIPAL, metadatos=metadatos, log=log)
    if formato in ("csv", "ambos"):
        escribir_csv(df_cifrado, ruta_csv, log=log)
    guardar_llave(llave, ruta_llave, log=log)

    log("-" * 72)
    log("CIFRADO COMPLETADO. Exporte SOLO el archivo cifrado hacia OpenCode.")
    log(f"  Excel cifrado : {ruta_xlsx}")
    log(f"  Llave secreta : {ruta_llave}   (GUARDAR EN LUGAR SEGURO, NO compartir)")
    return {
        "ruta_cifrado": ruta_xlsx,
        "ruta_llave": ruta_llave,
        "ruta_csv": ruta_csv if formato in ("csv", "ambos") else None,
        "columnas": list(columnas_sel),
        "modo": modo,
        "filas": int(len(df)),
        "sha256_pii_origen": sha_origen,
    }


def sugerir_ruta_llave(ruta_procesado: str):
    tallo, _ = os.path.splitext(os.path.basename(ruta_procesado))
    if tallo.endswith("_cifrado"):
        tallo = tallo[: -len("_cifrado")]
    return os.path.join(os.path.dirname(os.path.abspath(ruta_procesado)),
                        f"{tallo}_llave.key")


def procesar_rehidratacion(ruta_procesado: str, ruta_llave: str, dir_salida=None,
                           formato: str = "xlsx", forzar: bool = False, log=print):
    """Flujo completo de rehidratación/descifrado. Retorna (df_real, informe)."""
    if not os.path.isfile(ruta_procesado):
        raise FileNotFoundError(f"No existe el archivo procesado: {ruta_procesado}")
    if not os.path.isfile(ruta_llave):
        raise FileNotFoundError(
            f"No existe la llave: {ruta_llave}. "
            f"Busque el archivo *_llave.key generado en el cifrado."
        )

    log("=" * 72)
    log("FASE 2 · REHIDRATACIÓN / DESCIFRADO LOCAL")
    log(f"  Archivo procesado : {os.path.basename(ruta_procesado)}")
    log(f"  Llave criptográfica: {os.path.basename(ruta_llave)}")

    llave = cargar_llave(ruta_llave, log=log)
    df_proc = leer_tabular(ruta_procesado, log=log)

    df_real, informe = rehidratar_dataframe(df_proc, llave, log=log)

    ruta_xlsx, ruta_csv = rutas_salida_rehidratacion(ruta_procesado, dir_salida)
    verificar_no_sobrescribir([ruta_xlsx] + ([ruta_csv] if formato in ("csv", "ambos") else []), forzar)

    escribir_excel(df_real, ruta_xlsx, HOJA_REHIDRATADA, log=log)
    if formato in ("csv", "ambos"):
        escribir_csv(df_real, ruta_csv, log=log)
    informe["ruta_salida"] = ruta_xlsx
    informe["ruta_csv"] = ruta_csv if formato in ("csv", "ambos") else None

    log("-" * 72)
    if informe.get("coincidencia_100"):
        log("[OK] VERIFICACIÓN MATEMÁTICA: 100 % de coincidencia entre el archivo")
        log("     original y el rehidratado (SHA-256 multiconjunto idéntico).")
        log("     La biyectividad f_K^-1(f_K(x)) = x se cumple para todos los registros.")
    else:
        log("[!] ATENCIÓN: la verificación NO dio 100 % de coincidencia.")
        if informe.get("columnas_faltantes"):
            log(f"     Columnas PII ausentes en el procesado: {informe['columnas_faltantes']}")
        if informe.get("tokens_desconocidos"):
            log(f"     Tokens sin correspondencia en la llave (pueden ser datos nuevos o modificados):")
            for t in informe["tokens_desconocidos"][:5]:
                log(f"       - columna '{t['columna']}', fila {t['fila']}: {t['token']}")
    log(f"  Rehidratado    : {ruta_xlsx}")
    log(f"  Tokens restituidos: {informe.get('tokens_rehidratados', 0)}")
    log(f"  Nulos preservados: {informe.get('nulos_preservados', 0)}")
    return df_real, informe


# ===========================================================================
# INTERFAZ DE LÍNEA DE COMANDOS (CLI)
# ===========================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="app_anonimizador_universal",
        description="Sistema Universal de Anonimización y Rehidratación Biyectiva "
                    "(SENA Centro ASTIN). Sin argumentos abre la interfaz gráfica.",
    )
    p.add_argument("--version", action="version",
                   version=f"app_anonimizador_universal {__version__}")
    sub = p.add_subparsers(dest="comando")

    p_gui = sub.add_parser("gui", help="Abrir la interfaz gráfica (Tkinter).")

    p_cifrar = sub.add_parser(
        "cifrar", help="Cifrar/anomimizar un archivo .csv o .xlsx."
    )
    p_cifrar.add_argument("archivo", help="Ruta del archivo tabular (.csv / .xlsx).")
    p_cifrar.add_argument("--columnas", default=None,
                          help="Columnas a proteger, separadas por coma. "
                               "Por defecto: auto-detección PII.")
    p_cifrar.add_argument("--todas", action="store_true",
                          help="Cifrar TODAS las columnas del archivo.")
    p_cifrar.add_argument("--modo", choices=["hmac", "fernet"], default="hmac",
                          help="hmac = tokenización determinista HMAC-SHA256 "
                               "(recomendado, preserva cruces); "
                               "fernet = Fernet AES-256 aleatorio.")
    p_cifrar.add_argument("--llave-maestra", default=None,
                          help="Reutilizar la clave Fernet de un .key existente "
                               "(cruces consistentes entre archivos).")
    p_cifrar.add_argument("--salida", default=None,
                          help="Directorio de salida (por defecto: junto al archivo).")
    p_cifrar.add_argument("--formato", choices=["xlsx", "csv", "ambos"], default="xlsx",
                          help="Formato del archivo cifrado (por defecto: xlsx).")
    p_cifrar.add_argument("--solo-detectar", action="store_true",
                          help="Solo mostrar las columnas PII detectadas y salir.")
    p_cifrar.add_argument("--forzar", action="store_true",
                          help="Sobrescribir archivos de salida existentes.")
    p_cifrar.add_argument("--si", action="store_true",
                          help="Confirmar automáticamente la selección de columnas.")

    p_reh = sub.add_parser(
        "rehidratar", help="Descifrar/rehidratar un archivo procesado con su llave .key."
    )
    p_reh.add_argument("archivo", help="Archivo procesado (.xlsx / .csv).")
    p_reh.add_argument("--llave", default=None,
                       help="Ruta del archivo _llave.key. Por defecto se busca "
                            "automáticamente junto al archivo.")
    p_reh.add_argument("--salida", default=None, help="Directorio de salida.")
    p_reh.add_argument("--formato", choices=["xlsx", "csv", "ambos"], default="xlsx",
                       help="Formato del archivo rehidratado (por defecto: xlsx).")
    p_reh.add_argument("--forzar", action="store_true",
                       help="Sobrescribir archivos de salida existentes.")

    p_det = sub.add_parser(
        "detectar", help="Mostrar las columnas PII auto-detectadas de un archivo."
    )
    p_det.add_argument("archivo", help="Ruta del archivo tabular.")
    return p


def cmd_detectar(args) -> int:
    df = leer_tabular(args.archivo)
    deteccion = detectar_columnas_pii(df)
    print("=" * 72)
    print(f"COLUMNAS PII AUTO-DETECTADAS · {os.path.basename(args.archivo)}")
    print("=" * 72)
    for col in df.columns:
        d = deteccion.get(str(col))
        if d:
            print(f"  [PII] {col}  ->  {d['categoria']}  ({'; '.join(d['motivos'])})")
        else:
            print(f"  [   ] {col}  (no sensible)")
    return 0


def cmd_cifrar(args) -> int:
    modo = MODO_HMAC if args.modo == "hmac" else MODO_FERNET
    df_preview = leer_tabular(args.archivo)
    deteccion = detectar_columnas_pii(df_preview)

    if args.todas:
        seleccionadas = [str(c) for c in df_preview.columns]
    elif args.columnas:
        seleccionadas = [c.strip() for c in args.columnas.split(",") if c.strip()]
    else:
        seleccionadas = sorted(
            (str(c) for c, d in deteccion.items() if d["puntaje"] >= 2),
            key=lambda c: list(df_preview.columns).index(c),
        )

    if args.solo_detectar:
        return cmd_detectar(args)

    if not seleccionadas:
        print("[!] No se detectaron columnas PII ni se indicaron con --columnas.")
        print("    Use 'detectar' para revisar, o --todas / --columnas.")
        return 1

    print("[i] Columnas a proteger:")
    for c in seleccionadas:
        d = deteccion.get(c)
        detalle = f"  ({d['categoria']}; {'; '.join(d['motivos'])})" if d else "  (indicada manualmente)"
        print(f"    * {c}{detalle}")

    if not args.si and sys.stdin.isatty():
        try:
            r = input("¿Continuar con estas columnas? [S/n]: ").strip().lower()
            if r in ("n", "no"):
                print("Cancelado por el usuario.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("Cancelado.")
            return 0

    resumen = procesar_cifrado(
        args.archivo,
        columnas_sel=seleccionadas,
        modo=modo,
        dir_salida=args.salida,
        ruta_llave_maestra=args.llave_maestra,
        formato=args.formato,
        forzar=args.forzar,
    )
    return 0


def cmd_rehidratar(args) -> int:
    ruta_llave = args.llave or sugerir_ruta_llave(args.archivo)
    if args.llave is None and not os.path.isfile(ruta_llave):
        print(f"[!] No se encontró la llave '{os.path.basename(ruta_llave)}'. "
              f"Indíquela con --llave.")
        return 2
    df_real, informe = procesar_rehidratacion(
        args.archivo, ruta_llave, dir_salida=args.salida,
        formato=args.formato, forzar=args.forzar,
    )
    if informe.get("coincidencia_100"):
        print("[OK] Rehidratación verificada: 100 % de coincidencia con el original.")
        return 0
    print("[!] Rehidratación completada con advertencias (ver detalle arriba).")
    return 3


def main(argv=None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.comando == "gui":
        iniciar_gui()
        return 0
    if args.comando == "cifrar":
        return cmd_cifrar(args)
    if args.comando == "rehidratar":
        return cmd_rehidratar(args)
    if args.comando == "detectar":
        return cmd_detectar(args)
    if args.comando is None:
        try:
            import tkinter  # noqa: F401
            iniciar_gui()
            return 0
        except ImportError:
            print("[i] Tkinter no disponible en este entorno; usando modo CLI.")
            parser.print_help()
            return 0
    parser.print_help()
    return 0


# ===========================================================================
# INTERFAZ GRÁFICA DE USUARIO (Tkinter)
# ===========================================================================
def _tk_disponible() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


if _tk_disponible():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext


    class AppAnonimizador:
        """Ventana principal: pestañas 'Cifrar' y 'Rehidratar' + consola de log."""

        def __init__(self, root: tk.Tk):
            self.root = root
            root.title(
                f"Sistema Universal de Anonimización y Rehidratación Biyectiva  "
                f"(SENA ASTIN · v{__version__})"
            )
            root.geometry("1000x780")
            root.minsize(880, 640)
            # Ícono personalizado de la ventana y de todos sus diálogos.
            # En Windows, el diálogo de selección de archivos y los messagebox
            # heredan el ícono de la ventana principal.
            try:
                if os.path.isfile(RUTA_ICONO):
                    root.iconbitmap(RUTA_ICONO)
            except Exception:
                pass  # el ícono es cosmético; la aplicación debe seguir funcionando

            self.cola_log = queue.Queue()
            self.cola_resultados = queue.Queue()
            self.ruta_archivo = None
            self.df_preview = None
            self.deteccion = {}
            self.vars_cols = {}
            self.trabajando = False
            self.dialogo_abierto = False
            self.ruta_llave_maestra = None
            self.ruta_procesado = None
            self.ruta_llave_reh = None

            self._construir_widgets()
            self.root.after(120, self._drenar_log)
            self._log("Bienvenido. Seleccione un archivo tabular (.csv / .xlsx) para comenzar.")
            # El cuadro de diálogo para ubicar el archivo se abre automáticamente
            # al iniciar la aplicación (y cada vez que entre a la pestaña Cifrar
            # sin tener un archivo seleccionado).
            self.root.after(600, self._abrir_dialogo_si_es_necesario)
            root.lift()
            try:
                root.focus_force()
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Construcción de la interfaz
        # ------------------------------------------------------------------
        def _construir_widgets(self):
            self.estilo = ttk.Style(self.root)
            self.estilo.configure("Accion.TButton",
                                  font=("Segoe UI", 10, "bold"), padding=(12, 7))
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 2))

            self.tab_cifrar = ttk.Frame(self.notebook)
            self.tab_rehidratar = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_cifrar, text="  Cifrar / Anonimizar  ")
            self.notebook.add(self.tab_rehidratar, text="  Rehidratar / Descifrar  ")
            self.notebook.bind("<<NotebookTabChanged>>", self._al_cambiar_tab)

            self._construir_tab_cifrar()
            self._construir_tab_rehidratar()

            frame_log = ttk.LabelFrame(self.root, text="  Consola de registro  ")
            frame_log.pack(fill="both", expand=True, padx=8, pady=(2, 8))
            self.txt_log = scrolledtext.ScrolledText(
                frame_log, height=8, state="disabled", wrap="word",
                font=("Consolas", 9), background="#1e1e1e", foreground="#d4d4d4",
            )
            self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)

        def _construir_tab_cifrar(self):
            f = self.tab_cifrar

            # 1) Selección del archivo de entrada
            f_archivo = ttk.LabelFrame(f, text="  1. Archivo de entrada (.csv / .xlsx)  ")
            f_archivo.pack(fill="x", padx=8, pady=6)
            fila_archivo = ttk.Frame(f_archivo)
            fila_archivo.pack(fill="x", padx=6, pady=(8, 2))
            self.var_archivo = tk.StringVar(value="(ningún archivo seleccionado)")
            self.entry_archivo = ttk.Entry(fila_archivo, textvariable=self.var_archivo,
                                           state="readonly")
            self.entry_archivo.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self.entry_archivo.bind("<Double-Button-1>",
                                    lambda e: self._seleccionar_archivo())
            self.btn_seleccionar = ttk.Button(
                fila_archivo, text="Seleccionar archivo...",
                style="Accion.TButton", command=self._seleccionar_archivo,
            )
            self.btn_seleccionar.pack(side="right")
            ttk.Label(
                f_archivo,
                text="Consejo: al abrir la aplicación se muestra automáticamente el "
                     "cuadro de diálogo para ubicar el archivo. También puede usar el "
                     "botón 'Seleccionar archivo...' o hacer doble clic sobre la ruta.",
                foreground="#555555", wraplength=880, justify="left",
            ).pack(anchor="w", padx=6, pady=(0, 8))

            # 2) Confirmación de columnas PII
            f_cols = ttk.LabelFrame(f, text="  2. Confirmación de columnas a proteger "
                                            "(marque / desmarque)  ")
            f_cols.pack(fill="both", expand=True, padx=8, pady=6)

            barra = ttk.Frame(f_cols)
            barra.pack(fill="x", padx=6, pady=(6, 2))
            ttk.Button(barra, text="Marcar detectadas",
                       command=lambda: self._marcar_columnas("detectadas")).pack(side="left", padx=2)
            ttk.Button(barra, text="Marcar todas",
                       command=lambda: self._marcar_columnas("todas")).pack(side="left", padx=2)
            ttk.Button(barra, text="Desmarcar todas",
                       command=lambda: self._marcar_columnas("ninguna")).pack(side="left", padx=2)
            self.lbl_deteccion = ttk.Label(
                barra, text="", foreground="#007700"
            )
            self.lbl_deteccion.pack(side="left", padx=12)

            canvas = tk.Canvas(f_cols, height=230, highlightthickness=0)
            scroll = ttk.Scrollbar(f_cols, orient="vertical", command=canvas.yview)
            self.frame_cols = ttk.Frame(canvas)
            self.frame_cols.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=self.frame_cols, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 6))
            scroll.pack(side="right", fill="y", padx=(0, 4), pady=(0, 6))
            canvas.bind_all("<MouseWheel>",
                            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

            # 3) Opciones criptográficas
            f_opc = ttk.LabelFrame(f, text="  3. Opciones criptográficas  ")
            f_opc.pack(fill="x", padx=8, pady=6)
            self.var_modo = tk.StringVar(value="hmac")
            ttk.Radiobutton(
                f_opc, text="HMAC-SHA256 determinista (recomendado: mismo valor -> mismo token, preserva cruces)",
                variable=self.var_modo, value="hmac",
            ).pack(anchor="w", padx=6, pady=(6, 0))
            ttk.Radiobutton(
                f_opc, text="Fernet AES-256 CBC+HMAC (aleatorio, sin consistencia de cruces)",
                variable=self.var_modo, value="fernet",
            ).pack(anchor="w", padx=6, pady=(2, 2))

            f_llave = ttk.Frame(f_opc)
            f_llave.pack(fill="x", padx=6, pady=(2, 6))
            ttk.Label(f_llave, text="Reutilizar llave maestra (opcional, para cruces entre archivos):").pack(
                side="left")
            self.var_llave_maestra = tk.StringVar(value="(ninguna)")
            ttk.Entry(f_llave, textvariable=self.var_llave_maestra, state="readonly",
                      width=42).pack(side="left", padx=6, fill="x", expand=True)
            ttk.Button(f_llave, text="Examinar...",
                       command=self._seleccionar_llave_maestra).pack(side="left")

            # 4) Acción
            f_accion = ttk.Frame(f)
            f_accion.pack(fill="x", padx=8, pady=8)
            self.btn_cifrar = ttk.Button(
                f_accion, text="Cifrar y generar Excel protegido (_cifrado.xlsx + _llave.key)",
                style="Accion.TButton", command=self._accion_cifrar,
            )
            self.btn_cifrar.pack(side="left", ipadx=8, ipady=4)

        def _construir_tab_rehidratar(self):
            f = self.tab_rehidratar

            f_proc = ttk.LabelFrame(f, text="  1. Archivo procesado en OpenCode  ")
            f_proc.pack(fill="x", padx=8, pady=6)
            self.var_procesado = tk.StringVar(value="(seleccione el archivo .xlsx / .csv procesado)")
            ttk.Entry(f_proc, textvariable=self.var_procesado, state="readonly").pack(
                side="left", fill="x", expand=True, padx=(6, 4), pady=6)
            ttk.Button(f_proc, text="Examinar...",
                       command=self._seleccionar_procesado).pack(side="right", padx=6, pady=6)

            f_llave = ttk.LabelFrame(f, text="  2. Llave criptográfica (_llave.key)  ")
            f_llave.pack(fill="x", padx=8, pady=6)
            self.var_llave_reh = tk.StringVar(value="(se busca automáticamente junto al archivo)")
            ttk.Entry(f_llave, textvariable=self.var_llave_reh, state="readonly").pack(
                side="left", fill="x", expand=True, padx=(6, 4), pady=6)
            ttk.Button(f_llave, text="Examinar...",
                       command=self._seleccionar_llave_reh).pack(side="right", padx=6, pady=6)

            f_info = ttk.LabelFrame(f, text="  Información  ")
            f_info.pack(fill="both", expand=True, padx=8, pady=6)
            self.txt_info = scrolledtext.ScrolledText(f_info, height=10, state="disabled",
                                                      wrap="word", font=("Consolas", 9))
            self.txt_info.pack(fill="both", expand=True, padx=6, pady=6)
            self._info_reh(
                "La rehidratación restituye el 100 % de los nombres, documentos, "
                "correos y teléfonos reales usando la llave secreta.\n\n"
                "REQUISITOS:\n"
                "  * El archivo procesado debe conservar la hoja 'Datos_Protegidos' "
                "(o las mismas columnas tokenizadas).\n"
                "  * Los tokens NO deben ser alterados manualmente.\n"
                "  * La llave .key generada en el cifrado debe estar disponible localmente.\n\n"
                "Al finalizar se verifica automáticamente la coincidencia del 100 % "
                "(SHA-256) contra el archivo original."
            )

            f_accion = ttk.Frame(f)
            f_accion.pack(fill="x", padx=8, pady=8)
            self.btn_rehidratar = ttk.Button(
                f_accion, text="Rehidratar y restituir información real (_rehidratado.xlsx)",
                style="Accion.TButton", command=self._accion_rehidratar,
            )
            self.btn_rehidratar.pack(side="left", ipadx=8, ipady=4)

        # ------------------------------------------------------------------
        # Registro (log) seguro entre hilos
        # ------------------------------------------------------------------
        def _log(self, msg: str):
            self.cola_log.put(str(msg))

        def _drenar_log(self):
            # 1) Mensajes de registro (cola segura entre hilos)
            while True:
                try:
                    m = self.cola_log.get_nowait()
                except queue.Empty:
                    break
                self.txt_log.configure(state="normal")
                self.txt_log.insert("end", m + "\n")
                self.txt_log.see("end")
                self.txt_log.configure(state="disabled")
            # 2) Resultados de trabajos en segundo plano (nunca se llama a Tk
            #    desde los hilos de trabajo; todo se procesa aquí, en el hilo
            #    principal de la interfaz).
            try:
                while True:
                    tipo, on_ok, resultado, error = self.cola_resultados.get_nowait()
                    if tipo == "ok":
                        self._terminar(on_ok, resultado, None)
                    else:
                        self._terminar(on_ok, None, error)
            except queue.Empty:
                pass
            self.root.after(120, self._drenar_log)

        def _ejecutar_en_hilo(self, fn, on_ok, descripcion: str):
            """Ejecuta `fn(log)` en un hilo; el resultado se entrega a la GUI
            a través de la cola segura (procesada por _drenar_log)."""
            if self.trabajando:
                return
            self.trabajando = True
            self.btn_cifrar.configure(state="disabled")
            self.btn_rehidratar.configure(state="disabled")
            self._log(f"[i] {descripcion} ...")

            def worker():
                try:
                    resultado = fn(self._log)
                    self.cola_resultados.put(("ok", on_ok, resultado, None))
                except Exception as e:
                    self.cola_resultados.put(("error", on_ok, None, e))

            threading.Thread(target=worker, daemon=True).start()

        def _terminar(self, on_ok, resultado, error):
            self.trabajando = False
            self.btn_cifrar.configure(state="normal")
            self.btn_rehidratar.configure(state="normal")
            if error is not None:
                self._log(f"[X] ERROR: {error}")
                messagebox.showerror("Error", str(error), parent=self.root)
                return
            if on_ok is not None:
                on_ok(resultado)

        # ------------------------------------------------------------------
        # Pestaña Cifrar: eventos
        # ------------------------------------------------------------------
        def _seleccionar_archivo(self):
            ruta = filedialog.askopenfilename(
                parent=self.root, title="Seleccionar archivo tabular",
                filetypes=[
                    ("Archivos tabulares", "*.csv *.xlsx *.xlsm"),
                    ("CSV", "*.csv"),
                    ("Excel", "*.xlsx *.xlsm"),
                    ("Todos los archivos", "*.*"),
                ],
            )
            if not ruta:
                return
            self.dialogo_abierto = True
            self.ruta_archivo = ruta
            self.var_archivo.set(ruta)
            self._log(f"[i] Archivo seleccionado: {ruta}")
            self._ejecutar_en_hilo(
                lambda log: self._previsualizar_deteccion(ruta, log),
                self._poblar_checkboxes,
                "Leyendo archivo y auto-detectando columnas PII",
            )

        def _abrir_dialogo_si_es_necesario(self):
            """Abre el diálogo de selección si aún no se ha elegido archivo."""
            if self.ruta_archivo is None and not self.dialogo_abierto and not self.trabajando:
                self.dialogo_abierto = True
                self._seleccionar_archivo()

        def _al_cambiar_tab(self, _evento=None):
            """Al entrar a la pestaña Cifrar sin archivo, ofrece el diálogo."""
            try:
                indice = self.notebook.index(self.notebook.select())
            except Exception:
                return
            if indice == 0:
                self.root.after(250, self._abrir_dialogo_si_es_necesario)

        def _previsualizar_deteccion(self, ruta, log):
            df = leer_tabular(ruta, log=log)
            deteccion = detectar_columnas_pii(df)
            self.df_preview = df
            self.deteccion = deteccion
            return df, deteccion

        def _poblar_checkboxes(self, resultado):
            df, deteccion = resultado
            for w in self.frame_cols.winfo_children():
                w.destroy()
            self.vars_cols = {}
            n_detectadas = sum(1 for d in deteccion.values() if d["puntaje"] >= 2)
            for col in df.columns:
                d = deteccion.get(str(col))
                es_pii = bool(d and d["puntaje"] >= 2)
                var = tk.BooleanVar(value=es_pii)
                fila = ttk.Frame(self.frame_cols)
                ttk.Checkbutton(fila, text=str(col), variable=var).pack(side="left")
                motivo = f"{d['categoria']} · {'; '.join(d['motivos'])}" if d else "no detectada como sensible"
                color = "#006600" if es_pii else "#777777"
                ttk.Label(fila, text=motivo, foreground=color).pack(side="left", padx=8)
                fila.pack(anchor="w", fill="x", padx=6, pady=1)
                self.vars_cols[str(col)] = var
            self.lbl_deteccion.configure(
                text=f"{n_detectadas} columnas PII detectadas (puede ajustar la selección)."
            )
            self._log(f"[OK] Auto-detección completada: {n_detectadas} columnas PII.")

        def _marcar_columnas(self, modo: str):
            for col, var in self.vars_cols.items():
                d = self.deteccion.get(col)
                es_pii = bool(d and d["puntaje"] >= 2)
                if modo == "todas":
                    var.set(True)
                elif modo == "ninguna":
                    var.set(False)
                else:  # detectadas
                    var.set(es_pii)

        def _seleccionar_llave_maestra(self):
            ruta = filedialog.askopenfilename(
                parent=self.root, title="Seleccionar llave maestra existente",
                filetypes=[("Llaves criptográficas", "*.key"), ("Todos", "*.*")],
            )
            if ruta:
                self.ruta_llave_maestra = ruta
                self.var_llave_maestra.set(ruta)

        def _accion_cifrar(self):
            if self.df_preview is None or self.ruta_archivo is None:
                messagebox.showwarning(
                    "Seleccione un archivo",
                    "Primero seleccione un archivo y espere la auto-detección.",
                    parent=self.root,
                )
                return
            seleccionadas = [c for c, var in self.vars_cols.items() if var.get()]
            if not seleccionadas:
                messagebox.showwarning(
                    "Sin columnas seleccionadas",
                    "Marque al menos una columna a proteger.",
                    parent=self.root,
                )
                return
            modo = MODO_HMAC if self.var_modo.get() == "hmac" else MODO_FERNET
            ruta_xlsx, ruta_llave, ruta_csv = rutas_salida_cifrado(self.ruta_archivo)
            existentes = [r for r in (ruta_xlsx, ruta_llave) if os.path.exists(r)]
            forzar = True
            if existentes:
                forzar = messagebox.askyesno(
                    "Sobrescribir archivos",
                    "Ya existen:\n  " + "\n  ".join(existentes) +
                    "\n\n¿Sobrescribirlos? (la llave anterior será reemplazada)",
                    parent=self.root,
                )
                if not forzar:
                    return
            self._ejecutar_en_hilo(
                lambda log: procesar_cifrado(
                    self.ruta_archivo, columnas_sel=seleccionadas, modo=modo,
                    dir_salida=os.path.dirname(self.ruta_archivo),
                    ruta_llave_maestra=self.ruta_llave_maestra,
                    formato="xlsx", forzar=forzar, log=log,
                ),
                self._cifrado_exitoso,
                "Cifrando columnas seleccionadas y generando Excel protegido",
            )

        def _cifrado_exitoso(self, resumen):
            messagebox.showinfo(
                "Cifrado completado",
                f"Archivo cifrado : {resumen['ruta_cifrado']}\n"
                f"Llave secreta   : {resumen['ruta_llave']}\n\n"
                f"Columnas protegidas: {len(resumen['columnas'])}\n"
                f"Filas procesadas   : {resumen['filas']}\n\n"
                f"Exporte SOLO el archivo cifrado hacia OpenCode.\n"
                f"Guarde la llave en un lugar seguro (NO compartirla).",
                parent=self.root,
            )

        # ------------------------------------------------------------------
        # Pestaña Rehidratar: eventos
        # ------------------------------------------------------------------
        def _seleccionar_procesado(self):
            ruta = filedialog.askopenfilename(
                parent=self.root, title="Seleccionar archivo procesado",
                filetypes=[
                    ("Archivos tabulares", "*.csv *.xlsx *.xlsm"),
                    ("CSV", "*.csv"),
                    ("Excel", "*.xlsx *.xlsm"),
                    ("Todos los archivos", "*.*"),
                ],
            )
            if not ruta:
                return
            self.ruta_procesado = ruta
            self.var_procesado.set(ruta)
            sugerida = sugerir_ruta_llave(ruta)
            if os.path.isfile(sugerida):
                self.ruta_llave_reh = sugerida
                self.var_llave_reh.set(sugerida)
                self._log(f"[i] Llave encontrada automáticamente: {sugerida}")
            else:
                self.ruta_llave_reh = None
                self.var_llave_reh.set("(no se encontró *_llave.key junto al archivo: selecciónela)")
                self._log("[!] No se encontró la llave automáticamente; selecciónela manualmente.")

        def _seleccionar_llave_reh(self):
            ruta = filedialog.askopenfilename(
                parent=self.root, title="Seleccionar llave criptográfica",
                filetypes=[("Llaves criptográficas", "*.key"), ("Todos", "*.*")],
            )
            if ruta:
                self.ruta_llave_reh = ruta
                self.var_llave_reh.set(ruta)

        def _info_reh(self, texto):
            self.txt_info.configure(state="normal")
            self.txt_info.delete("1.0", "end")
            self.txt_info.insert("1.0", texto)
            self.txt_info.configure(state="disabled")

        def _accion_rehidratar(self):
            if not self.ruta_procesado:
                messagebox.showwarning(
                    "Seleccione el archivo procesado",
                    "Seleccione el archivo .xlsx/.csv procesado en OpenCode.",
                    parent=self.root,
                )
                return
            if not self.ruta_llave_reh or not os.path.isfile(self.ruta_llave_reh):
                messagebox.showwarning(
                    "Seleccione la llave",
                    "Seleccione el archivo _llave.key generado durante el cifrado.",
                    parent=self.root,
                )
                return
            ruta_xlsx, _ = rutas_salida_rehidratacion(self.ruta_procesado)
            forzar = True
            if os.path.exists(ruta_xlsx):
                forzar = messagebox.askyesno(
                    "Sobrescribir archivo",
                    f"Ya existe:\n  {ruta_xlsx}\n\n¿Sobrescribirlo?",
                    parent=self.root,
                )
                if not forzar:
                    return
            self._ejecutar_en_hilo(
                lambda log: procesar_rehidratacion(
                    self.ruta_procesado, self.ruta_llave_reh,
                    dir_salida=os.path.dirname(self.ruta_procesado),
                    formato="xlsx", forzar=forzar, log=log,
                ),
                self._rehidratacion_exitosa,
                "Rehidratando archivo procesado",
            )

        def _rehidratacion_exitosa(self, resultado):
            df_real, informe = resultado
            if informe.get("coincidencia_100"):
                resumen = (
                    "VERIFICACIÓN: 100 % de coincidencia con el original.\n\n"
                    f"Archivo rehidratado: {informe.get('ruta_salida')}\n"
                    f"Tokens restituidos : {informe.get('tokens_rehidratados', 0)}\n"
                    f"Nulos preservados  : {informe.get('nulos_preservados', 0)}\n"
                )
            else:
                resumen = (
                    "ATENCIÓN: la verificación no dio 100 % de coincidencia.\n\n"
                    f"Archivo rehidratado: {informe.get('ruta_salida')}\n"
                    f"Tokens restituidos : {informe.get('tokens_rehidratados', 0)}\n"
                    f"Columnas faltantes : {informe.get('columnas_faltantes')}\n"
                    f"Tokens desconocidos: {len(informe.get('tokens_desconocidos', []))}\n"
                )
            self._info_reh(resumen)
            messagebox.showinfo("Rehidratación completada", resumen, parent=self.root)


    def iniciar_gui():
        root = tk.Tk()
        AppAnonimizador(root)
        root.mainloop()


else:
    def iniciar_gui():
        raise RuntimeError(
            "Tkinter no está disponible en este entorno. Use la interfaz CLI:\n"
            "  python app_anonimizador_universal.py cifrar ARCHIVO\n"
            "  python app_anonimizador_universal.py rehidratar ARCHIVO --llave LLAVE.key"
        )


if __name__ == "__main__":
    sys.exit(main())
