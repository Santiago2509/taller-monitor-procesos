# Taller — Monitor de procesos

Herramienta tipo `top` escrita en Python que lee directamente el sistema de archivos `/proc` de Linux.

## Qué muestra

| Dato | De dónde sale |
|---|---|
| PID, PPID, nombre, estado, hilos, memoria | `/proc/<pid>/status` |
| % de CPU de cada proceso | `/proc/<pid>/stat` (campos 14 `utime` + 15 `stime`, comparados entre dos muestras) |
| **CPU#**: núcleo donde el planificador ejecutó el proceso por última vez | `/proc/<pid>/stat` (campo 39 `processor`) |
| Uso de cada núcleo (barras) | `/proc/stat` (líneas `cpu0`, `cpu1`, ...) |
| Carga promedio | `/proc/loadavg` |

Cada carpeta numérica de `/proc` es un proceso; el programa recorre todas, lee su `status` y su `stat`, espera un intervalo, vuelve a leer y calcula los porcentajes con la diferencia.

## Cómo ejecutarlo (Linux / WSL / máquina virtual)

```bash
python3 monitor.py            # modo en vivo, refresca cada 1 s
python3 monitor.py --once     # un solo listado
python3 monitor.py -n 30 -i 2 # 30 procesos, refresco cada 2 s
```

## Prueba de estrés (para la captura)

Terminal 1:
```bash
python3 monitor.py
```

Terminal 2:
```bash
sudo apt install -y stress-ng
stress-ng --cpu 4 --timeout 60s
# o bien, sin stress-ng:
chmod +x estresar.sh && ./estresar.sh 60
```

Mientras corre el estrés se observa:
- Las barras de los núcleos suben a ~100 %.
- Aparecen procesos `stress-ng-cpu` (o `yes`) arriba de la tabla con ~100 % de CPU y estado `R Ejecución`.
- La columna **CPU#** muestra que el planificador reparte cada proceso en un núcleo distinto (y a veces los migra entre núcleos).

Para detener la alternativa con `yes`: `killall yes`.
