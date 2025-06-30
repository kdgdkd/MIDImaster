# MIDImaster

MIDImaster es una herramienta de línea de comandos con interfaz de usuario en terminal (TUI) diseñada para ser un maestro de MIDI Beat Clock flexible y configurable. Permite enviar señales de reloj MIDI a múltiples salidas, y controlar el tempo (BPM) y el transporte (Play/Pause/Stop) de forma interactiva o remota a través de mensajes MIDI u OSC.

## Características Principales

- **Generador de MIDI Beat Clock:** Envía mensajes clock, start, stop, y continue a los puertos MIDI de salida seleccionados.

- **Integración OSC (Open Sound Control):**
  
  - Recibe comandos de transporte y BPM a través de la red.
  
  - Envía actualizaciones de estado y BPM a otras aplicaciones compatibles con OSC.

- **Control Interactivo de BPM:**
  
  - Ajuste de BPM mediante entrada numérica directa (ej: 120).
  
  - Incremento/decremento de BPM con teclas + y -.
  
  - Bloqueo de BPM para evitar cambios accidentales.

- **Controles de Transporte:**
  
  - Play, Pause, Stop mediante atajos de teclado.

- **Gestión de Puertos MIDI:**
  
  - Selector interactivo para puertos de salida MIDI físicos.
  
  - Soporte para creación de puertos MIDI virtuales de salida.
  
  - Listado de puertos MIDI disponibles.

- **Mapeo de MIDI Entrante Basado en Reglas:**
  
  - Carga de archivos de reglas JSON desde el directorio rules_midimaster/.
  
  - Mapeo de mensajes MIDI entrantes (Note, CC, etc.) a acciones internas como Play, Stop y cambios de BPM.

- **Configuración Centralizada:**
  
  - Un archivo principal midimaster.conf.json para ajustes globales como el BPM por defecto y la configuración de red OSC.

- **Interfaz de Usuario en Terminal (TUI):**
  
  - Muestra el estado actual (puertos de salida, estado del reloj, BPM).
  
  - Proporciona retroalimentación para las acciones del usuario.
  
  - Construida con prompt_toolkit.

## Requisitos

- Python 3.6+

- Bibliotecas de Python:
  
  - mido (para comunicación MIDI)
  
  - prompt_toolkit (para la interfaz de usuario en terminal)
  
  - python-osc (para Open Sound Control)

