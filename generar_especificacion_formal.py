# -*- coding: utf-8 -*-
"""
Generador del DOCUMENTO DE ESPECIFICACIÓN FORMAL Y ARQUITECTURA DE SOFTWARE
(v2.0 ampliada) con ecuaciones nativas de Word (OMML), editables en el
editor de ecuaciones de Microsoft Word.

Salida: especificacion-formal-anonimizador-universal_v2.docx
"""

import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsmap
from docx.shared import Inches, Pt, RGBColor

# ---------------------------------------------------------------------------
# Paleta del documento (identidad del original)
# ---------------------------------------------------------------------------
AZUL = RGBColor(0x00, 0x32, 0x4D)          # encabezados y títulos
NARANJA = RGBColor(0xE8, 0x5D, 0x04)        # acentos
GRIS_TXT = RGBColor(0x44, 0x4A, 0x52)
FILL_AZUL = "00324D"
FILL_GRIS = "E2E8F0"
FILL_GRIS2 = "F1F5F9"
FUENTE = "Calibri"
FUENTE_CODIGO = "Consolas"

# ---------------------------------------------------------------------------
# Mini-constructor de ecuaciones OMML (matemáticas nativas de Word)
# ---------------------------------------------------------------------------
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
# Registrar el prefijo 'm' (OMML) en el mapa de espacios de nombres de python-docx
nsmap["m"] = M_NS


def m_tag(nombre):
    """Etiqueta con prefijo 'm' (OMML), resuelta a través del nsmap registrado."""
    return "m:%s" % nombre


def m_r(texto):
    """Run matemático (texto)."""
    r = OxmlElement(m_tag("r"))
    t = OxmlElement(m_tag("t"))
    t.text = texto
    r.append(t)
    return r


def m_e(*hijos):
    e = OxmlElement(m_tag("e"))
    for h in hijos:
        e.append(h)
    return e


def m_omath(*hijos):
    om = OxmlElement(m_tag("oMath"))
    for h in hijos:
        om.append(h)
    return om


def m_sub(base, sub):
    """base_sub  (subíndice)"""
    s = OxmlElement(m_tag("sSub"))
    s.append(m_e(*base))
    s.append(m_e(*sub))
    return s


def m_sup(base, sup):
    """base^sup  (superíndice)"""
    s = OxmlElement(m_tag("sSup"))
    s.append(m_e(*base))
    s.append(m_e(*sup))
    return s


def m_subsup(base, sub, sup):
    """base_sub^sup  (subíndice y superíndice simultáneos)"""
    s = OxmlElement(m_tag("sSubSup"))
    s.append(m_e(*base))
    s.append(m_e(*sub))
    s.append(m_e(*sup))
    return s


# Abreviaturas para componer ecuaciones
def T(t):            return m_r(t)
def SB(a, b):        return m_sub(a, b)
def SP(a, b):        return m_sup(a, b)
def SBS(a, b, c):    return m_subsup(a, b, c)

# ---------------------------------------------------------------------------
# Utilidades del documento
# ---------------------------------------------------------------------------
doc = Document()

for seccion in doc.sections:
    seccion.top_margin = Inches(0.8)
    seccion.bottom_margin = Inches(0.8)
    seccion.left_margin = Inches(0.9)
    seccion.right_margin = Inches(0.9)

estilo = doc.styles["Normal"]
estilo.font.name = FUENTE
estilo.font.size = Pt(10.5)
estilo.paragraph_format.space_after = Pt(6)
estilo.paragraph_format.line_spacing = 1.15


