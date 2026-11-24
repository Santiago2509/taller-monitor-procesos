#!/usr/bin/env python3
"""
Monitor de procesos — Taller de Sistemas Operativos
Herramienta tipo "top" construida leyendo directamente /proc.

Fuentes de información del kernel:
  /proc/<pid>/status  -> Nombre, Estado, PID, PPid, hilos, memoria (VmRSS)
  /proc/<pid>/stat    -> utime, stime (tiempo de CPU) y campo 39 "processor"
                         (último núcleo donde el planificador ejecutó el proceso)
  /proc/stat          -> tiempos acumulados de CPU, total y por cada núcleo
  /proc/loadavg       -> carga promedio del sistema

Uso:
  python3 monitor.py            # modo en vivo (refresca cada 1 s)
  python3 monitor.py --once     # imprime un solo listado y termina
  python3 monitor.py -n 30 -i 2 # 30 procesos, refresco cada 2 s
"""

import argparse
import os
import shutil
import sys
import time

CLK_TCK = os.sysconf(os.sysconf_names["SC_CLK_TCK"])  # ticks por segundo

ESTADOS = {
    "R": "Ejecución",
    "S": "Espera (interrumpible)",
    "D": "Espera (disco/IO)",
    "Z": "Zombie",
    "T": "Detenido",
    "t": "Traza (detenido)",
    "I": "Inactivo (kernel)",
    "X": "Muerto",
}

# Colores ANSI
RST = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GRN = "\033[32m"
YEL = "\033[33m"
CYN = "\033[36m"
REV = "\033[7m"


# ----------------------------------------------------------------------------
# Lectura de /proc
# ----------------------------------------------------------------------------
def listar_pids():
    """Cada carpeta numérica dentro de /proc es un proceso."""
    return [int(d) for d in os.listdir("/proc") if d.isdigit()]


def leer_status(pid):
    """Lee /proc/<pid>/status y devuelve un dict clave -> valor."""
    datos = {}
    with open(f"/proc/{pid}/status") as f:
        for linea in f:
            clave, _, valor = linea.partition(":")
            datos[clave] = valor.strip()
    return datos


def leer_stat(pid):
    """Lee /proc/<pid>/stat. Devuelve (ticks_cpu, nucleo).

    El nombre (campo 2) va entre paréntesis y puede tener espacios, por eso se
    corta desde el último ')'. Tras ese corte, campos[0] es el campo 3 (state).
      campo 14 utime  -> campos[11]
      campo 15 stime  -> campos[12]
      campo 39 processor -> campos[36]
    """
    with open(f"/proc/{pid}/stat") as f:
        contenido = f.read()
    campos = contenido[contenido.rfind(")") + 2:].split()
    ticks = int(campos[11]) + int(campos[12])
    nucleo = int(campos[36])
    return ticks, nucleo


def leer_cpus():
    """Lee /proc/stat. Devuelve dict {'cpu': (total, ocupado), 'cpu0': ...}."""
    cpus = {}
    with open("/proc/stat") as f:
        for linea in f:
            if not linea.startswith("cpu"):
                break
            partes = linea.split()
            valores = list(map(int, partes[1:]))
            # user nice system idle iowait irq softirq steal ...
            inactivo = valores[3] + valores[4]
            total = sum(valores[:8])
            cpus[partes[0]] = (total, total - inactivo)
    return cpus


