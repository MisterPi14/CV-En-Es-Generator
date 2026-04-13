#!/usr/bin/env bash
# Administra el entorno virtual del proyecto con dos casos:
# 1) Si el venv no existe o faltan dependencias -> lo crea (si falta) e instala requirements.
# 2) Si el venv existe y todas las dependencias ya están instaladas -> solo lo activa.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_HOME="${HOME}/.python-envs"
ENV_NAME="cvtranslator"
ENV_PATH="${ENV_HOME}/${ENV_NAME}"
REQ_FILE="${PROJECT_ROOT}/requirements.txt"

log() { printf "[setup_env] %s\n" "$*"; }
err() { printf "[setup_env][ERROR] %s\n" "$*" >&2; }

if ! command -v python &>/dev/null; then
  err "Python no está en el PATH. Instálalo o añade al PATH antes de continuar."; exit 1
fi

mkdir -p "${ENV_HOME}"

NEED_INSTALL=0
if [ ! -d "${ENV_PATH}" ]; then
  log "El entorno no existe. Se creará en: ${ENV_PATH}"
  python -m venv "${ENV_PATH}"
  NEED_INSTALL=1
else
  log "Entorno encontrado: ${ENV_PATH}"
  if [ ! -f "${REQ_FILE}" ]; then
    err "No se encontró requirements.txt en ${REQ_FILE}"; exit 1
  fi
  # Verificar dependencias
  PYTHON_BIN="${ENV_PATH}/bin/python"
  [ -f "${PYTHON_BIN}" ] || PYTHON_BIN="${ENV_PATH}/Scripts/python.exe"
  if [ ! -f "${PYTHON_BIN}" ]; then
    err "No se encontró ejecutable de Python dentro del entorno. Borrar el venv y reintentar."; exit 1
  fi
  MISSING=()
  while IFS= read -r line; do
    req="${line%%#*}"               # quitar comentarios inline
    req="${req%%;*}"                 # quitar markers
    req="$(echo "$req" | xargs)"    # trim
    [ -z "$req" ] && continue
    pkg="${req%%[<>=!~]*}"           # nombre base
    if ! "${PYTHON_BIN}" -m pip show "$pkg" >/dev/null 2>&1; then
      MISSING+=("$req")
    fi
  done < "${REQ_FILE}"
  if [ ${#MISSING[@]} -gt 0 ]; then
    log "Faltan dependencias: ${MISSING[*]}"
    NEED_INSTALL=1
  else
    log "Todas las dependencias ya están satisfechas. Solo se activará el entorno."
  fi
fi

# Ruta de activación preferida (Git Bash en Windows prioriza Scripts si existe)
if [ -f "${ENV_PATH}/Scripts/activate" ]; then
  ACTIVATE_PATH="${ENV_PATH}/Scripts/activate"
elif [ -f "${ENV_PATH}/bin/activate" ]; then
  ACTIVATE_PATH="${ENV_PATH}/bin/activate"
else
  err "No se encontró script de activación (bin/activate o Scripts/activate)."; exit 1
fi

# shellcheck source=/dev/null
source "${ACTIVATE_PATH}"

if [ "$NEED_INSTALL" -eq 1 ]; then
  log "Actualizando pip/setuptools/wheel"
  python -m pip install --upgrade pip setuptools wheel
  log "Instalando dependencias de requirements.txt"
  pip install -r "${REQ_FILE}"
  log "Instalación completa. Entorno activo."
else
  log "Entorno activado sin reinstalar dependencias."
fi

log "Para reusar: source ${ACTIVATE_PATH}"
log "Para generar PDFs: python build.py"
