# Propuesta Servicios — Venezuela INNOVA 2026

Aplicación para recibir y auditar propuestas de adquisición de equipos, con un motor de lote autónomo en `agent/`. El motor no importa módulos de `app/` ni usa SQLite.

## Requisitos

- Python 3.10 o superior
- Una clave de Gemini para extraer PDF/imágenes y buscar precios; XLSX y validaciones determinísticas funcionan sin ella
- Variables de entorno configuradas para las cuentas web y cifrado antes de cargar archivos

No hay cuentas ni contraseñas predeterminadas en el proyecto: los usuarios se crean mediante `APP_USERS_JSON`.

El proyecto usa `gemini-3.8-flash`: Google devolvió `404 NOT_FOUND` para `gemini-2.5-flash` en una cuenta nueva y recomendó este modelo.

## Instalación y configuración

### Linux (Bash) — principal para el hackatón

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`.venv` es la carpeta del entorno virtual; `source .venv/bin/activate` solo la activa y dará error si todavía no creaste esa carpeta. `.env` es otro archivo, con claves y cuentas: si falta, la activación del entorno sigue funcionando, pero la aplicación no tendrá usuarios configurados, no podrá cifrar cargas y no podrá usar Gemini.

### Windows (PowerShell) — para trabajar en casa

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Crear y proteger `.env`

El proyecto carga automáticamente `.env`. En Linux, copia la plantilla, limita sus permisos al usuario y edítala:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

En Windows, crea y abre el archivo así:

```powershell
Copy-Item .env.example .env
notepad .env
```

Pega en `GEMINI_API_KEY` una clave nueva creada en Google AI Studio. No la incluyas en código ni la compartas por chat. Genera valores aleatorios distintos para AES y la sesión; cada comando imprime líneas listas para copiar a `.env`.

Linux (Bash):

```bash
python -c 'import base64, secrets; print("APP_ENCRYPTION_KEY=" + base64.b64encode(secrets.token_bytes(32)).decode()); print("APP_SESSION_SECRET=" + base64.b64encode(secrets.token_bytes(32)).decode())'
```

Windows (PowerShell):

```powershell
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $encryptionBytes = New-Object byte[] 32
    $rng.GetBytes($encryptionBytes)
    Write-Output "APP_ENCRYPTION_KEY=$([Convert]::ToBase64String($encryptionBytes))"

    $sessionBytes = New-Object byte[] 32
    $rng.GetBytes($sessionBytes)
    Write-Output "APP_SESSION_SECRET=$([Convert]::ToBase64String($sessionBytes))"
} finally {
    $rng.Dispose()
}
```

Configura `APP_USERS_JSON` en `.env` con contraseñas propias. No uses los marcadores de `.env.example`. `.env` queda excluido de Git; respáldalo de forma segura, especialmente `APP_ENCRYPTION_KEY`, porque sin esa clave no podrás descifrar los archivos guardados.

Las variables ya establecidas en el sistema o en la terminal tienen prioridad sobre `.env`. En Bash ejecuta `unset GEMINI_API_KEY`; en PowerShell ejecuta `Remove-Item Env:GEMINI_API_KEY`. También puedes abrir una terminal nueva.

### Usar el proyecto en Windows y Linux

Repite la creación de `.env` en cada computadora; no se sube a Git. Si necesitas abrir en ambos sistemas la misma base de datos y los mismos archivos cifrados, configura el **mismo `APP_ENCRYPTION_KEY`** en ambos `.env` y transfiérelo por un canal seguro. Puedes usar una clave Gemini y usuarios propios en cada entorno. Si cada equipo tendrá datos independientes, genera claves de cifrado distintas.

### Comprobar Gemini desde Bash

Ejecuta desde la raíz del proyecto. El SDK de Gemini no lee `.env` por sí solo, así que la prueba carga el archivo explícitamente:

```bash
python - <<'PY'
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.cwd() / ".env")

from google import genai

with genai.Client() as client:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Responde solo OK",
    )
    print(response.text)
PY
```

Prueba la extracción de una propuesta PDF o imagen con el agente (reemplaza la ruta por un archivo real):