def sombrear_parrafo(p, color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    p._p.get_or_add_pPr().append(shd)


def sombrear_celda(celda, color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    celda._tc.get_or_add_tcPr().append(shd)


def titulo(texto, subtitulo=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(17)
    r.font.color.rgb = AZUL
    p.paragraph_format.space_after = Pt(2)
    if subtitulo:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(subtitulo)
        r2.font.size = Pt(12)
        r2.font.color.rgb = GRIS_TXT
        p2.paragraph_format.space_after = Pt(10)


def h1(texto):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(13.5)
    r.font.color.rgb = AZUL
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    borde = OxmlElement("w:bottom")
    borde.set(qn("w:val"), "single")
    borde.set(qn("w:sz"), "12")
    borde.set(qn("w:space"), "2")
    borde.set(qn("w:color"), "E85D04")
    pBdr.append(borde)
    pPr.append(pBdr)
    return p


def h2(texto):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(11.5)
    r.font.color.rgb = NARANJA
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    return p


def parrafo(runs, alineacion=None, espacio_despues=6):
    p = doc.add_paragraph()
    if isinstance(runs, str):
        runs = [(runs, False, False, None)]
    for texto, bold, italic, color in runs:
        r = p.add_run(texto)
        r.bold = bold
        r.italic = italic
        if color:
            r.font.color.rgb = color
    if alineacion:
        p.alignment = alineacion
    p.paragraph_format.space_after = Pt(espacio_despues)
    return p


def viñeta(runs):
    p = parrafo(runs, espacio_despues=2)
    p.style = doc.styles["List Bullet"]
    return p


def ecuacion(partes, numero=None):
    """Ecuación display centrada, numerada a la derecha (OMML nativo)."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab1 = OxmlElement("w:tab")
    tab1.set(qn("w:val"), "center")
    tab1.set(qn("w:pos"), "4824")
    tabs.append(tab1)
    if numero:
        tab2 = OxmlElement("w:tab")
        tab2.set(qn("w:val"), "right")
        tab2.set(qn("w:pos"), "9360")
        tabs.append(tab2)
    pPr.append(tabs)
    p.add_run("\t")
    p._p.append(m_omath(*partes))
    if numero:
        p.add_run("\t(%s)" % numero)
    p.paragraph_format.space_after = Pt(8)
    return p


def bloque_codigo(lineas):
    p = doc.add_paragraph()
    sombrear_parrafo(p, FILL_GRIS2)
    p.paragraph_format.space_after = Pt(10)
    for i, linea in enumerate(lineas):
        r = p.add_run(linea)
        r.font.name = FUENTE_CODIGO
        r.font.size = Pt(8.5)
        if i < len(lineas) - 1:
            r.add_break()
    return p


def tabla(encabezados, filas, anchos=None):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Table Grid"
    t.autofit = False
    celdas_h = t.rows[0].cells
    for i, h in enumerate(encabezados):
        celdas_h[i].text = ""
        p = celdas_h[i].paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        sombrear_celda(celdas_h[i], FILL_AZUL)
        if anchos:
            celdas_h[i].width = Inches(anchos[i])
    for fila in filas:
        celdas = t.add_row().cells
        for i, valor in enumerate(fila):
            celdas[i].text = ""
            p = celdas[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            if isinstance(valor, tuple) and valor and valor[0] == "EQ":
                p._p.append(m_omath(*valor[1]))
            else:
                r = p.add_run(valor)
                r.font.size = Pt(9)
                if i == 0:
                    r.bold = True
            if anchos:
                celdas[i].width = Inches(anchos[i])
    for idx, fila in enumerate(t.rows):
        if idx == 0:
            continue
        if idx % 2 == 0:
            for celda in fila.cells:
                sombrear_celda(celda, FILL_GRIS2)
    return t


# ===========================================================================
# PORTADA / ENCABEZADO
# ===========================================================================
titulo("DOCUMENTO DE ESPECIFICACIÓN FORMAL Y ARQUITECTURA DE SOFTWARE",
       "Sistema Universal de Anonimización y Rehidratación Biyectiva de Datos Sensibles (PII)")

tabla(
    ["Campo", "Detalle"],
    [
        ["Entidad y Centro", "SENA — Centro de Automatización Industrial (ASTIN) · Coordinación de Etapa Productiva"],
        ["Proyecto / Sistema", "Plataforma de Gobernanza e Ingesta Segura para Agentes IA (OpenCode)"],
        ["Esquema Criptográfico", "AES-256-CBC con HMAC-SHA256 (Fernet) / Tokenización determinista HMAC-SHA256 con Vault biyectivo"],
        ["Estándar de Verificación", "Lógica de Hoare {P} C {Q}, Invariantes de Estado, huella SHA-256 de multiconjunto"],
        ["Versión y Estado", "Versión 2.0 — Especificación Ampliada con Ecuaciones Formales (Noviembre 2026)"],
    ],
    anchos=[1.7, 5.3],
)

# ===========================================================================
# 1. ALCANCE
# ===========================================================================
h1("1. Alcance y Objetivos de Ingeniería")
parrafo("El procesamiento masivo de datos institucionales mediante herramientas de inteligencia "
        "artificial y agentes autónomos (como OpenCode) introduce retos de cumplimiento bajo la Ley "
        "1581 de 2012 (Habeas Data). La exposición involuntaria de Información de Identificación "
        "Personal (PII, por sus siglas en inglés) —números de cédula, nombres completos, correos "
        "electrónicos o números telefónicos— en entornos externos o modelos de lenguaje constituye "
        "una vulnerabilidad crítica de seguridad y gobernanza.")
parrafo("El objetivo de este software es proveer una solución universal, autónoma e idempotente que "
        "permita la encriptación biyectiva local de datos sensibles antes de su ingesta en OpenCode, "
        "garantizando que el análisis, filtrado y generación de código opere exclusivamente sobre "
        "tokens opacos, para posteriormente ejecutar la rehidratación exacta (descifrado) de la "
        "información en el entorno local del Centro ASTIN.")

# ===========================================================================
# 2. MODELO MATEMÁTICO
# ===========================================================================
h1("2. Modelo Matemático Formal y Tipos Algebraicos")
parrafo("El sistema se fundamenta en la teoría de conjuntos y el álgebra criptográfica simétrica. "
        "Se emplea la siguiente convención de notación:", espacio_despues=2)
viñeta([("Σ*", True, False, None), (": conjunto de todas las cadenas de texto Unicode (dominio base).", False, False, None)])
viñeta([("∥", True, False, None), (": operador de concatenación de cadenas.", False, False, None)])
viñeta([("⊥", True, False, None), (": valor nulo (celda vacía, NaN/None en pandas).", False, False, None)])
viñeta([("K", True, False, None), (": clave maestra secreta.  ", False, False, None),
        ("K", True, True, None), ("c", False, True, None),
        (": subclave derivada por columna.", False, False, None)])
viñeta([("f", True, False, None), ("K", False, True, None),
        (": función de transformación criptográfica parametrizada por la clave.", False, False, None)])

h2("2.1 Dominios y Tipos Primarios")
parrafo("Los dominios formales del sistema se definen como sigue:")

ecuacion([SB([T("D")], [T("PII")]), T(" ⊂ Σ*")], "1")
parrafo("Espacio de datos sensibles: dominio discreto de cadenas que representan identificadores "
        "personales (DNI, nombres, apellidos, correos, teléfonos).", espacio_despues=4)

ecuacion([T("C ⊂ Σ*")], "2")
parrafo("Espacio cifrado opaco: cadenas pseudonimizadas o ciphertext en Base64url generadas por el "
        "esquema criptográfico.", espacio_despues=4)

ecuacion([T("K ∈ "), SP([T("{0,1}")], [T("256")])], "3")
parrafo("Clave maestra simétrica de 256 bits, generada localmente con entropía criptográfica fuerte "
        "(Fernet / AES-256).", espacio_despues=4)

ecuacion([SB([T("K")], [T("c")]), T(" = HMAC-SHA256( K, “subclave” ∥ c ),   c ∈ Cols(A)")], "4")
parrafo("Subclave por columna: cada columna c del archivo A deriva su propia clave mediante "
        "HMAC-SHA256, de modo que un mismo valor en columnas distintas produce tokens distintos.",
        espacio_despues=4)

ecuacion([T("Vault : "), SB([T("D")], [T("PII")]), T(" → C,   inyectiva")], "5")
parrafo("Bóveda local de mapeo: relación biyectiva guardada cifrada en el archivo de metadatos "
        "(.key) que garantiza la reversibilidad determinista.", espacio_despues=4)

ecuacion([SP([T("D")], [T("⊥")]), T(" := "), SB([T("D")], [T("PII")]), T(" ∪ {⊥}")], "6")
parrafo("Dominio extendido con el valor nulo: los vacíos forman parte explícita del modelo y deben "
        "atravesar el ciclo sin alteración.")

h2("2.2 Funciones de Transformación Criptográfica")
ecuacion([SB([T("f")], [T("K")]), T(" : "), SP([T("D")], [T("⊥")]), T(" → C ∪ {⊥},    "),
          SB([T("f")], [T("K")]), T("(⊥) = ⊥")], "7")
parrafo("La transformación preserva los valores nulos (Invariante I5). Se implementan dos modos "
        "equivalentes en reversibilidad:")

ecuacion([SB([T("f")], [T("K")]), T("(x) = "), SB([T("τ")], [T("formato")]),
          T("( HMAC-SHA256( "), SB([T("K")], [T("c")]), T(", x ) )")], "8")
parrafo("Modo determinista (predeterminado): tokenización HMAC-SHA256 con forma preservada "
        "(τ_formato): valores numéricos producen tokens numéricos de 12 dígitos, correos producen "
        "tokens con forma de correo (dominio ficticio “.tkn”) y el resto usa el prefijo “TKN_”. "
        "Mismo valor ⇒ mismo token: habilita cruces (joins) entre archivos cifrados.", espacio_despues=4)

ecuacion([SB([T("f")], [T("K")]), T("(x) = "), SB([T("Fernet")], [T("K")]), T("(x)")], "9")
parrafo("Modo aleatorio: cifrado simétrico autenticado AES-256-CBC + HMAC-SHA256 por valor; "
        "reversible de forma directa, sin mapa inverso (los tokens no preservan consistencia de "
        "cruces).")

h2("2.3 Teorema de Biyectividad e Invertibilidad Absoluta")
parrafo([("Sea f", False, False, None), ("K", False, True, None),
         (": D", False, False, None), ("PII", False, False, None),
         (" → C la función de transformación criptográfica parametrizada por la clave K. Para que "
          "el proceso de ingesta y retorno sea válido, f", False, False, None), ("K", False, True, None),
         (" debe ser biyectiva en todo el dominio activo:", False, False, None)])
ecuacion([T("∀ x ∈ "), SB([T("D")], [T("PII")]), T(" :   "),
          SBS([T("f")], [T("K")], [T("−1")]), T("( "),
          SB([T("f")], [T("K")]), T("( x ) ) = x")], "10")
parrafo([("Demostración (boceto). ", True, False, None),
         ("(a) Modo Fernet: el cifrado autenticado es invertible por construcción — "
          "Fernet_K(x) descifra exactamente a x con la misma K. "
          "(b) Modo determinista: HMAC no es invertible algebraicamente; la biyectividad se "
          "garantiza por el Vault (ecuación 5), que almacena el par (token ↦ x) para cada valor "
          "único cifrado en el archivo .key. La rehidratación ejecuta la sustitución exacta del "
          "mapa, de modo que f_K⁻¹(f_K(x)) = x se cumple para todo registro del dominio activo. ∎",
          False, False, None)])

h2("2.4 Propiedades Formales Adicionales")
ecuacion([T("x = y  ⇒  "), SB([T("f")], [T("K")]), T("(x) = "),
          SB([T("f")], [T("K")]), T("(y)")], "11")
parrafo("Determinismo (modo HMAC): valores idénticos producen tokens idénticos — consistencia de "
        "cruces entre reportes cifrados con la misma llave maestra (ej. PE-04 y PE-14).", espacio_despues=4)

ecuacion([T("∀ x ∈ "), SB([T("D")], [T("PII")]), T(" :   "),
          SB([T("f")], [T("K")]), T("(x) ∉ "), SB([T("D")], [T("PII")])], "12")
parrafo("Cero fuga por construcción: el token generado nunca pertenece al dominio sensible; el "
        "sistema lo verifica activamente antes de exportar y aborta ante cualquier coincidencia.",
        espacio_despues=4)

ecuacion([T("x ≠ y  ⇒  "), SB([T("f")], [T("K")]), T("(x) ≠ "),
          SB([T("f")], [T("K")]), T("(y)")], "13")
parrafo("Inyectividad sobre el dominio activo: la generación de tokens reintenta con un contador "
        "determinista ante colisiones, garantizando la unicidad del mapa inverso.")

# ===========================================================================
# 3. CONTRATOS FORMALES (HOARE)
# ===========================================================================
h1("3. Contratos Formales bajo Lógica de Hoare {P} C {Q}")
parrafo("La ejecución del software está gobernada por contratos de ingeniería en notación de Lógica "
        "de Hoare, donde {P} representa las precondiciones del entorno, C la operación del programa "
        "y {Q} las postcondiciones verificadas:  {P} C {Q}.")

h2("3.1 Precondiciones Formales {P}")
ecuacion([T("P1 :  A ∈ {CSV, XLSX}  ∧  Cols(A) = { "),
          SB([T("c")], [T("1")]), T(", "), SB([T("c")], [T("2")]),
          T(", …, "), SB([T("c")], [T("n")]),
          T(" }  ∧  filas(A) ≥ 1")], "14")
ecuacion([T("P2 :  K ∈ "), SP([T("{0,1}")], [T("256")]),
          T("   (entropía criptográfica fuerte)")], "15")
ecuacion([T("P3 :  P ⊆ Cols(A)  ∧  P ≠ ∅   (selección de columnas confirmada)")], "16")

h2("3.2 Postcondiciones Formales {Q}")
ecuacion([T("Q1 :  ran( "), SB([T("f")], [T("K")]), SB([T("|")], [T("P")]),
          T(" ) ∩ "), SB([T("D")], [T("PII")]), T(" = ∅")], "17")
parrafo("Ausencia de PII en el archivo exportado: ninguna columna seleccionada conserva valores "
        "legibles del dominio sensible.", espacio_despues=4)

ecuacion([T("Q2 :  A″ ≡ A")], "18")
parrafo("Reversibilidad verificada: al ejecutar el proceso inverso con A′ y K se obtiene A″ "
        "idéntico al original en los dominios protegidos.", espacio_despues=4)

ecuacion([T("Q3 :  Cols(A′) = Cols(A)  ∧  NoPII(A′) = NoPII(A)  ∧  filas(A′) = filas(A)")], "19")
parrafo("Preservación de estructura: columnas no sensibles, orden, nombres y cantidad de filas "
        "inalterados.")

h2("3.3 Invariantes del Sistema (I)")
parrafo("A lo largo de toda la ejecución se cumplen los siguientes invariantes fundamentales:")
tabla(
    ["Invariante", "Expresión Formal", "Significado de Ingeniería"],
    [
        ["I1 · Cero Fuga de PII",
         ("EQ", [T("ran( "), SB([T("f")], [T("K")]), SB([T("|")], [T("P")]),
                 T(" ) ∩ "), SB([T("D")], [T("PII")]), T(" = ∅")]),
         "Ningún valor de la base sensible original queda en texto claro en el archivo exportado; se verifica activamente antes de escribir."],
        ["I2 · Biyectividad",
         ("EQ", [T("∀ x ∈ "), SB([T("D")], [T("PII")]), T(" : "),
                 SBS([T("f")], [T("K")], [T("−1")]), T("( "), SB([T("f")], [T("K")]),
                 T("(x) ) = x")]),
         "El ciclo cifrar → rehidratar restituye exactamente el dato original (100 % de coincidencia)."],
        ["I3 · Integridad de Estructura",
         ("EQ", [T("Cols(A′) = Cols(A)  ∧  NoPII(A′) = NoPII(A)")]),
         "Nombres, orden y contenido de columnas no sensibles (Fichas, Programas, Fechas, Estados) permanecen inalterados."],
        ["I4 · Determinismo de Tokens",
         ("EQ", [T("x = y  ⇒  "), SB([T("f")], [T("K")]), T("(x) = "),
                 SB([T("f")], [T("K")]), T("(y)")]),
         "Cruces y joins consistentes entre archivos cifrados con la misma llave maestra."],
        ["I5 · Preservación de Nulos",
         ("EQ", [SB([T("f")], [T("K")]), T("(⊥) = ⊥")]),
         "Celdas vacías (NaN/None) atraviesan el ciclo completo sin alteración."],
    ],
    anchos=[1.5, 3.1, 2.4],
)

h2("3.4 Verificación de Integridad por Huella Multiconjunto")
parrafo("La postcondición Q2 se verifica criptográficamente en cada rehidratación mediante una "
        "huella SHA-256 del multiconjunto de valores PII, independiente del orden de las filas:")
ecuacion([SB([T("H")], [T("c")]), T("(A) = SHA-256( "),
          SB([T("⋈")], [T("c ∈ P")]),
          T("  ordenar( { m(x) : x ∈ A[c] } ) )")], "20")
parrafo("donde m(x) = x si x ≠ ⊥, y m(⊥) = “NULL”. La clasificación (ordenar) vuelve la huella "
        "invariante ante reordenamientos de filas realizados por OpenCode.", espacio_despues=4)
ecuacion([T("Q2  ⟺  ( "), SB([T("H")], [T("c")]), T("(A) = "), SB([T("H")], [T("c")]),
          T("(A″) )  ∧  ( P ⊆ Cols(A″) )")], "21")

# ===========================================================================
# 4. ARQUITECTURA
# ===========================================================================
h1("4. Arquitectura del Software y Flujo Operativo de 3 Fases")
ecuacion([T("A  "), SP([T("→")], [T("F1")]), T("  ⟨A′, K, Vault⟩  "),
          SP([T("→")], [T("F2")]), T("  A′*  "), SP([T("→")], [T("F3")]),
          T("  A″ ,   A″ ≡ A")], "22")
parrafo([("Fase 1 — Pre-Procesamiento Local (Cifrado): ", True, False, None),
         ("el usuario selecciona el archivo original (.csv/.xlsx). El motor heurístico detecta las "
          "columnas sensibles y la GUI (Tkinter) permite ajustar la selección. Al confirmar se "
          "generan el archivo [Nombre]_cifrado.xlsx y, de forma independiente, la llave criptográfica "
          "[Nombre]_llave.key.", False, False, None)])
parrafo([("Fase 2 — Procesamiento Seguro en OpenCode: ", True, False, None),
         ("se ingresa únicamente el archivo cifrado. El agente realiza análisis, cruces de tablas o "
          "construcción de scripts operando sobre los tokens, sin acceso a la identidad real.",
          False, False, None)])
parrafo([("Fase 3 — Post-Procesamiento Local (Rehidratación): ", True, False, None),
         ("el resultado devuelto por OpenCode se procesa localmente con la llave .key, restituyendo "
          "nombres y cédulas reales, con verificación SHA-256 de coincidencia al 100 %.",
          False, False, None)])

h2("4.1 Modos Criptográficos")
tabla(
    ["Propiedad", "HMAC_DETERMINISTA_SHA256 (predeterminado)", "FERNET_AES256_CBC_HMAC"],
    [
        ["Token", "HMAC-SHA256(K_c, x) con forma preservada (τ_formato)", "Fernet_K(x) — cifrado autenticado aleatorio"],
        ["Reversibilidad", "Vía Vault cifrado en el .key", "Directa por descifrado"],
        ["Consistencia de cruces", "Sí (ecuación 11)", "No (tokens aleatorios)"],
        ["Uso recomendado", "Dashboards y joins entre reportes (PE-04/PE-14)", "Ciclos simples de ida y vuelta"],
    ],
    anchos=[1.5, 2.8, 2.7],
)

h2("4.2 Formato del Archivo de Llave (.key)")
parrafo("Metadatos criptográficos en JSON; el mapa inverso viaja cifrado con Fernet:", espacio_despues=2)
bloque_codigo([
    "{",
    '  "formato": "ANONIMIZADOR_UNIVERSAL_V1",',
    '  "archivo_origen": "BASE DE DATOS ETAPA PRODUCTIVA.csv",',
    '  "modo": "HMAC_DETERMINISTA_SHA256",',
    '  "columnas_pii": ["NOMBRE_APRENDIZ", "NUMERO_DOCUMENTO", "..."],',
    '  "dtypes_pii": {"NUMERO_DOCUMENTO": "int64"},',
    '  "fernet_key": "<clave AES-256>",',
    '  "mapa_cifrado": "<JSON del mapa token→valor, cifrado con Fernet>",',
    '  "sha256_pii_origen": "<huella de verificación (ecuación 20)>"',
    "}",
])

# ===========================================================================
# 5. INTERFAZ UNIVERSAL
# ===========================================================================
h1("5. Especificación de la Interfaz Universal (GUI & CLI)")
parrafo("La solución combina un motor de detección heurístico con una interfaz gráfica (Tkinter) y "
        "una línea de comandos equivalente.")

h2("5.1 Detección Heurística de Columnas PII")
parrafo("Conjuntos de palabras clave por categoría y patrones de expresión regular:")
ecuacion([SB([T("κ")], [T("Nombre")]), T(" = { nombre, apellido, aprendiz, jefe inmediato, responsable, … }")], None)
ecuacion([SB([T("κ")], [T("Documento")]), T(" = { documento, cédula, identificación, dni, nit, pasaporte, … }")], None)
ecuacion([SB([T("κ")], [T("Contacto")]), T(" = { correo, email, teléfono, celular, dirección, … }")], None)
ecuacion([SB([T("R")], [T("DNI")]), T(" = ^\\d{7,10}$ ,   "),
          SB([T("R")], [T("EMAIL")]), T(" = ^[\\w\\.\\-\\+']+@[\\w\\.\\-]+\\.\\w{2,}$")], None)
parrafo("Una columna c se clasifica como sensible si su puntaje supera el umbral y no pertenece a "
        "la lista de bloqueo B (ficha, programa, modalidad, estado, fecha, código, …):")
ecuacion([SB([T("P")], [T("detectada")]), T(" = { c ∈ Cols(A) : score(c) ≥ 2  ∧  c ∉ B }")], "23")

h2("5.2 Bloque de Configuración de Patrones")
bloque_codigo([
    "PATRONES_PII = {",
    "    'KEYWORDS_NOMBRE'    : ['nombre', 'apellido', 'aprendiz', 'jefe inmediato', 'responsable'],",
    "    'KEYWORDS_DOCUMENTO' : ['documento', 'cedula', 'identificacion', 'dni', 'nit', 'pasaporte'],",
    "    'KEYWORDS_CONTACTO'  : ['correo', 'email', 'telefono', 'celular', 'direccion'],",
    "    'REGEX_DNI'   : r'^\\d{7,10}$',",
    "    'REGEX_EMAIL' : r\"^[\\w\\.\\-\\+']+@[\\w\\.\\-]+\\.\\w{2,}$\",",
    "    'REGEX_TEL'   : r'^\\+?[\\d\\s\\-\\(\\)]{7,15}$',",
    "    'BLOQUEADOS'  : ['ficha', 'programa', 'modalidad', 'estado', 'fecha', 'codigo'],",
    "}",
])

h2("5.3 Comandos de Línea de Comandos (CLI)")
bloque_codigo([
    "AnonimizadorSENA.exe                        # abre la interfaz gráfica",
    "AnonimizadorSENA_CLI.exe detectar \"BASE.csv\"",
    "AnonimizadorSENA_CLI.exe cifrar \"BASE.csv\" --si",
    "AnonimizadorSENA_CLI.exe cifrar \"PE14.csv\" --llave-maestra \"PE04_llave.key\" --si",
    "AnonimizadorSENA_CLI.exe rehidratar \"BASE_cifrado.xlsx\"",
])

# ===========================================================================
# 6. SUITE DE PRUEBAS
# ===========================================================================
h1("6. Suite de Pruebas Unitarias y Demostración de Calidad")
parrafo("Para certificar que el módulo opera bajo la especificación de Lógica de Hoare, el software "
        "incorpora una suite de pruebas unitarias automatizadas (31 casos):")
tabla(
    ["Caso de Prueba", "Entrada / Condición", "Resultado Esperado"],
    [
        ["Test_Biyectividad_100%",
         "Tabla con 1.040 registros PII (nombres y cédulas)",
         "Rehidratación exacta con 0 % de diferencia (ecuación 10)."],
        ["Test_Cero_Fuga_PII",
         "Inspección regex sobre el archivo cifrado",
         "0 coincidencias de DNI o correos en texto claro (Invariante I1)."],
        ["Test_Preservacion_Estructura",
         "CSV con columnas no sensibles y valores vacíos (NaN)",
         "Columnas no PII y nulos idénticos (Invariantes I3 e I5)."],
        ["Test_Determinismo_Tokens",
         "Mismo valor cifrado dos veces con la misma llave",
         "Token idéntico (ecuación 11)."],
        ["Test_Llave_Maestra_Entre_Archivos",
         "PE-04 y PE-14 cifrados con llave compartida",
         "Valores comunes producen tokens comunes (cruces consistentes)."],
        ["Test_Token_Desconocido",
         "Token alterado manualmente por OpenCode",
         "Advertencia explícita; el resto de valores se restituye completo."],
        ["Test_Columnas_Renombradas",
         "OpenCode renombra columnas (minúsculas/espacios)",
         "Se restituyen valores y nombres originales de columna."],
        ["Test_Rendimiento_3540",
         "Base completa de Etapa Productiva (3.540 registros)",
         "Cifrado 0,68 s · Rehidratación 1,62 s (equipo de referencia)."],
        ["Test_GUI_Dialogo_Automatico",
         "Apertura de la aplicación",
         "Cuadro de diálogo de archivo + casillas PII auto-marcadas."],
    ],
    anchos=[1.7, 2.6, 2.7],
)

h2("6.1 Resultados de Verificación Medidos")
tabla(
    ["Métrica", "Valor Medido", "Criterio de Aceptación"],
    [
        ["Pruebas unitarias", "31 / 31 OK (100 %)", "≥ 95 % de aprobación"],
        ["Verificación SHA-256 de rehidratación", "100 % de coincidencia", "= 100 % (ecuación 21)"],
        ["Cero fuga (I1)", "0 coincidencias", "= 0 coincidencias"],
        ["Rendimiento (3.540 filas × 13 columnas)", "0,68 s cifrado / 1,62 s rehidratación", "< 120 s"],
        ["Ejecución de la suite", "python -m unittest test_anonimizador_universal -v", "Exit code 0"],
    ],
    anchos=[2.4, 2.6, 2.0],
)

# ===========================================================================
# 7. CONCLUSIÓN
# ===========================================================================
h1("7. Conclusión")
parrafo("El desarrollo de esta solución universal de anonimización biyectiva garantiza la total "
        "protección de los datos personales de los aprendices e instructores del Centro ASTIN, "
        "permitiendo un flujo de trabajo seguro, auditado y conforme a la normativa vigente al "
        "interactuar con herramientas de IA avanzadas. La especificación formal aquí consignada "
        "—dominios, transformaciones, contratos de Hoare, invariantes I1–I5 y huella de verificación— "
        "constituye la base de certificación del sistema ante auditorías de protección de datos.")

# ===========================================================================
# 8. REFERENCIAS
# ===========================================================================
h1("8. Referencias Normativas y Técnicas")
for ref in [
    "Ley Estatutaria 1581 de 2012 — Protección de Datos Personales (Habeas Data), República de Colombia.",
    "Reglamento (UE) 2016/679 (GDPR) — principios de minimización y pseudonimización.",
    "Hoare, C. A. R. (1969). An Axiomatic Basis for Computer Programming. Communications of the ACM.",
    "NIST SP 800-38A — Recommendation for Block Cipher Modes of Operation (AES-CBC).",
    "FIPS 198-1 — The Keyed-Hash Message Authentication Code (HMAC).",
    "Fernet Specification — cryptography.io (AES-CBC + HMAC-SHA256, tokens versionados).",
    "ISO/IEC 27001 — Sistema de Gestión de Seguridad de la Información.",
]:
    viñeta(ref)

# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------
ruta_proyecto = os.path.dirname(os.path.abspath(__file__))
ruta_salida = os.path.join(ruta_proyecto, "especificacion-formal-anonimizador-universal_v2.docx")
doc.save(ruta_salida)
print("Documento generado:", ruta_salida)