- **Para puertos MIDI virtuales:**
  
  - **Windows:** Un driver de loopback MIDI como [loopMIDI](https://www.google.com/url?sa=E&q=https%3A%2F%2Fwww.tobias-erichsen.de%2Fsoftware%2Floopmidi.html).
  
  - **macOS:** El "IAC Driver" integrado (se activa en "Configuración de Audio MIDI").
  
  - **Linux:** El módulo de kernel snd-virmidi.

## Instalación

1. **Clona el repositorio o descarga midimaster.py**.

2. **Instala las dependencias:**
   
   ```
   pip install mido prompt_toolkit python-osc
   ```
   
   

3. **Crea el archivo de configuración principal (opcional):**  
   Crea un archivo llamado midimaster.conf.json en el mismo directorio que el script. Si no se encuentra, MIDImaster usará valores por defecto internos.
   
   ```
   {
    "general_settings": {
      "default_bpm": 120.0,
      "default_virtual_port_name": "midimaster_OUT"
    },
    "osc_configuration": {
      "enabled": true,
      "listen_ip": "0.0.0.0",
      "listen_port": 8000,
      "send_ip": "127.0.0.1",
      "send_port": 9000
    }
   }
   ```
   
   

4. **Crea el directorio de reglas (opcional):**  
   Para usar mapeos MIDI, crea una carpeta llamada rules_midimaster:
   
   ```
   mkdir rules_midimaster
   ```
   
   

## Uso

### Ejecución Básica

Para iniciar MIDImaster:

```
python midimaster.py
```



Al iniciar, si hay puertos MIDI de salida físicos disponibles, se te presentará un selector interactivo para elegir a dónde enviar el reloj.

### Argumentos de Línea de Comandos

- python midimaster.py [nombre_archivo_reglas]
  
  - Carga un archivo de reglas específico desde el directorio rules_midimaster/. No incluyas la extensión .json.
  
  - Ejemplo: python midimaster.py mi_setup cargará rules_midimaster/mi_setup.json.

- --virtual-ports
  
  - Crea un puerto MIDI de salida virtual. Su nombre se define con default_virtual_port_name en midimaster.conf.json o con el argumento --vp-out.

- --vp-out NOMBRE
  
  - Especifica un nombre personalizado para el puerto de salida virtual, sobreescribiendo el del archivo de configuración.
  
  - Ejemplo: python midimaster.py --virtual-ports --vp-out "MiClockVirtual"

- --list-ports
  
  - Muestra todos los puertos MIDI de entrada y salida disponibles y luego sale.

### Controles Interactivos en la TUI

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

## Integración OSC

MIDImaster puede enviar y recibir mensajes OSC si está activado en midimaster.conf.json.

### Comandos Entrantes (Escucha)

MIDImaster escucha los siguientes mensajes OSC. La IP y el puerto se definen con listen_ip y listen_port.

- **/midimaster/play**: Inicia el reloj (o continúa si está en pausa).

- **/midimaster/pause**: Pausa el reloj si está en marcha.

- **/midimaster/stop**: Detiene el reloj.

- **/midimaster/bpm/set**: Establece un nuevo BPM.
  
  - **Argumento:** (float) o (int) El nuevo valor de BPM. Ejemplo: 140.0.

### Mensajes Salientes (Envío)

MIDImaster envía los siguientes mensajes OSC para actualizar otras aplicaciones. La IP y el puerto de destino se definen con send_ip y send_port.

- **/midimaster/status**: Se envía cada vez que el estado del transporte cambia.
  
  - **Argumento:** (string) El nuevo estado: "PLAYING", "PAUSED", o "STOPPED".

- **/midimaster/bpm/current**: Se envía cada vez que el BPM cambia.
  
  - **Argumento:** (float) El nuevo valor de BPM.

## Archivos de Configuración

### midimaster.conf.json (Configuración Global)

Este archivo, ubicado en el directorio raíz, controla los ajustes globales.

- **general_settings**:
  
  - default_bpm: El BPM inicial cuando la aplicación arranca.
  
  - default_virtual_port_name: El nombre por defecto para el puerto de --virtual-ports.

- **osc_configuration**:
  
  - enabled: true o false para activar/desactivar toda la funcionalidad OSC.
  
  - listen_ip: La dirección IP para escuchar comandos entrantes (ej: "0.0.0.0" para escuchar en todas las interfaces de red).
  
  - listen_port: El puerto para los comandos entrantes.
  
  - send_ip: La dirección IP de destino para los mensajes de estado salientes.
  
  - send_port: El puerto de destino para los mensajes salientes.

### rules_midimaster/*.json (Archivos de Reglas)

Estos archivos definen mapeos específicos de MIDI y pueden sobreescribir algunos ajustes globales para la sesión.

- **clock_settings**:
  
  - default_bpm (opcional): Establece el BPM inicial, sobreescribiendo el valor de midimaster.conf.json cuando se carga este archivo de reglas.

- **input_mappings**:
  
  - Una lista de objetos, cada uno definiendo cómo un mensaje MIDI entrante dispara una acción.
  
  - Campos principales: device_in, event_in, action.
  
  - Para una descripción detallada de los mapeos, consulta el ejemplo en la versión en inglés o los archivos de ejemplo.

## Solución de Problemas

- **"No hay puertos MIDI de salida físicos disponibles."**: Asegúrate de que tus dispositivos MIDI estén conectados y reconocidos por el sistema operativo antes de iniciar MIDImaster.

- **"Error abriendo puerto virtual..."**: Verifica que tienes un backend de MIDI virtual funcionando (loopMIDI, IAC Driver, etc.).

- **Los comandos OSC no se reciben**:
  
  - Asegúrate de que enabled esté en true en la sección osc_configuration de midimaster.conf.json.
  
  - Revisa el firewall de tu sistema. Puede que necesites crear una regla para permitir que Python o específicamente el puerto listen_port (ej: 8000) reciba conexiones.
  
  - Verifica que la IP y el puerto en tu aplicación emisora coinciden con listen_ip y listen_port en midimaster.conf.json.

- **Los mapeos de entrada no funcionan**:
  
  - Verifica que el alias en device_in es correcto y que el substring coincide con el nombre real del puerto (visible con --list-ports).
  
  - Usa un monitor MIDI para verificar los mensajes que envía tu dispositivo (canal, nota/CC, etc.).

- **La TUI se ve extraña o no responde**: Podría ser un problema de compatibilidad con tu terminal. Intenta con otra terminal o asegúrate de que prompt_toolkit está actualizado.

## Contribuciones

Las contribuciones, ideas y reportes de errores son bienvenidos. Por favor, abre un "issue" en el repositorio de GitHub.