```bash
python - lote/propuestas/oferta.pdf <<'PY'
import sys
from agent.extractor import extract_proposal

proposal = extract_proposal(sys.argv[1])
print("Archivo:", proposal.archivo)
print("Ítems extraídos:", len(proposal.items))
print("Anomalías:", proposal.anomalias_ingesta)
PY
```

Windows (PowerShell):

```powershell
@'
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.cwd() / ".env")

from google import genai

with genai.Client() as client:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Responde solo OK",
    )
    print(response.text)
'@ | python
```

Variables opcionales:

- `APP_DATA_DIR`: directorio de base SQLite y archivos cifrados (predeterminado: `data`).
- `DATABASE_URL`: URL SQLAlchemy para sustituir SQLite.
- `REPOSITORY_URL`: valor para `repositorio` del JSON de lote cuando no hay remoto Git.
- `COOKIE_SECURE=1`: marca la cookie como Secure cuando se sirve detrás de HTTPS.

## Ejecutar y validar

Linux (Bash):

```bash
pytest tests/ -v
python evaluar_lote.py --input lote --output salida.json
```

Windows (PowerShell):

```powershell
pytest tests/ -v
python evaluar_lote.py --input lote --output salida.json
```

Estructura de lote:

```text
lote/
├── proyecto.pdf
└── propuestas/
    ├── oferta-a.pdf
    ├── oferta-b.xlsx
    └── oferta-c.png
```

Los fallos de lectura o extracción se registran explícitamente; si faltan datos financieros, moneda, impuestos o una cotización de entrega verificable, la factibilidad queda como **no concluyente** en vez de inventar costos. La búsqueda de mercado usa Google Search Grounding, conserva URLs y precios observados en el informe y se cachea por componente y día. Un precio por encima del máximo observado genera una alerta, no un descarte automático.

El archivo `validador_salida.html` implementa un validador local del contrato indicado en estas instrucciones (claves exactas, tipos, timestamps `-04:00` y ranking sin duplicados). No se proporcionó el validador oficial original, por lo que este archivo no se presenta como copia oficial.

## Aplicación web

Linux (Bash), con las variables de `.env` configuradas:

```bash
uvicorn app.main:app --reload
```

Windows (PowerShell):

```powershell
uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000/login`. Al crear un proyecto, el rol **Carga** registra ciudad, estado y presupuesto máximo con impuestos incluidos, en USD o VES. En **Recepción**, carga el PDF base y entre 3 y 20 propuestas. El evaluador extrae requisitos del PDF base con Gemini y conserva páginas de evidencia.

Antes de evaluar, el rol **Aprobador** registra la tasa BCV en VES por USD, fecha y fuente oficial. El sistema exige esa referencia y utiliza la misma tasa para normalizar propuestas y presupuesto a USD; también informa equivalentes en VES. Las propuestas deben indicar moneda y total final o impuestos desglosados. Si no se conoce la moneda, faltan impuestos, el PDF no produce requisitos verificables o el flete no está confirmado para el destino, no se declara la propuesta financieramente factible: queda como no concluyente y muestra la advertencia.

En **Recepción**, Carga o Aprobador puede registrar por propuesta una cotización adicional de transporte con monto final (incluidos los impuestos del flete si aplican), moneda, fecha y fuente. El sistema la convierte con la tasa BCV del proyecto y la suma al TCO; si la oferta declara el flete incluido, evita duplicarlo. Si no hay cotización ni confirmación de flete incluido, no inventa una tarifa y deja la factibilidad no concluyente. Los recargos porcentuales se calculan sobre el subtotal, salvo que la cláusula indique que aplican al valor de la factura; el desglose y los avisos se muestran en la trazabilidad y el informe.

El botón **Evaluar propuestas de servicios** conserva en pantalla los eventos en vivo: lectura y extracción del PDF base y las propuestas, validaciones, componentes del TCO, cotización del flete usada o faltante, búsquedas web por ítem y resultado. El informe presenta una recomendación solo si hay una propuesta con aritmética y alcance conformes, TCO completo y costo dentro del presupuesto; incluye una matriz de montos declarados, conciliación aritmética y TCO ajustado, y dictámenes cuantificados. Las alertas de precios web son indicativas y no causan descarte automático. Se puede imprimir a PDF desde el navegador o descargar como Markdown/CSV. Los proyectos existentes reciben las columnas nuevas al iniciar la app, pero hay que completar manualmente ciudad, estado, presupuesto y referencia BCV antes de evaluarlos.

