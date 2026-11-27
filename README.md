# Propuesta Servicios — Venezuela INNOVA 2026

Aplicación para recibir y auditar propuestas de adquisición de equipos, con un motor de lote autónomo en `agent/`. El motor no importa módulos de `app/` ni usa SQLite.

## Requisitos

- Python 3.10 o superior
- Una clave de Gemini para extraer PDF/imágenes y buscar precios; XLSX y validaciones determinísticas funcionan sin ella
- Variables de entorno configuradas para las cuentas web y cifrado antes de cargar archivos

No hay cuentas ni contraseñas predeterminadas en el proyecto: los usuarios se crean mediante `APP_USERS_JSON`.

## Instalación en Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configura Gemini si vas a extraer PDF o imágenes y ejecutar la investigación de precios:

```powershell
$env:GEMINI_API_KEY = "TU_CLAVE"
```

Genera claves locales de cifrado y sesión. Conserva estas claves seguras: perder la clave AES impide descifrar los archivos guardados.

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:APP_ENCRYPTION_KEY = [Convert]::ToBase64String($bytes)
$sessionBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($sessionBytes)
$env:APP_SESSION_SECRET = [Convert]::ToBase64String($sessionBytes)
```

`APP_USERS_JSON` contiene cuentas y roles. Configura contraseñas propias, no uses el ejemplo literalmente:

```powershell
$env:APP_USERS_JSON = '{"carga":{"password":"CAMBIAR","role":"Carga"},"revision":{"password":"CAMBIAR","role":"Revisor"},"aprobacion":{"password":"CAMBIAR","role":"Aprobador"},"consulta":{"password":"CAMBIAR","role":"Solo lectura"}}'
```

Variables opcionales:

- `APP_DATA_DIR`: directorio de base SQLite y archivos cifrados (predeterminado: `data`).
- `DATABASE_URL`: URL SQLAlchemy para sustituir SQLite.
- `REPOSITORY_URL`: valor para `repositorio` del JSON de lote cuando no hay remoto Git.
- `COOKIE_SECURE=1`: marca la cookie como Secure cuando se sirve detrás de HTTPS.

## Ejecutar y validar

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

Los fallos de lectura o extracción se registran como propuestas descartadas; no se sustituyen con precios ni contenido ficticios. El coste de mercado se consulta con Google Search Grounding y se cachea por componente y día. La búsqueda no decide por sí sola el descarte o ranking.

El archivo `validador_salida.html` implementa un validador local del contrato indicado en estas instrucciones (claves exactas, tipos, timestamps `-04:00` y ranking sin duplicados). No se proporcionó el validador oficial original, por lo que este archivo no se presenta como copia oficial.

## Aplicación web

Con las variables de entorno anteriores:

```powershell
uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000/login`. Crea un proyecto desde el panel, carga un PDF de proyecto y entre 3 y 20 propuestas. Luego usa las pestañas **Recepción**, **Evaluación** y **Revisión**. El informe se puede imprimir a PDF desde el navegador y también exportar a CSV. La tasa BCV requiere rol Aprobador y registra valor, fecha y fuente.

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
