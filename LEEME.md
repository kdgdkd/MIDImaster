# MIDImaster

MIDImaster is a flexible MIDI clock in python, allowing for external control

```
# MIDImaster

MIDImaster es una herramienta de línea de comandos con interfaz de usuario en terminal (TUI) diseñada para ser un maestro de MIDI Beat Clock flexible y configurable. Permite enviar señales de reloj MIDI a múltiples salidas (físicas y/o virtuales) y controlar el tempo (BPM) y el transporte (Play/Pause/Stop) tanto interactivamente como a través de mensajes MIDI entrantes definidos en archivos de reglas JSON.

## Características Principales

*   **Generador de MIDI Beat Clock:** Envía mensajes `clock`, `start`, `stop`, y `continue` a los puertos MIDI de salida seleccionados.
*   **Control Interactivo de BPM:**
    *   Ajuste de BPM mediante entrada numérica directa (ej: `120`).
    *   Incremento/decremento de BPM con teclas `+` y `-`.
    *   Bloqueo de BPM para evitar cambios accidentales.
*   **Controles de Transporte:**
    *   Play, Pause, Stop mediante atajos de teclado.
*   **Gestión de Puertos MIDI:**
    *   Selector interactivo para puertos de salida MIDI físicos.
    *   Soporte para creación de puertos MIDI virtuales de salida (ideal para enrutar a DAWs u otras aplicaciones en el mismo sistema).
    *   Listado de puertos MIDI disponibles.
*   **Mapeo de MIDI Entrante Basado en Reglas:**
    *   Carga de archivos de configuración JSON desde el directorio `rules_midimaster/`.
    *   Definición de alias para dispositivos MIDI para facilitar la configuración.
    *   Mapeo de mensajes MIDI entrantes (Note On/Off, CC, Program Change, Start, Stop, etc.) desde dispositivos específicos a acciones internas como:
        *   Play, Stop, Pause.
        *   Ajustar BPM (con opción de escalado lineal para mensajes CC).
*   **Interfaz de Usuario en Terminal (TUI):**
    *   Muestra el estado actual (puertos de salida, estado del reloj, BPM).
    *   Proporciona retroalimentación para las acciones del usuario.
    *   Construida con `prompt_toolkit`.
*   **Configuración Persistente (Parcial):**
    *   El BPM por defecto puede establecerse en el archivo de reglas JSON.
    *   El puerto de salida por defecto puede sugerirse desde el archivo de reglas.

## Requisitos

*   Python 3.6+
*   Bibliotecas de Python:
    *   `mido` (para comunicación MIDI)
    *   `prompt_toolkit` (para la interfaz de usuario en terminal)
*   **Para puertos MIDI virtuales:**
    *   **Windows:** Un driver de loopback MIDI como [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
    *   **macOS:** El "IAC Driver" integrado (se activa en "Configuración de Audio MIDI").
    *   **Linux:** El módulo de kernel `snd-virmidi` (generalmente disponible, puede requerir `modprobe snd-virmidi`).

## Instalación

1.  **Clona el repositorio o descarga `midimaster.py`**.
2.  **Instala las dependencias:**
    ```bash    pip install mido prompt_toolkit    ```
3.  **Crea el directorio de reglas (opcional, pero recomendado para usar mapeos):**
    En el mismo directorio donde está `midimaster.py`, crea una carpeta llamada `rules_midimaster`:
    ```bash    mkdir rules_midimaster    ```

## Uso

### Ejecución Básica

Para iniciar MIDImaster:

```bashpython midimaster.py
```



Al iniciar, si hay puertos MIDI de salida físicos disponibles, se te presentará un selector interactivo para elegir a dónde enviar el reloj.

### Argumentos de Línea de Comandos

- python midimaster.py [nombre_archivo_reglas]
  
  - Carga un archivo de reglas específico desde el directorio rules_midimaster/. No incluyas la extensión .json.
  
  - Ejemplo: python midimaster.py my_setup cargará rules_midimaster/my_setup.json.

- --virtual-ports
  
  - Crea un puerto MIDI de salida virtual. Por defecto se llama midimaster_OUT.

- --vp-out NOMBRE
  
  - Especifica un nombre personalizado para el puerto MIDI de salida virtual.
  
  - Ejemplo: python midimaster.py --virtual-ports --vp-out "MiClockVirtual"

- --list-ports
  
  - Muestra todos los puertos MIDI de entrada y salida disponibles y luego sale.

### Controles Interactivos en la TUI

Una vez que MIDImaster está en ejecución:

- **BPM:**
  
  - 0-9: Introduce un nuevo BPM (3 dígitos, ej: 1, 2, 5 para 125 BPM).
  
  - +: Incrementa el BPM en 1.
  
  - -: Decrementa el BPM en 1.
  
  - b: Bloquea/Desbloquea el control de BPM.

- **Transporte:**
  
  - Espacio o c: Alterna entre Play/Pause. Si está en Stop, inicia Play.
  
  - Enter: Si está Detenido (Stopped), inicia Play. Si está en Play o Pausa, Detiene (Stop).
  
  - p: Inicia Play (si no está ya en Play).
  
  - s: Detiene (Stop) el reloj.

- **Salir:**
  
  - q o Esc: Cierra la aplicación.
  
  - Ctrl+C: Cierra la aplicación (interrupción forzada).

### Archivos de Reglas (JSON)

Los archivos de reglas permiten personalizar el comportamiento de MIDImaster, especialmente para el mapeo de MIDI entrante y configuraciones por defecto. Deben ubicarse en el directorio rules_midimaster/ y tener la extensión .json.

La estructura básica de un archivo de reglas es:

```
{
  "device_alias": {
    "mi_controlador": "Arturia KeyStep", // Un alias para un nombre de puerto que contiene "Arturia KeyStep"
    "mi_salida_preferida": "UM-ONE"
  },
  "clock_settings": {
    "default_bpm": 125.0,
    "device_out": "mi_salida_preferida" // Intenta usar este alias como salida por defecto si no se seleccionan puertos interactivamente
  },
  "input_mappings": [
    // Mapeos aquí
  ]
}
```



#### Sección device_alias

Define nombres amigables (alias) para tus dispositivos MIDI. MIDImaster buscará el substring proporcionado en los nombres reales de los puertos MIDI.

- "nombre_alias": "substring_del_nombre_real_del_puerto"

#### Sección clock_settings

Configuraciones relacionadas con el reloj MIDI saliente.

- default_bpm (opcional): Número (int o float). Establece el BPM inicial al cargar el archivo.

- device_out (opcional): String (un alias definido en device_alias o un substring directo). Si no se seleccionan puertos interactivamente y no se usa --virtual-ports exclusivamente, MIDImaster intentará abrir este puerto como salida.

#### Sección input_mappings

Una lista de objetos, cada uno definiendo cómo un mensaje MIDI entrante específico debe disparar una acción en MIDImaster.

Cada objeto de mapeo puede contener:

- device_in: (String, obligatorio) El alias (de device_alias) del puerto MIDI de entrada.

- ch_in: (Integer, opcional, 0-15) El canal MIDI del mensaje entrante. Si se omite, se aplica a cualquier canal.

- event_in: (String, obligatorio) El tipo de mensaje MIDI:
  
  - "note" (cubre note_on y note_off)
  
  - "note_on"
  
  - "note_off"
  
  - "cc" (para control_change)
  
  - "pc" (para program_change)
  
  - "start", "stop", "continue" (mensajes de sistema)
  
  - Otros tipos de Mido (ej: "pitchwheel", "aftertouch")

- value_1_in: (Integer, opcional) El primer valor del mensaje MIDI:
  
  - Para note_on/note_off: número de nota (0-127).
  
  - Para control_change: número de CC (0-127).
  
  - Para program_change: número de programa (0-127).

- action: (String, obligatorio) La acción a realizar:
  
  - "play": Inicia el reloj (o continúa si está en pausa).
  
  - "stop": Detiene el reloj.
  
  - "pause": Pausa el reloj (solo si está en Play).
  
  - "bpm": Ajusta el BPM. Usado típicamente con event_in: "cc".
    
    - Si el event_in es cc, el valor del CC (0-127) se usa directamente como BPM, a menos que se defina bpm_scale.

- bpm_scale: (Objeto, opcional, solo para action: "bpm" y event_in: "cc")  
  Permite escalar el valor del CC entrante a un rango de BPM.
  
  - range_in: (Lista de 2 números, ej: [0, 127]) Rango del valor del CC de entrada.
  
  - range_out: (Lista de 2 números, ej: [60.0, 180.0]) Rango del BPM de salida.

**Ejemplo de input_mappings:**

```
"input_mappings": [
  {
    "device_in": "mi_controlador",
    "event_in": "start",
    "action": "play"
  },
  {
    "device_in": "mi_controlador",
    "event_in": "stop",
    "action": "stop"
  },
  {
    "device_in": "mi_controlador",
    "ch_in": 0, // Canal 1
    "event_in": "note_on",
    "value_1_in": 36, // Nota C2
    "action": "play"
  },
  {
    "device_in": "mi_controlador",
    "ch_in": 0,
    "event_in": "note_on",
    "value_1_in": 37, // Nota C#2
    "action": "stop"
  },
  {
    "device_in": "mi_controlador",
    "ch_in": 9, // Canal 10
    "event_in": "cc",
    "value_1_in": 22, // CC #22
    "action": "bpm",
    "bpm_scale": {
      "range_in": [0, 127],
      "range_out": [80.0, 160.0]
    }
  }
]
```



## Ejemplo Completo de Archivo de Reglas

Nombre del archivo: rules_midimaster/my_live_setup.json

```
{
  "device_alias": {
    "akai_mpk": "MPK mini",
    "focusrite_out": "Focusrite USB MIDI"
  },
  "clock_settings": {
    "default_bpm": 130.0,
    "device_out": "focusrite_out"
  },
  "input_mappings": [
    {
      "device_in": "akai_mpk",
      "event_in": "note_on",
      "ch_in": 15,          // Canal 16
      "value_1_in": 48,     // Nota C3
      "action": "play"
    },
    {
      "device_in": "akai_mpk",
      "event_in": "note_on",
      "ch_in": 15,
      "value_1_in": 49,     // Nota C#3
      "action": "stop"
    },
    {
      "device_in": "akai_mpk",
      "event_in": "cc",
      "ch_in": 0,           // Canal 1
      "value_1_in": 1,      // CC #1 (Modulation wheel)
      "action": "bpm",
      "bpm_scale": {
        "range_in": [0, 127],
        "range_out": [70.0, 190.0]
      }
    }
  ]
}
```



Para usar este archivo:

```
python midimaster.py my_live_setup
```

## Solución de Problemas

- **"No hay puertos MIDI de salida físicos disponibles."**: Asegúrate de que tus dispositivos MIDI estén conectados y reconocidos por el sistema operativo antes de iniciar MIDImaster.

- **"Error abriendo puerto virtual..."**: Verifica que tienes un backend de MIDI virtual funcionando (loopMIDI, IAC Driver, etc.).

- **Los mapeos de entrada no funcionan**:
  
  - Verifica que el alias en device_in coincide con una entrada en device_alias, y que el valor en device_alias es un substring del nombre real del puerto MIDI de entrada (visible con --list-ports).
  
  - Asegúrate de que tu controlador MIDI está enviando en el canal (ch_in) y con los valores (event_in, value_1_in) especificados. Usa un monitor MIDI para verificar los mensajes que envía tu dispositivo.

- **La TUI se ve extraña o no responde**: Podría ser un problema de compatibilidad con tu terminal. Intenta con otra terminal o asegúrate de que prompt_toolkit está actualizado.

## Contribuciones

Las contribuciones, ideas y reportes de errores son bienvenidos. Por favor, abre un "issue" en el repositorio de GitHub.