### Probar pantallas por rol (Linux/Bash)

1. En `.env`, reemplaza `APP_USERS_JSON` por cuatro cuentas locales. Define contraseñas distintas y no compartas este archivo:

   ```dotenv
   APP_USERS_JSON='{"carga":{"password":"CAMBIA_ESTA_CLAVE","role":"Carga"},"revisor":{"password":"CAMBIA_ESTA_CLAVE","role":"Revisor"},"aprobador":{"password":"CAMBIA_ESTA_CLAVE","role":"Aprobador"},"lectura":{"password":"CAMBIA_ESTA_CLAVE","role":"Solo lectura"}}'
   ```

2. Desde la raíz del proyecto, inicia la app. Si estaba ejecutándose, deténla y vuelve a iniciarla para que lea las cuentas actualizadas:

   ```bash
   cd ~/hackaton2026
   source .venv/bin/activate
   uvicorn app.main:app --reload
   ```

3. Abre `http://127.0.0.1:8000/login` e inicia sesión como `carga`. Al crear el proyecto, ingresa ciudad, estado y presupuesto máximo con impuestos incluidos, eligiendo USD o VES. En **Recepción**, carga el PDF base y entre 3 y 20 propuestas. Anota el ID del proyecto en la URL para volver a él con las demás cuentas.
4. Cierra sesión, entra como `aprobador` y registra en **Recepción** la tasa BCV (VES por USD), su fecha y fuente oficial. Vuelve a `carga` o `revisor`, abre **Evaluación**, inicia la auditoría y espera a que termine el panel en vivo. Luego abre **Revisión** para ver resultados y evidencia.
5. Cierra sesión y entra como `revisor`. Abre el mismo proyecto: puede evaluar y registrar dictámenes, pero no verá la creación de proyectos, la carga de archivos ni los controles de tasa BCV y estado.
6. Cierra sesión y entra como `aprobador`. Además de evaluar y dictaminar, puede actualizar la tasa BCV, fecha, fuente y estado. Cambiar la tasa invalida la comparación anterior y requiere volver a evaluar.
7. Cierra sesión y entra como `lectura`. Puede consultar proyectos, informes y proveedores, pero no verá botones para crear, cargar, evaluar, dictaminar ni cambiar la tasa/estado.

Los valores `CAMBIA_ESTA_CLAVE` son marcadores: reemplázalos por contraseñas diferentes antes de iniciar. Las acciones también se verifican en el backend; no dependas solo de que un botón esté oculto.

Los archivos se cifran con AES-256-GCM y se autentican mediante el identificador de registro como dato asociado. La bitácora guarda eventos humanos y de evaluación en registros append-only; la identidad y permisos provienen de `APP_USERS_JSON`.

## Cómo indicarme cambios de pantallas frontend

Cuando quieras que adapte una pantalla, envíame:

1. **Nombre de la pantalla**: por ejemplo, “Dashboard” o “Revisión de propuestas”.
2. **Captura**: adjunta una imagen completa; si hay una zona puntual, añade otra captura acercada. Oculta claves, nombres privados y datos sensibles.
3. **Ruta y estado**: indica la URL o pestaña, el rol con el que la ves y si hay datos cargados.
4. **Acción**: describe qué haces antes de verla (clics, selección, carga o envío de formulario).
5. **Resultado deseado**: señala qué debe cambiar y qué debe permanecer igual; incluye texto exacto si corresponde.
6. **Prioridad**: visual, interacción, validación, responsive o accesibilidad.

Ejemplo: “En `Revisión`, con rol Revisor, quiero que el motivo de descarte y la página de evidencia se vean en columnas separadas; no cambies el orden del ranking.” Si puedes, incluye también el tamaño de pantalla (por ejemplo, 1440×900 o móvil).
