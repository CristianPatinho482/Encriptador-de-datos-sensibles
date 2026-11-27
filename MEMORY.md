# MEMORY.md — Memoria del Sistema y Especificación Formal del Proyecto

## 1. Memoria del Proyecto y Estado del Dominio
- **Organización:** SENA Centro ASTIN — Coordinación de Etapa Productiva.
- **Caso Principal de Prueba:** `BASE DE DATOS ETAPA PRODUCTIVA.csv` (1.040 aprendices virtuales, 3.540 registros totales).
- **Problema Solucionado:** Ingreso masivo de datos personales identificables (PII) a entornos de IA y herramientas en la nube.
- **Solución Adoptada:** Pseudonimización biyectiva local universal con generación de archivo **Excel Cifrado** y metadatos criptográficos en llave separada.

### Estado de Implementación (actualizado 2026-11-27)
- [x] `app_anonimizador_universal.py` — motor criptográfico + GUI (Tkinter) + CLI. Versión 1.0.0.
- [x] Modo predeterminado `HMAC_DETERMINISTA_SHA256` con subclave por columna, forma preservada ligera (numérico 12 dígitos / correo `.tkn` / `TKN_`) y mapa inverso cifrado con Fernet dentro del `.key`.
- [x] Modo alternativo `FERNET_AES256_CBC_HMAC` (descifrado directo por valor).
- [x] Reutilización de llave maestra entre reportes (`--llave-maestra`) para cruces consistentes (ej. PE-04 ↔ PE-14).
- [x] Verificación activa de invariantes: I₁ (cero fuga) antes de exportar; I₂ (biyectividad) con SHA-256 de multiconjunto (tolerante a reordenamiento de filas) en cada rehidratación; I₃ (estructura) por preservación de columnas no PII, tipos y nulos.
- [x] `test_anonimizador_universal.py` — 31 pruebas unitarias (detección, determinismo, cero fuga, roundtrip 100 %, nulos, reordenamiento, llave maestra, CLI, GUI, ícono). Resultado: **31/31 OK**.
- [x] `generar_datos_demo.py` — dataset sintético de 60 filas para demostración segura.
- [x] Validado de extremo a extremo: cifrado → rehidratación → 100 % de coincidencia (SHA-256).
- [x] **Ejecutable Windows de un clic (PyInstaller, 2026-11-27):** `dist/AnonimizadorSENA.exe` (GUI, sin consola) y `dist/AnonimizadorSENA_CLI.exe` (consola), ambos con el ícono `assets/SOFIABOT.ico` embebido, más lanzador `Anonimizador SENA.lnk` (Escritorio). Sin necesidad de instalar Python.
- [x] GUI con diálogo automático de selección de archivo, auto-detección PII con casillas de confirmación e ícono SOFIABOT.
- [ ] Pendiente (futuro): firma digital de los ejecutables y de los archivos de salida; cifrado de llave con contraseña maestra (passphrase).


---

## 2. Especificación Matemática y Formal (Lógica de Hoare)

### Espacio de Datos y Tipos Algebraicos
- $D_{\text{PII}} \subset \text{String}$ (Nombres, Apellidos, DNI, Correos, Teléfonos).
- $K \in \text{Byte}^{32}$ (Clave secreta AES-256 Fernet).
- $P \subseteq \text{Columnas}$ (Subconjunto de columnas clasificadas como sensibles).

### Contratos Formales $\{P\} \; C \; \{Q\}$
- **Precondición $\{P\}$:**
  $$P \equiv (K \neq \emptyset) \land (|K| = 256 \text{ bits}) \land (\text{Existe archivo de entrada CSV/XLSX})$$
- **Postcondición $\{Q\}$:**
  $$Q \equiv (\forall c \in P, \, \text{ContainsPII}(c_{\text{out}}) = \text{False}) \land (\forall x \in D_{\text{PII}}, \, f_K^{-1}(f_K(x)) = x)$$
- **Invariantes del Sistema ($I$):**
  1. $I_1: \text{ValoresCifrados} \cap \text{TextoClaro} = \emptyset$
  2. $I_2: \text{Dec}(\text{Enc}(x, K), K) = x \quad \forall x \in D_{\text{PII}}$
  3. $I_3: \text{EstructuraNoPII}(A_{\text{in}}) = \text{EstructuraNoPII}(A_{\text{out}})$

---

## 3. Patrones de Detección Heurística PII
El sistema utiliza coincidencia por palabras clave y expresiones regulares para auto-detectar PII:
- **Nombres / Apellidos:** `nombre`, `primer_apellido`, `segundo_apellido`, `aprendiz`, `jefe_inmediato`, `responsable`.
- **Documentos / DNI:** `numero_documento`, `documento`, `cedula`, `identificacion`, `dni`, `nit`, `pasaporte`.
- **Contacto:** `correo`, `email`, `telefono`, `celular`, `direccion`.
- **Patrones Regex:** Cadenas de 7 a 10 dígitos continuos (DNI), expresiones de email (`[\w\.-]+@[\w\.-]+\.\w+`).

---

## 4. Estructura de Salida (Archivo Excel Cifrado)
El archivo generado para su procesamiento en OpenCode contiene:
1. **Hoja Principal (`Datos_Protegidos`):** Columnas no sensibles en texto claro + columnas PII convertidas a hashes o tokens encriptados.
2. **Archivo de Metadatos y Llave (`<nombre_archivo>.key`):** Clave Fernet codificada + mapa JSON cifrado de columnas afectadas para la rehidratación biyectiva.
