# Observatorio aéreo

Comparación de Málaga, Sevilla, Granada-Jaén, Almería, Jerez, Córdoba, Gibraltar, Madrid y Barcelona.

**Web:** https://JoseHino.github.io/observatorio-aereo/

## Vistas

- Comparativa mensual: pasajeros, operaciones, carga, variación interanual y evolución absoluta o índice base 100.
- Estacionalidad: peso de cada mes en años completos y comparación acumulada con igual número de meses.
- Detalle: rutas británicas, países socios europeos, nacional/internacional y llegadas/salidas de Gibraltar.
- Fuentes, cobertura por aeropuerto y descarga CSV.

## Fuentes y límites

1. [Aena](https://www.aena.es/es/estadisticas/informes-mensuales.html): PDF mensual, tabla de pasajeros, operaciones y mercancías. Desde enero de 2023.
2. [Gibraltar Airport](https://gibraltarairport.gi/about-us/air-traffic-statistics): PDF anual con meses, llegadas/salidas, movimientos y carga/correo/mensajería. La carga no tiene exactamente el mismo perímetro que Aena.
3. [Eurostat](https://ec.europa.eu/eurostat/web/transport/database): API JSON-stat, `avia_paoac` (solo países socios declarantes europeos, no todos los países del mundo) y `avia_paoa` (nacional/internacional). `freq=M`, `unit=PAS`, `tra_meas=PAS_CRD`, `rep_airp=ES_<ICAO>`; en el segundo, `schedule=TOTAL`. Se excluyen agregados UE para evitar doble cómputo.
4. [UK CAA](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/): tabla 12.1 CSV, conexiones con Reino Unido, desde 2024. Son una parte del tráfico, no una segunda población para sumar. La CAA exige atribución y restringe la reventa de sus estadísticas; se conservan los enlaces originales.

Cada fila conserva su URL. Pasajeros significa movimientos, no personas únicas ni turistas. Las operaciones incluyen aviación no comercial. País del vuelo no es nacionalidad. No se estima ocupación con pasajeros/operaciones. Los datos ausentes no se convierten en cero ni se reconstruyen a partir de porcentajes redondeados. Los informes pueden revisarse.

La comparación utiliza el último mes común de los aeropuertos elegidos. Los desgloses muestran su propio último mes, sin sobrepasar el corte seleccionado. Los años parciales no se anualizan. Los datos completos por compañía/destino de Aena requieren registro y no están integrados.

## Actualización y publicación

GitHub Actions ejecuta `.github/workflows/update.yml` diariamente a las **07:20 UTC** (09:20 en horario de verano peninsular; 08:20 en invierno), y puede iniciarse manualmente en Actions. GitHub puede retrasar la ejecución programada. Funciona con el ordenador apagado, sin claves privadas de datos ni servicios de pago.

Descarga fuentes públicas, valida, conserva el histórico anterior en incidencias parciales, recompila y despliega GitHub Pages. Un fallo de validación/compilación impide reemplazar la publicación. Las advertencias se muestran en los registros y en la cobertura. La caché histórica caduca en 30 días para incorporar revisiones. GitHub puede desactivar ejecuciones programadas de repositorios públicos tras 60 días sin actividad; las actualizaciones guardadas generan actividad, y se puede reactivar el workflow en Actions si fuera necesario.

## Desarrollo

Node 24 y Python 3.12+:

```bash
pip install -r pipeline/requirements.txt
python pipeline/refresh.py
node pipeline/check-data.mjs
npm ci
npm run build
python -m http.server 4187 --bind 127.0.0.1 --directory dist
```

`src/content/dashboard/` contiene la interfaz, `src/data.json` la instantánea y `pipeline/refresh.py` los adaptadores oficiales. La compilación en GitHub utiliza el código fuente del mismo runtime y comprueba su integridad. No necesita el plugin local de creación. No se publican credenciales, cachés ni rutas privadas de la máquina.
