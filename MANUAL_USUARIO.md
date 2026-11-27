# Manual de Usuario — Anonimizador SENA

**Sistema Universal de Anonimización y Rehidratación Biyectiva · Versión 1.0.0**
SENA — Centro ASTIN · Coordinación de Etapa Productiva

---

## 1. ¿Qué es y para qué sirve?

Es una aplicación local que **protege los datos personales** (nombres, cédulas,
correos, teléfonos) de archivos Excel o CSV **antes** de procesarlos en
herramientas externas de inteligencia artificial (como OpenCode), y que
**restituye el 100 % de la información real** cuando los resultados regresan.

Con este flujo, las herramientas externas trabajan con *tokens* (textos sin
significado) y **nunca ven los datos reales** de los aprendices.

---

## 2. Qué necesito

**Nada más que el archivo `AnonimizadorSENA.exe`.**

- No necesita instalar Python ni ningún programa adicional.
- Funciona en Windows 10/11.
- Abra la aplicación con **doble clic**.

> Si Windows muestra un aviso de **SmartScreen** ("Windows protegió su equipo"),
> es un falso positivo habitual de los programas empaquetados. Haga clic en
> **"Más información" → "Ejecutar de todas formas"**.

---

## 3. El flujo de trabajo en 3 pasos

```
 1. CIFRAR            2. ANALIZAR (OpenCode)        3. REHIDRATAR
 BASE.csv   ────►   BASE_cifrado.xlsx   ────►   BASE_rehidratado.xlsx
   +                     (solo tokens,              (datos reales
 BASE_llave.key          sin PII real)               restituidos 100 %)
```

| Fase | Qué hace | Dónde |
|---|---|---|
| 1. Cifrar | Convierte las columnas sensibles en tokens y genera la llave | Esta aplicación |
| 2. Analizar | La herramienta externa trabaja con el Excel cifrado | OpenCode / nube |
| 3. Rehidratar | Devuelve los nombres y documentos reales al archivo final | Esta aplicación |

---

## 4. Cifrar un archivo (paso a paso)

1. Abra `AnonimizadorSENA.exe`. Se abre la ventana y, automáticamente, el
   **cuadro de diálogo para ubicar el archivo**.
2. Seleccione su archivo `.csv` o `.xlsx` (ej. `BASE DE DATOS ETAPA PRODUCTIVA.csv`).
3. La aplicación **detecta automáticamente las columnas con datos personales**
   y las muestra con casillas de verificación (puede marcar o desmarcar).
   - En verde: columnas detectadas como sensibles (quedan marcadas).
   - En gris: columnas no sensibles (Fichas, Programas, Fechas...).
4. Revise la selección y haga clic en
   **"Cifrar y generar Excel protegido"**.
5. Se generan **dos archivos** junto a su archivo original:

| Archivo | Contenido | ¿Se comparte? |
|---|---|---|
| `NOMBRE_cifrado.xlsx` | Hoja `Datos_Protegidos`: tokens sin datos reales + hoja `Metadatos` | **SÍ**, este va a OpenCode |
| `NOMBRE_llave.key` | Clave secreta + mapa para devolver los datos reales | **NUNCA** — se guarda localmente |

---

## 5. Rehidratar (recuperar los datos reales)

Cuando OpenCode devuelva el archivo procesado:

1. Abra la pestaña **"Rehidratar / Descifrar"**.
2. Seleccione el **archivo procesado** (el que devolvió OpenCode).
   La llave se busca automáticamente junto al archivo; si no aparece,
   selecciónela con el botón "Examinar...".
3. Haga clic en **"Rehidratar y restituir información real"**.
4. Se genera `NOMBRE_rehidratado.xlsx` y la aplicación verifica
   automáticamente:
   - **"100 % de coincidencia"**: todo se restauró correctamente. ✔
   - Si no da 100 %, revise los avisos (ver sección 9).

---

## 6. La llave: reglas de oro 🔑

