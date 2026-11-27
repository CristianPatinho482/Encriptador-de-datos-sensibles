# Sistema Universal de Anonimización y Rehidratación Biyectiva

**SENA — Centro ASTIN · Coordinación de Etapa Productiva**

Aplicación local en Python (GUI + CLI) que protege los datos personales
identificables (PII) de archivos tabulares antes de procesarlos en herramientas
externas (OpenCode, modelos en la nube) y **restituye el 100 % de la
información real** al regresar, sin exponer jamás los datos en claro.

Cumple los principios de protección de datos **Ley 1581 de 2012 (Habeas Data)**
y estándares internacionales (GDPR).

---

## 1. Cómo funciona (flujo de trabajo con OpenCode)

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ 1. CIFRADO LOCAL    │     │ 2. ANÁLISIS EXTERNO  │     │ 3. REHIDRATACIÓN     │
│ BASE_ETAPA.csv      │ ──► │ BASE_ETAPA_cifrado   │ ──► │ BASE_ETAPA_          │
│   │                 │     │ .xlsx (tokens)       │     │ rehidratado.xlsx     │
│   ▼                 │     │ procesado en OpenCode│     │ (texto claro 100 %)  │
│ BASE_ETAPA_cifrado  │     │ (nunca ve PII real)  │     │ ▲                   │
│ .xlsx + _llave.key  │     └──────────────────────┘     │ usa _llave.key      │
└─────────────────────┘                                  └─────────────────────┘
```

1. **Cifrar / Anonimizar:** el sistema auto-detecta las columnas con PII
   (nombres, cédulas, correos, teléfonos), muestra una ventana de confirmación
   con casillas, y genera dos archivos:
   - `[Nombre]_cifrado.xlsx` — hoja `Datos_Protegidos` con columnas sensibles
     convertidas en **tokens irreversibles**, columnas no sensibles intactas.
   - `[Nombre]_llave.key` — clave Fernet AES-256 + **mapa JSON cifrado**
     token → valor real (metadatos criptográficos).
2. **Análisis externo:** se comparte con OpenCode **solo el Excel cifrado**.
3. **Rehidratar / Descifrar:** al recibir el archivo procesado de vuelta, junto
   a su `_llave.key`, se restituye el 100 % de nombres, documentos, correos y
   teléfonos reales, con verificación automática de coincidencia (SHA-256).

---

## 2. Instalación

Requisitos: **Python 3.10+** en Windows.

```bat
cd "C:\Users\capatino\Documents\Proyecto encriptador de archivos sensibles"
python -m pip install -r requirements.txt
```

Dependencias: `pandas`, `openpyxl`, `cryptography`, `numpy`.
La interfaz gráfica usa `tkinter` (incluida en el instalador oficial de Python).

---

## 3. Uso

### 3.1 Interfaz gráfica (recomendado)

```bat
python app_anonimizador_universal.py
```

Doble clic también funciona. Al abrir la aplicación se muestra **automáticamente el
cuadro de diálogo para ubicar el archivo** (`.csv` / `.xlsx`). También puede abrirlo
con el botón **"Seleccionar archivo..."** o con doble clic sobre la ruta. Dos pestañas:

| Pestaña | Función |
|---|---|
| **Cifrar / Anonimizar** | Seleccionar archivo → auto-detección PII → marcar/desmarcar columnas → elegir esquema → generar `_cifrado.xlsx` + `_llave.key` |
| **Rehidratar / Descifrar** | Seleccionar archivo procesado + llave → restaurar `_rehidratado.xlsx` con verificación del 100 % |

### 3.2 Línea de comandos (CLI)

```bat
:: Detectar columnas PII de un archivo
python app_anonimizador_universal.py detectar "BASE DE DATOS ETAPA PRODUCTIVA.csv"

:: Cifrar (auto-detección + confirmación)
python app_anonimizador_universal.py cifrar "BASE DE DATOS ETAPA PRODUCTIVA.csv" --si

:: Cifrar indicando columnas explícitas y modo Fernet
python app_anonimizador_universal.py cifrar "BASE.csv" --columnas "NOMBRE_APRENDIZ,NUMERO_DOCUMENTO" --modo fernet