def leer_procesos():
    """Recorre /proc y arma la información de cada proceso."""
    procesos = {}
    for pid in listar_pids():
        try:
            st = leer_status(pid)
            ticks, nucleo = leer_stat(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
            continue  # el proceso terminó mientras lo leíamos
        estado = st.get("State", "? (?)")
        letra = estado[0]
        procesos[pid] = {
            "pid": pid,
            "ppid": st.get("PPid", "?"),
            "nombre": st.get("Name", "?"),
            "letra": letra,
            "estado": ESTADOS.get(letra, estado),
            "hilos": st.get("Threads", "?"),
            "rss_kb": int(st.get("VmRSS", "0 kB").split()[0]),
            "ticks": ticks,
            "nucleo": nucleo,
        }
    return procesos


# ----------------------------------------------------------------------------
# Cálculos entre dos muestras
# ----------------------------------------------------------------------------
def uso_cpus(antes, ahora):
    uso = {}
    for nombre, (total, ocupado) in ahora.items():
        t0, o0 = antes.get(nombre, (0, 0))
        dt = total - t0
        uso[nombre] = 100.0 * (ocupado - o0) / dt if dt > 0 else 0.0
    return uso


def uso_procesos(antes, ahora, segundos):
    for pid, p in ahora.items():
        prev = antes.get(pid)
        if prev and segundos > 0:
            p["cpu"] = 100.0 * (p["ticks"] - prev["ticks"]) / CLK_TCK / segundos
        else:
            p["cpu"] = 0.0
    return ahora


# ----------------------------------------------------------------------------
# Presentación
# ----------------------------------------------------------------------------
def barra(pct, ancho):
    llenos = int(round(pct / 100 * ancho))
    llenos = max(0, min(ancho, llenos))
    color = GRN if pct < 50 else (YEL if pct < 85 else RED)
    return f"{color}{'|' * llenos}{RST}{' ' * (ancho - llenos)}"


def pintar(uso, procesos, n_filas, color=True):
    cols = shutil.get_terminal_size((100, 30)).columns
    lineas = []
    with open("/proc/loadavg") as f:
        carga = " ".join(f.read().split()[:3])

    total_proc = len(procesos)
    en_ejec = sum(1 for p in procesos.values() if p["letra"] == "R")
    lineas.append(f"{BOLD}MONITOR DE PROCESOS (/proc){RST}   "
                  f"{time.strftime('%H:%M:%S')}   "
                  f"Procesos: {total_proc}  En ejecución: {en_ejec}   "
                  f"Carga promedio: {carga}")
    lineas.append("")

    # --- Uso por núcleo ---
    nucleos = sorted((k for k in uso if k != "cpu"), key=lambda k: int(k[3:]))
    ancho_barra = max(10, min(40, cols // 2 - 18))
    lineas.append(f"{BOLD}Reparto de carga por núcleo (desde /proc/stat){RST}")
    for i in range(0, len(nucleos), 2):
        fila = ""
        for k in nucleos[i:i + 2]:
            fila += f"  {k:>5} [{barra(uso[k], ancho_barra)}] {uso[k]:5.1f}%"
        lineas.append(fila)
    lineas.append(f"  {'TOTAL':>5} [{barra(uso['cpu'], ancho_barra)}] {uso['cpu']:5.1f}%")
    lineas.append("")

    # --- Procesos por núcleo (cuántos procesos ejecutándose en cada CPU) ---
    por_nucleo = {}
    for p in procesos.values():
        if p["cpu"] > 1.0:
            por_nucleo.setdefault(p["nucleo"], []).append(p["nombre"])
    if por_nucleo:
        resumen = "  ".join(f"CPU{n}:{len(v)}" for n, v in sorted(por_nucleo.items()))
        lineas.append(f"{BOLD}Procesos activos (>1% CPU) por núcleo:{RST} {resumen}")
        lineas.append("")

    # --- Tabla de procesos ---
    encabezado = f"{'PID':>7} {'PPID':>7} {'NOMBRE':<18} {'ESTADO':<24} {'CPU#':>4} {'%CPU':>6} {'MEM(MB)':>8} {'HILOS':>5}"
    lineas.append(f"{REV}{encabezado.ljust(cols - 1)}{RST}")
    orden = sorted(procesos.values(), key=lambda p: (p["cpu"], p["rss_kb"]), reverse=True)
    for p in orden[:n_filas]:
        c = GRN if p["letra"] == "R" else (RED if p["letra"] in "ZD" else "")
        lineas.append(
            f"{p['pid']:>7} {p['ppid']:>7} {p['nombre'][:18]:<18} "
            f"{c}{(p['letra'] + ' ' + p['estado'])[:24]:<24}{RST if c else ''} "
            f"{p['nucleo']:>4} {p['cpu']:>6.1f} {p['rss_kb'] / 1024:>8.1f} {p['hilos']:>5}"
        )
    lineas.append("")
    lineas.append(f"{CYN}Ctrl+C para salir.  CPU# = núcleo donde el planificador ejecutó el proceso por última vez.{RST}")

    texto = "\n".join(lineas)
    if not color:
        import re
        texto = re.sub(r"\033\[[0-9;]*m", "", texto)
    return texto


def main():
    ap = argparse.ArgumentParser(description="Monitor de procesos leyendo /proc")
    ap.add_argument("-n", type=int, default=20, help="número de procesos a mostrar")
    ap.add_argument("-i", type=float, default=1.0, help="intervalo de refresco (s)")
    ap.add_argument("--once", action="store_true", help="mostrar una sola vez y salir")
    args = ap.parse_args()

    if not os.path.exists("/proc/stat"):
        sys.exit("Este programa necesita Linux (sistema de archivos /proc).")

    cpus_antes, procs_antes, t_antes = leer_cpus(), leer_procesos(), time.time()
    time.sleep(0.5 if args.once else args.i)

    try:
        while True:
            cpus_ahora, procs_ahora, t_ahora = leer_cpus(), leer_procesos(), time.time()
            uso = uso_cpus(cpus_antes, cpus_ahora)
            procs = uso_procesos(procs_antes, procs_ahora, t_ahora - t_antes)
            salida = pintar(uso, procs, args.n, color=sys.stdout.isatty())
            if args.once:
                print(salida)
                return
            sys.stdout.write("\033[H\033[2J" + salida + "\n")
            sys.stdout.flush()
            cpus_antes, procs_antes, t_antes = cpus_ahora, procs_ahora, t_ahora
            time.sleep(args.i)
    except KeyboardInterrupt:
        print("\nMonitor finalizado.")


if __name__ == "__main__":
    main()
