#!/usr/bin/env bash
# Genera carga de CPU durante N segundos (por defecto 60) en tantos hilos como núcleos.
# Uso: ./estresar.sh [segundos] [hilos]
SEG=${1:-60}
HILOS=${2:-$(nproc)}

if command -v stress-ng >/dev/null 2>&1; then
    echo "Usando stress-ng: $HILOS hilos durante ${SEG}s"
    stress-ng --cpu "$HILOS" --timeout "${SEG}s"
else
    echo "stress-ng no está instalado; usando 'yes > /dev/null' x $HILOS durante ${SEG}s"
    for _ in $(seq "$HILOS"); do
        timeout "$SEG" yes > /dev/null &
    done
    wait
fi
echo "Estrés finalizado."