:: Cifrar reutilizando la llave de otro reporte (cruces consistentes)
python app_anonimizador_universal.py cifrar "REPORTE_PE14.csv" --llave-maestra "REPORTE_PE04_llave.key" --si

:: Rehidratar (la llave se busca automáticamente junto al archivo)
python app_anonimizador_universal.py rehidratar "BASE_cifrado.xlsx"
```

### 3.3 Datos de demostración

```bat
python generar_datos_demo.py
```

Genera `BASE DE DATOS ETAPA PRODUCTIVA_DEMO.csv` (60 filas, datos ficticios con
tildes, nulos y duplicados) para probar todo el flujo sin riesgo.

### 3.4 Ejecutable de Windows (sin instalar Python)

Para usuarios finales se genera un ejecutable de un clic con PyInstaller,
con el ícono `assets/SOFIABOT.ico` embebido:

| Archivo | Uso |
|---|---|
| `dist/AnonimizadorSENA.exe` | Interfaz gráfica (doble clic, sin consola) |
| `dist/AnonimizadorSENA_CLI.exe` | Línea de comandos (`cifrar` / `rehidratar` / `detectar`) |
| `Anonimizador SENA.lnk` | Lanzador con el ícono (ya quedó uno en el Escritorio) |

Para recompilar después de modificar el código:

```bat
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name AnonimizadorSENA --icon "assets\SOFIABOT.ico" --add-data "assets\SOFIABOT.ico;assets" app_anonimizador_universal.py
python -m PyInstaller --noconfirm --clean --onefile --console --name AnonimizadorSENA_CLI --icon "assets\SOFIABOT.ico" --add-data "assets\SOFIABOT.ico;assets" app_anonimizador_universal.py
```

> **Notas:** los `.exe` de PyInstaller suelen disparar avisos de SmartScreen o
> del antivirus (falso positivo habitual); se recomienda agregar una excepción
> o firmarlos digitalmente. Los `.exe`, `build/` y `dist/` **no se suben a git**
> (están en `.gitignore`): se compilan localmente con el comando anterior.

**Kit para compartir:** `AnonimizadorSENA_v1.0.0_Windows.zip` contiene el
ejecutable, el manual (`MANUAL_USUARIO.html`) y un `LEEME.txt`. Para un usuario
final basta entregar ese ZIP (o solo el `.exe` + el manual). El **manual de
usuario** (`MANUAL_USUARIO.md` / `MANUAL_USUARIO.html`) explica el flujo
cifrar → analizar → rehidratar, las reglas de la llave y la solución de
problemas.

---

## 4. Arquitectura criptográfica

### Esquemas soportados

| Modo | Token | Ventaja |
|---|---|---|
| **HMAC_DETERMINISTA_SHA256** *(predeterminado)* | `HMAC-SHA256(subclave_columna, valor)` con forma preservada | Mismo valor → mismo token: **permite cruces/joins** entre archivos cifrados |
| **FERNET_AES256_CBC_HMAC** | Cifrado simétrico autenticado por valor | Biyectivo directo, tokens aleatorios (sin joins) |

- **Subclave por columna:** `HMAC-SHA256(clave_maestra, nombre_columna)` — un
  mismo valor en columnas distintas produce tokens distintos.
- **Forma preservada ligera:** los documentos numéricos producen tokens
  numéricos de 12 dígitos; los correos producen tokens con forma de correo
  (dominio ficticio `.tkn`); el resto usa el prefijo `TKN_`.
- **Mapa inverso cifrado:** el `.key` contiene el mapa token → valor real
  cifrado con Fernet. Es lo que garantiza la **biyectividad estricta** en modo
  HMAC (HMAC por sí solo no es invertible).

### Invariantes formales (Lógica de Hoare)

```
{ P }  C  { Q }   donde P ≡ (K ≠ ∅) ∧ (|K| = 256 bits) ∧ (existe archivo de entrada)