1. **La llave es el único secreto.** Sin ella, los tokens son irrecuperables.
2. **Guárdela en lugar seguro** (carpeta restringida o disco cifrado).
3. **Nunca** la suba a la nube, al chat ni al correo.
4. **Haga copia de seguridad.** Si la llave se pierde, no hay forma de
   recuperar los datos reales de ese cifrado.
5. **Cruces entre reportes:** si necesita cruzar dos archivos cifrados
   (ej. PE-04 con PE-14), cifre ambos **reutilizando la misma llave**
   (opción "Reutilizar llave maestra" en la GUI). Así, el mismo documento
   produce el mismo token en ambos archivos.

---

## 7. Columnas sensibles: cómo se detectan

La aplicación combina **palabras clave** y **patrones**:

- **Nombres:** `nombre`, `apellido`, `aprendiz`, `jefe inmediato`, `responsable`...
- **Documentos:** `documento`, `cédula`, `identificación`, `dni`, `nit`...
- **Contacto:** `correo`, `email`, `teléfono`, `celular`, `dirección`...
- **Patrones:** números de 7–10 dígitos, correos electrónicos, teléfonos.

Columnas como `FICHA`, `PROGRAMA`, `MODALIDAD`, `ESTADO` y `FECHA` se
**excluyen automáticamente** y quedan intactas en el archivo cifrado.
Si la detección no es perfecta, ajuste las casillas antes de cifrar.

---

## 8. Uso por línea de comandos (opcional)

```bat
AnonimizadorSENA_CLI.exe detectar "BASE.csv"
AnonimizadorSENA_CLI.exe cifrar "BASE.csv" --si
AnonimizadorSENA_CLI.exe rehidratar "BASE_cifrado.xlsx"
```

*(Para usuarios avanzados; la interfaz gráfica cubre todo el flujo.)*

---

## 9. Solución de problemas

| Mensaje / situación | Qué hacer |
|---|---|
| SmartScreen o antivirus bloquea el `.exe` | "Más información" → "Ejecutar de todas formas" (falso positivo) |
| "El archivo está abierto en otro programa (p. ej. Excel)" | Cierre el archivo en Excel y repita |
| "La verificación NO dio 100 %" con tokens desconocidos | OpenCode modificó o agregó datos: los valores originales sí se restauraron; revise los tokens señalados |
| "La columna PII ... no está en el archivo procesado" | OpenCode eliminó esa columna; el resto se restaura normal |
| Archivo `.xls` antiguo no se lee | Conviértalo a `.xlsx` o `.csv` en Excel |
| CSV que no se abre | Se soportan codificaciones UTF-8 y latin-1; separador auto-detectado (coma o punto y coma) |

---

## 10. Seguridad y protección de datos (Ley 1581 de 2012)

- Comparta con OpenCode **únicamente** el archivo `_cifrado.xlsx`.
- Los tokens no revelan nombres ni documentos reales; la llave es lo único
  que permite volver al texto claro.
- Si una llave o una base real llegara a exponerse, repórtelo al encargado
  de protección de datos del SENA como incidente de seguridad.
- Si una llave se expuso, considérela comprometida: genere una nueva y
  vuelva a cifrar.

---

## 11. Preguntas frecuentes

**¿Puedo procesar cualquier archivo?**
Sí: cualquier `.csv` o `.xlsx`; la detección se adapta a las columnas.

**¿Los valores vacíos se pierden?**
No. Las celdas vacías y las columnas no sensibles quedan intactas.

**¿Dos cifrados del mismo archivo dan el mismo resultado?**
Sí, si reutiliza la misma llave maestra; con llaves nuevas los tokens cambian.

**¿Qué pasa si pierdo la llave?**
Los datos cifrados con ella no se pueden recuperar. Por eso: copia de
seguridad de toda llave generada.

**¿El programa envía datos a internet?**
No. Todo el procesamiento es 100 % local.

---

*Documento interno SENA — Centro ASTIN. Versión del manual: 1.0.0*
