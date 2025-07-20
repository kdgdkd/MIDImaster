#!/bin/bash

# ==============================================================================
# vmidi-sets.sh - Script para gestionar CONJUNTOS de puertos MIDI virtuales.
#
# Crea múltiples tarjetas MIDI virtuales, cada una con su propio nombre y
# número de puertos, según la configuración hardcodeada en este script.
#
# Requiere privilegios de superusuario (ejecutar con sudo).
# ==============================================================================

# --- Comprobación de Privilegios ---
if [ "$EUID" -ne 0 ]; then
  echo "Este script necesita privilegios de superusuario. Por favor, ejecútalo con sudo."
  echo "Ejemplo: sudo ./vmidi-sets.sh start"
  exit 1
fi

# --- CONFIGURACIÓN DE PUERTOS ---
# Define aquí los conjuntos de puertos que quieres crear.
# Formato: ["Nombre de la Tarjeta"]=numero_de_puertos
# Puedes añadir, modificar o eliminar las líneas según tus necesidades.
declare -A VMIDI_SETS=(
    ["CLOCK"]=1          # 4 puertos para conectar a tu DAW
    ["TPT"]=1         # 8 puertos para un rack de sintetizadores virtuales
    ["MIDItema"]=2    # 2 puertos para superficies de control
)

# --- Función de Ayuda / Uso ---
usage() {
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos:"
    echo "  start    Crea todos los conjuntos de puertos MIDI definidos en el script."
    echo "  stop     Destruye TODOS los puertos MIDI virtuales."
    echo "  status   Muestra el estado actual de los puertos virtuales."
    echo ""
    echo "La configuración de los puertos se gestiona directamente editando la sección"
    echo "'VMIDI_SETS' dentro de este archivo."
}

# --- Lógica Principal del Script ---
COMMAND=$1

case $COMMAND in
    start)
        # Comprueba si el módulo ya está cargado para evitar errores
        if lsmod | grep -q "snd_virmidi"; then
            echo "¡Error! Los puertos MIDI virtuales ya están activos."
            echo "Usa 'sudo $0 stop' primero si quieres reconfigurarlos."
            exit 1
        fi

        echo "Creando conjuntos de puertos MIDI virtuales..."
        
        card_index=0
        for name in "${!VMIDI_SETS[@]}"; do
            num_ports="${VMIDI_SETS[$name]}"
            card_name="$name"
            
            echo "  -> Creando tarjeta ${card_index}: \"${card_name}\" con ${num_ports} puertos..."
            
            # Carga una instancia del módulo con un índice y nombre de tarjeta únicos
            modprobe snd-virmidi index=${card_index} midi_devs=${num_ports} card_name="${card_name}"
            
            # Incrementa el índice para la siguiente tarjeta
            ((card_index++))
        done

        echo ""
        echo "¡Todos los conjuntos de puertos han sido creados con éxito!"
        echo "Estado actual:"
        aconnect -l | grep 'client'
        ;;

    stop)
        # Comprueba si el módulo está cargado antes de intentar detenerlo
        if ! lsmod | grep -q "snd_virmidi"; then
            echo "Los puertos MIDI virtuales no están activos. No hay nada que detener."
            exit 0
        fi

        echo "Destruyendo todos los puertos MIDI virtuales..."
        # El comando -r elimina todas las instancias del módulo
        modprobe -r snd-virmidi
        echo "¡Puertos destruidos con éxito!"
        ;;

    status)
        if lsmod | grep -q "snd_virmidi"; then
            echo "Los puertos MIDI virtuales están ACTIVOS."
            echo "---"
            aconnect -l | grep 'client'
        else
            echo "Los puertos MIDI virtuales están INACTIVOS."
        fi
        ;;

    *)
        # Si el comando no es válido, muestra la ayuda
        usage
        exit 1
        ;;
esac

exit 0