I₁ (Cero fuga)       : ValoresCifrados ∩ TextoClaro = ∅
I₂ (Biyectividad)    : Dec(Enc(x, K), K) = x   ∀ x ∈ D_PII
I₃ (Estructura)      : EstructuraNoPII(A_in) = EstructuraNoPII(A_out)
```

El programa **verifica activamente** I₁ antes de exportar (si detecta un valor
en claro en la salida, aborta) e I₂ en cada rehidratación (comparación SHA-256
del multiconjunto de valores PII contra el original, tolerante a reordenamiento
de filas).

### Formato del archivo `_llave.key` (JSON)

```json
{
  "formato": "ANONIMIZADOR_UNIVERSAL_V1",
  "archivo_origen": "BASE DE DATOS ETAPA PRODUCTIVA.csv",
  "fecha_cifrado": "2026-11-26T14:32:10",
  "modo": "HMAC_DETERMINISTA_SHA256",
  "columnas_pii": ["NOMBRE_APRENDIZ", "NUMERO_DOCUMENTO", "..."],
  "dtypes_pii": {"NUMERO_DOCUMENTO": "int64"},
  "fernet_key": "<clave AES-256>",
  "mapa_cifrado": "<JSON del mapa token→valor, cifrado con Fernet>",
  "sha256_pii_origen": "<huella de verificación>"
}
```

### Detección heurística de columnas PII

- **Palabras clave:** `nombre`, `apellido`, `aprendiz`, `jefe inmediato`,
  `responsable`, `documento`, `cedula`, `identificacion`, `dni`, `nit`,
  `correo`, `email`, `telefono`, `celular`, `direccion`, etc.
- **Expresiones regulares sobre valores:** cadenas de 7–10 dígitos (DNI),
  correos electrónicos, teléfonos.
- **Lista de exclusión:** `ficha`, `programa`, `modalidad`, `estado`, `fecha`,
  `codigo`, etc. (evita falsos positivos).
- La GUI siempre muestra la lista con casillas para confirmar/ajustar.

---

## 5. Pruebas unitarias (demostración matemática)

```bat
python -m unittest test_anonimizador_universal -v
```

Cubre: detección PII, determinismo de tokens, **cero fuga (I₁)**,
**rehidratación al 100 % (I₂)**, preservación de nulos y columnas no sensibles
**(I₃)**, reordenamiento de filas, reutilización de llave maestra entre
archivos, no exposición de texto claro en el `.key`, y flujo CLI completo.

---

## 6. Seguridad y buenas prácticas

1. **La llave `.key` es el único secreto.** Guárdela en lugar seguro (carpeta
   restringida, disco cifrado) y **nunca** la suba a la nube ni la comparta con
   OpenCode.
2. Comparta únicamente el archivo `_cifrado.xlsx` (hoja `Datos_Protegidos`).
3. Haga copias de seguridad de las llaves: sin la llave, los tokens son
   **irrecuperables** (HMAC no es invertible sin el mapa).
4. Para cruzar dos reportes cifrados (ej. PE-04 con PE-14), cifre ambos con la
   misma llave maestra (`--llave-maestra` o la opción en la GUI).
5. Si OpenCode agrega filas nuevas con valores que no estaban en el original,
   la rehidratación los dejará como tokens desconocidos y la verificación lo
   advertirá (los valores originales sí se restauran completos).
6. Los tokens con forma numérica tienen 12 dígitos fijos; Excel no les pierde
   precisión.

## 7. Estructura del proyecto

| Archivo | Descripción |
|---|---|
| `app_anonimizador_universal.py` | Aplicación principal (motor criptográfico + GUI + CLI) |
| `test_anonimizador_universal.py` | Pruebas unitarias de biyectividad y seguridad |
| `generar_datos_demo.py` | Generador de datos sintéticos de demostración |
| `assets/SOFIABOT.ico` | Ícono de la ventana principal y de sus diálogos |
| `MANUAL_USUARIO.md` / `MANUAL_USUARIO.html` | Manual de usuario (HTML para abrir en el navegador) |
| `LEEME.txt` | Instrucciones rápidas para el kit de distribución |
| `dist/AnonimizadorSENA.exe` | Ejecutable Windows de un clic (PyInstaller; no va a git) |
| `Anonimizador SENA.lnk` | Lanzador con ícono para el Escritorio |
| `AnonimizadorSENA_v1.0.0_Windows.zip` | Kit de distribución listo para compartir (no va a git) |
| `requirements.txt` | Dependencias Python |
| `MEMORY.md` / `AGENTS.md` | Memoria del sistema y directivas del agente |
