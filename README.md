# Tribbu · Dashboard Agentes Live

Dashboard en tiempo real del rendimiento de agentes desde Intercom.

## Deploy en Railway (5 minutos)

### 1. Sube el código a GitHub
```bash
git init
git add .
git commit -m "Tribbu dashboard"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/tribbu-dashboard.git
git push -u origin main
```

### 2. Despliega en Railway
1. Ve a [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Selecciona tu repositorio
3. Railway detectará Python automáticamente

### 3. Añade la variable de entorno
En Railway → tu proyecto → Variables → Add:
```
INTERCOM_TOKEN = TU_TOKEN_AQUI
```

### 4. Consigue la URL
Railway te dará una URL tipo: `https://tribbu-dashboard-production.up.railway.app`

### 5. Actualiza el dashboard HTML
En `dashboard.html`, línea ~200, cambia:
```javascript
const API_BASE = ... 'RAILWAY_URL_AQUI'
```
Por tu URL de Railway.

### 6. Abre el HTML en el navegador
¡Listo! Selecciona fechas y pulsa Actualizar.

## Endpoints

- `GET /api/agents?date_from=2026-05-07&date_to=2026-05-07` → datos de agentes
- `GET /health` → comprueba que el servidor está vivo

## Estructura

```
tribbu-dashboard/
├── main.py          # FastAPI backend
├── dashboard.html   # Frontend (abre en navegador)
├── requirements.txt
├── railway.json
└── Procfile
```
