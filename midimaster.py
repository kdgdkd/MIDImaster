# midimaster.py
import mido
import time
import json
import argparse
import traceback
import signal
import os
from pathlib import Path
import sys
import threading

# --- UI Imports ---
from prompt_toolkit import Application, HTML
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings

# --- OSC Imports ---
from pythonosc import dispatcher, osc_server, udp_client

# --- Global Configuration ---
RULES_DIR_NAME = "rules_midimaster"
RULES_DIR = Path(f"./{RULES_DIR_NAME}")
SHUTDOWN_FLAG = False
DEFAULT_BPM = 120.0
PPQN = 24

# --- Performance State ---
class PerformanceState:
    def __init__(self):
        self.status = "STOPPED"
        self.bpm = DEFAULT_BPM # Se actualizará desde JSON si existe
        self.bpm_input_buffer = ""
        self.bpm_locked = False
        self.output_ports = []
        self.virtual_port_name = None
        self.last_feedback_message = ""
        self.feedback_message_time = 0
        self.feedback_message_duration = 3

performance_state = PerformanceState()
midi_clock_thread = None
app_ui_instance = None
bpm_update_signal = threading.Event()

# --- OSC Configuration & State ---
main_config = {}
osc_client = None
osc_server_thread = None

# --- Mapeo de MIDI ---
global_device_aliases = {}
midi_filters = []

# --- Helper Functions ---
def signal_handler(sig, frame):
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True
    if app_ui_instance:
        app_ui_instance.exit(result="shutdown")
    # print("\n[*] Interrupción recibida, cerrando midimaster...") # Se imprime en finally

def find_port_by_substring(ports, sub):
    if not ports or not sub: return None
    for name in ports:
        if sub.lower() in name.lower(): return name
    return None

def _load_json_file_content(filepath: Path):
    if not filepath.is_file():
        print(f"Advertencia: Archivo '{filepath.name}' no encontrado.")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f: content = json.load(f)
        return content
    except json.JSONDecodeError:
        print(f"Error: Archivo '{filepath.name}' no es un JSON válido.")
    except Exception as e:
        print(f"Error inesperado cargando '{filepath.name}': {e}")
    return None

def load_rule_file(fp: Path):
    global global_device_aliases, midi_filters, performance_state
    content = _load_json_file_content(fp)
    if not content or not isinstance(content, dict): return False # Indicar fallo

    devices = content.get("device_alias", {})
    mappings = content.get("midi_filter", [])
    clock_settings = content.get("clock_settings", {}) # Cargar clock_settings

    if isinstance(devices, dict):
        if not global_device_aliases: # Cargar solo los primeros alias definidos
            global_device_aliases.update(devices)
        # else: si ya hay alias, no sobrescribir con los de archivos posteriores (o decidir otra estrategia)
            
    if isinstance(mappings, list):
        for i, m_config in enumerate(mappings):
            if isinstance(m_config, dict):
                m_config["_source_file"] = fp.name
                m_config["_map_id_in_file"] = i
                midi_filters.append(m_config)
    
    # Aplicar clock_settings
    if isinstance(clock_settings, dict):
        new_bpm = clock_settings.get("default_bpm")
        if isinstance(new_bpm, (int, float)):
            performance_state.bpm = max(20.0, min(300.0, float(new_bpm)))
            # No mostrar feedback aquí, se mostrará el BPM inicial en la UI
        
        # Guardar device_out por defecto si se proporciona, se usará si no hay selección
        # Esto es para el caso donde no se usa el selector interactivo ni --virtual-ports
        default_out_alias = clock_settings.get("device_out")
        if default_out_alias and not performance_state.output_ports: # Solo si no se han configurado ya
             # Se resolverá y abrirá en main() si es necesario
             # Guardaremos el alias para resolverlo después
             performance_state.default_device_out_alias_from_json = default_out_alias


    return True # Indicar éxito

# --- OSC and Main Config ---
OSC_ADDRESSES = {
    # Para recibir comandos
    "PLAY": "/midimaster/play",
    "STOP": "/midimaster/stop",
    "PAUSE": "/midimaster/pause",
    "SET_BPM": "/midimaster/bpm/set",
    # Para enviar actualizaciones
    "STATUS": "/midimaster/status",
    "CURRENT_BPM": "/midimaster/bpm/current"
}

def load_main_config():
    config_path = Path("./midimaster.conf.json")
    # Valores por defecto en caso de que el fichero o las claves no existan
    defaults = {
        "general_settings": {
            "default_bpm": 120.0,
            "default_virtual_port_name": "midimaster_OUT"
        },
        "osc_configuration": {
            "enabled": False,
            "listen_ip": "0.0.0.0",
            "listen_port": 8000,
            "send_ip": "127.0.0.1",
            "send_port": 9000
        }
    }
    if not config_path.is_file():
        print(f"Advertencia: Archivo de configuración '{config_path.name}' no encontrado. Usando valores por defecto.")
        return defaults

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        
        # Sobrescribir valores por defecto con los del usuario de forma segura
        defaults["general_settings"].update(user_config.get("general_settings", {}))
        defaults["osc_configuration"].update(user_config.get("osc_configuration", {}))
        return defaults
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error cargando '{config_path.name}': {e}. Usando valores por defecto.")
        return defaults
    

# --- MIDI Clock Thread (con pequeño ajuste para timing) ---
def midi_clock_sender():
    global SHUTDOWN_FLAG, performance_state
    
    # Variables para un timing más preciso
    last_pulse_time = 0
    pulse_interval = 0 # Se calculará en el bucle

    while not SHUTDOWN_FLAG:
        current_time = time.perf_counter()

        if performance_state.status == "PLAYING":
            # Si se ha señalado un cambio de BPM, reiniciar la temporización
            if bpm_update_signal.is_set():
                last_pulse_time = 0
                bpm_update_signal.clear()

            pulse_interval = 60.0 / (performance_state.bpm * PPQN)
            if last_pulse_time == 0: # Primer pulso después de Play o cambio de BPM
                last_pulse_time = current_time
            
            if current_time >= last_pulse_time:
                clock_message = mido.Message('clock')
                for port in performance_state.output_ports:
                    try:
                        port.send(clock_message)
                    except Exception: pass
                
                last_pulse_time += pulse_interval # Programar el siguiente pulso

            # Dormir hasta un poco antes del siguiente pulso teórico
            # Esto es una heurística, no un reloj de alta precisión en tiempo real.
            next_event_time = last_pulse_time 
            sleep_time = next_event_time - time.perf_counter() - 0.0005 # despertar un poco antes
            if sleep_time > 0:
                time.sleep(sleep_time)
            # Si estamos retrasados, el bucle se ejecutará inmediatamente.

        else: # STOPPED o PAUSED
            if performance_state.status == "STOPPED":
                last_pulse_time = 0 # Resetear para la próxima vez que se dé a play
            time.sleep(0.01) # Menor consumo de CPU cuando no está activo


# --- Funciones de Control (set_bpm, send_midi_command, play/pause/stop, set_feedback_message) ---

def set_bpm(new_bpm):
    if performance_state.bpm_locked:
        set_feedback_message(f"BPM bloqueado en {performance_state.bpm:.2f}")
        return
    
    prev_bpm = performance_state.bpm
    new_bpm_float = max(20.0, min(300.0, float(new_bpm)))
    
    if prev_bpm != new_bpm_float:
        performance_state.bpm = new_bpm_float
        set_feedback_message(f"BPM: {prev_bpm:.2f} -> {performance_state.bpm:.2f}")
        bpm_update_signal.set()
        send_osc_message(OSC_ADDRESSES["CURRENT_BPM"], new_bpm_float)


def send_midi_command(command_type):
    msg = mido.Message(command_type)
    for port in performance_state.output_ports:
        try:
            port.send(msg)
        except Exception: pass

def play_clock(*args):
    if performance_state.status == "STOPPED":
        send_midi_command('start')
        set_feedback_message("PLAYING")
    elif performance_state.status == "PAUSED":
        send_midi_command('continue')
        set_feedback_message("PLAYING (Continuado)")
    performance_state.status = "PLAYING"
    bpm_update_signal.set()
    send_osc_message(OSC_ADDRESSES["STATUS"], "PLAYING")

def pause_clock(*args):
    if performance_state.status == "PLAYING":
        send_midi_command('stop') 
        performance_state.status = "PAUSED"
        set_feedback_message("PAUSED")
        send_osc_message(OSC_ADDRESSES["STATUS"], "PAUSED")

def stop_clock(*args):
    send_midi_command('stop')
    performance_state.status = "STOPPED"
    set_feedback_message("STOPPED")
    send_osc_message(OSC_ADDRESSES["STATUS"], "STOPPED")

def set_feedback_message(message):
    performance_state.last_feedback_message = message
    performance_state.feedback_message_time = time.time()


# --- OSC Functions ---
def send_osc_message(address, value):
    """Envía un mensaje OSC si el cliente está configurado."""
    if osc_client:
        try:
            osc_client.send_message(address, value)
        except Exception as e:
            # Evitar que un error de OSC detenga la aplicación
            # print(f"Error enviando OSC: {e}") # Descomentar para depuración
            pass

def _handle_osc_bpm_set(address, *args):
    """Manejador para recibir BPM vía OSC. Espera un float o int."""
    if args and isinstance(args[0], (int, float)):
        set_bpm(float(args[0]))

def osc_server_handler(server):
    """Función objetivo para el hilo del servidor OSC."""
    try:
        server.serve_forever()
    except Exception as e:
        if not SHUTDOWN_FLAG: # Solo mostrar error si no es un cierre intencionado
             print(f"\nError en el servidor OSC: {e}")


# --- UI Functions (prompt_toolkit) ---
# (get_status_text, get_feedback_line_text, build_key_bindings permanecen iguales)
def get_status_text():
    ports_str_list = []
    if performance_state.virtual_port_name:
        ports_str_list.append(f"Virtual: {performance_state.virtual_port_name}")
    ports_str_list.extend([port.name for port in performance_state.output_ports if port.name != performance_state.virtual_port_name]) # Evitar duplicados si el virtual está en la lista

    ports_display = ", ".join(ports_str_list) if ports_str_list else "Ninguno"


    status_line = f"Salida: {ports_display}\n"
    status_line += f"Estado: {performance_state.status.upper()}\n"
    
    bpm_display = f"{performance_state.bpm:.2f}"
    if len(performance_state.bpm_input_buffer) > 0:
        bpm_display += f" (Entrada: {performance_state.bpm_input_buffer})" # Corrección aquí
    if performance_state.bpm_locked:
        bpm_display += " [BLOQUEADO]"
    status_line += f"BPM:    {bpm_display}"
    return HTML(status_line)

def get_feedback_line_text():
    if performance_state.last_feedback_message and \
       (time.time() - performance_state.feedback_message_time < performance_state.feedback_message_duration):
        return HTML(f"\n<i>{performance_state.last_feedback_message}</i>")
    return HTML("\n ") 

def build_key_bindings():
    kb = KeyBindings()

    @kb.add('escape', eager=True) 
    @kb.add('q', eager=True)
    def _(event):
        global SHUTDOWN_FLAG
        SHUTDOWN_FLAG = True
        set_feedback_message("Saliendo...")
        if event.app: # Asegurarse de que app existe
            event.app.exit(result="quit")

    for i in range(10):
        digit_char = str(i)
        @kb.add(digit_char)
        def _(event, captured_digit=digit_char): # Usar un nombre diferente para la variable capturada
            if not performance_state.bpm_locked:
                performance_state.bpm_input_buffer += captured_digit
                if len(performance_state.bpm_input_buffer) == 3:
                    try:
                        new_bpm_val = float(performance_state.bpm_input_buffer)
                        set_bpm(new_bpm_val)
                    except ValueError:
                        set_feedback_message(f"Entrada BPM inválida: {performance_state.bpm_input_buffer}")
                    performance_state.bpm_input_buffer = ""
                elif len(performance_state.bpm_input_buffer) > 3: 
                    performance_state.bpm_input_buffer = captured_digit 
            else:
                set_feedback_message(f"BPM bloqueado. '{captured_digit}' ignorado.")


    @kb.add('+')
    def _(event): set_bpm(performance_state.bpm + 1)

    @kb.add('-')
    def _(event): set_bpm(performance_state.bpm - 1)
    
    @kb.add('b')
    def _(event):
        performance_state.bpm_locked = not performance_state.bpm_locked
        lock_status = "BLOQUEADO" if performance_state.bpm_locked else "DESBLOQUEADO"
        set_feedback_message(f"Control BPM: {lock_status}")

    @kb.add('c-c', eager=True)
    def _(event):
        global SHUTDOWN_FLAG
        SHUTDOWN_FLAG = True
        if event.app:
            event.app.exit(result="shutdown_critical")


    @kb.add(' ')
    @kb.add('c')
    def _(event):
        if performance_state.status == "PLAYING":
            pause_clock()
        else: 
            play_clock()
    
    @kb.add('enter')
    def _(event):
        if performance_state.bpm_input_buffer:
            try:
                new_bpm_val = float(performance_state.bpm_input_buffer)
                set_bpm(new_bpm_val)
            except ValueError:
                set_feedback_message(f"Entrada BPM inválida: {performance_state.bpm_input_buffer}")
            finally:
                performance_state.bpm_input_buffer = ""
        elif performance_state.status == "PLAYING" or performance_state.status == "PAUSED":
            stop_clock()
            # Si se quiere que Enter desde Pausa también reinicie:
            # if performance_state.status == "PAUSED": play_clock() # Esto lo reiniciaría
        else: # STOPPED
            play_clock()

    @kb.add('p')
    def _(event):
        if performance_state.status != "PLAYING":
            play_clock()

    @kb.add('s')
    def _(event):
        if performance_state.status != "STOPPED":
            stop_clock()
            
    return kb

def global_midi_callback(msg, port_name):
    """
    Despachador global de callbacks MIDI.
    Maneja los comandos de transporte por defecto y pasa el resto al procesador de reglas.
    """
    # Manejo de comandos de transporte MIDI universales
    if msg.type == 'start':
        play_clock()
        return # Consumir el evento para evitar que sea procesado por las reglas JSON
    elif msg.type == 'stop':
        stop_clock()
        return
    elif msg.type == 'continue':
        # play_clock() ya gestiona la reanudación desde PAUSED
        play_clock()
        return

    # Si no es un comando de transporte, se pasa al procesador de mapeos JSON
    process_midi_mappings(msg, port_name)


# --- Procesamiento de Mapeos MIDI (igual que antes) ---

def process_midi_mappings(msg, port_name):
    global performance_state
    if not midi_filters: return

    for mapping in midi_filters: 
        dev_alias = mapping.get("device_in")
        if dev_alias:
            dev_substr = global_device_aliases.get(dev_alias, dev_alias)
            if dev_substr.lower() not in port_name.lower():
                continue
        else: continue 

        if "ch_in" in mapping:
            if hasattr(msg, 'channel'): # Comprueba si el mensaje TIENE un atributo 'channel'
                if msg.channel != mapping["ch_in"]:
                    continue
            else:
                # Si el mensaje NO tiene canal (ej. 'start', 'stop')
                # pero el mapeo SÍ especifica 'ch_in', entonces este mapeo no aplica.
                continue
        
        map_event = mapping.get("event_in")
        is_event_match = False
        if map_event:
            if map_event == "note" and msg.type in ["note_on", "note_off"]: is_event_match = True
            elif map_event == "cc" and msg.type == "control_change": is_event_match = True
            elif map_event == "pc" and msg.type == "program_change": is_event_match = True
            elif msg.type == map_event: is_event_match = True
        if not is_event_match: continue
        
        if "value_1_in" in mapping:
            msg_v1 = getattr(msg, 'note', None)
            if msg_v1 is None: msg_v1 = getattr(msg, 'control', None)
            if msg_v1 is None: msg_v1 = getattr(msg, 'program', None)
            if msg_v1 is None: msg_v1 = -1
            expected_value = mapping["value_1_in"]
            if msg.type in ["note_on", "note_off", "control_change", "program_change"]:
                if msg_v1 != expected_value:
                    continue
            elif msg.type not in ["note_on", "note_off", "control_change", "program_change"] and "value_1_in" in mapping:
                 continue
        
        action = mapping.get("action") 
        if action == "play": play_clock()
        elif action == "stop": stop_clock()
        elif action == "pause":
            if performance_state.status == "PLAYING": pause_clock()
        elif action == "continue": # Bloque añadido
            if performance_state.status == "PAUSED":
                play_clock()
        elif action == "bpm" and msg.type == "control_change":
            cc_val = msg.value
            scale_config = mapping.get("bpm_scale") 
            if isinstance(scale_config, dict):
                min_in = scale_config.get("range_in", [0,127])[0]
                max_in = scale_config.get("range_in", [0,127])[1]
                min_out = scale_config.get("range_out", [60,180])[0]
                max_out = scale_config.get("range_out", [60,180])[1]
                
                if max_in == min_in: normalized = 0.0 if cc_val <= min_in else 1.0
                else: normalized = (float(max(min_in, min(max_in, cc_val))) - min_in) / (max_in - min_in)
                scaled_bpm = normalized * (max_out - min_out) + min_out
                set_bpm(scaled_bpm)
            else:
                set_bpm(cc_val) 
        # break 


# --- UI para selección de puertos (adaptado de MIDImod) ---
def interactive_port_selector(available_ports, prompt_title="Selecciona puertos de SALIDA para el clock"):
    if not available_ports:
        print("No hay puertos MIDI de salida físicos disponibles.")
        return []

    selected_ports_ordered = {}
    current_selection_index_ui = 0
    next_selection_order = 1
    
    kb_ports = KeyBindings()

    @kb_ports.add('c-c', eager=True)
    @kb_ports.add('c-q', eager=True)
    def _(event): event.app.exit(result=None)

    @kb_ports.add('up', eager=True)
    def _(event):
        nonlocal current_selection_index_ui
        current_selection_index_ui = (current_selection_index_ui - 1 + len(available_ports)) % len(available_ports)

    @kb_ports.add('down', eager=True)
    def _(event):
        nonlocal current_selection_index_ui
        current_selection_index_ui = (current_selection_index_ui + 1) % len(available_ports)

    @kb_ports.add('space', eager=True)
    def _(event):
        nonlocal next_selection_order
        selected_port_name = available_ports[current_selection_index_ui]
        if selected_port_name in selected_ports_ordered: 
            removed_order = selected_ports_ordered.pop(selected_port_name)
            for p_name_key in list(selected_ports_ordered.keys()):
                if selected_ports_ordered[p_name_key] > removed_order:
                    selected_ports_ordered[p_name_key] -= 1
            next_selection_order -= 1
        else: 
            selected_ports_ordered[selected_port_name] = next_selection_order
            next_selection_order += 1
            
    @kb_ports.add('enter', eager=True)
    def _(event):
        final_selected_names = []
        if not selected_ports_ordered:
            if available_ports: # Asegurarse de que la lista no está vacía
                final_selected_names.append(available_ports[current_selection_index_ui])
        else:
            # Si hay puertos marcados con Espacio, usa esos.
            sorted_selection = sorted(selected_ports_ordered.items(), key=lambda item: item[1])
            final_selected_names = [item[0] for item in sorted_selection]
        event.app.exit(result=final_selected_names)

    def get_text_for_port_ui():
        # Construir una lista de cadenas de texto (algunas con formato HTML)
        text_parts = []
        text_parts.append(f"<b>{prompt_title}</b>\n(↑↓: navegar, Esp: marcar/desmarcar, Enter: confirmar, Ctrl+C: salir)\n")
        
        for i, port_name_str in enumerate(available_ports):
            order_num = selected_ports_ordered.get(port_name_str)
            marker = f"[{order_num}]" if order_num else "[ ]"
            line_content = f"{marker} {port_name_str}" # line_content es un string simple
            
            if i == current_selection_index_ui:
                # Envolver la línea seleccionada con etiquetas de estilo HTML
                text_parts.append(f"<style bg='ansiblue' fg='ansiwhite'>> {line_content}</style>\n")
            else:
                text_parts.append(f"  {line_content}\n")
        
        full_html_content = "".join(text_parts)
        return HTML(full_html_content)

    control = FormattedTextControl(text=get_text_for_port_ui, focusable=True, key_bindings=kb_ports)
    port_selector_app = Application(layout=Layout(HSplit([Window(content=control)])), full_screen=False, mouse_support=False)
    
    print(f"\nMIDImaster ")
    print(f"--- Selección de Puertos MIDI ---") 
    selected_names = port_selector_app.run()
    
    if selected_names is None: 
        print("Selección de puertos cancelada.")
        return None 
    return selected_names

# --- Main Application ---
def main():
    global SHUTDOWN_FLAG, performance_state, midi_clock_thread, app_ui_instance
    global global_device_aliases, midi_filters, main_config, osc_client, osc_server_thread

    main_config = load_main_config()
    # Actualizar el BPM por defecto desde la configuración
    performance_state.bpm = main_config.get("general_settings", {}).get("default_bpm", DEFAULT_BPM)

    parser = argparse.ArgumentParser(prog=Path(sys.argv[0]).name, description="midimaster - MIDI Beat Clock Maestro")
    parser.add_argument("rule_file", nargs='?', default=None, help=f"Archivo de reglas JSON opcional de './{RULES_DIR_NAME}/'.")
    parser.add_argument("--virtual-ports", action="store_true", help="Activa puerto MIDI virtual de SALIDA.")
    parser.add_argument("--vp-out", type=str, default=main_config.get("general_settings", {}).get("default_virtual_port_name"), metavar="NOMBRE", help="Nombre para el puerto virtual de SALIDA.")
    parser.add_argument("--list-ports", action="store_true", help="Lista puertos MIDI y sale.")
    args = parser.parse_args()

    if args.list_ports:
        print("Puertos de ENTRADA MIDI disponibles:")
        for name in mido.get_input_names(): print(f"  - '{name}'")
        print("\nPuertos de SALIDA MIDI disponibles:")
        for name in mido.get_output_names(): print(f"  - '{name}'")
        return

    RULES_DIR.mkdir(parents=True, exist_ok=True)



    selected_port_names = []
    port_name_from_json = None

    if args.rule_file:
        file_path = RULES_DIR / f"{args.rule_file}.json"
        if load_rule_file(file_path):
            print(f"Archivo de reglas '{file_path.name}' cargado.")
            # Intentar resolver el puerto desde el JSON antes de mostrar el selector
            if hasattr(performance_state, 'default_device_out_alias_from_json'):
                alias = performance_state.default_device_out_alias_from_json
                dev_substr = global_device_aliases.get(alias, alias)
                resolved_name = find_port_by_substring(mido.get_output_names(), dev_substr)
                if resolved_name:
                    port_name_from_json = resolved_name
                    selected_port_names.append(port_name_from_json)
                    print(f"Usando dispositivo de salida '{resolved_name}' definido en JSON.")
                else:
                    print(f"Advertencia: Dispositivo de salida por defecto '{alias}' del JSON no encontrado.")

    # Mostrar selector interactivo solo si el JSON no especificó un puerto válido
    if not port_name_from_json:
        available_physical_outputs = mido.get_output_names()
        if available_physical_outputs:
            user_selected_names = interactive_port_selector(available_physical_outputs)
            if user_selected_names is None: # Usuario canceló
                print("Saliendo de midimaster.")
                return
            if user_selected_names:
                selected_port_names.extend(user_selected_names)

    # Abrir puertos
    opened_port_objects = []
    if args.virtual_ports:
        try:
            vp_name = args.vp_out
            port = mido.open_output(vp_name, virtual=True)
            opened_port_objects.append(port)
            performance_state.virtual_port_name = port.name
            print(f"Puerto virtual de salida '{port.name}' abierto.")
        except Exception as e:
            print(f"Error abriendo puerto virtual '{args.vp_out}': {e}")

    for name in selected_port_names:
        if performance_state.virtual_port_name and name == performance_state.virtual_port_name:
            continue
        try:
            port = mido.open_output(name)
            opened_port_objects.append(port)
            print(f"Puerto de salida físico '{name}' abierto.")
        except Exception as e:
            print(f"Error abriendo puerto físico '{name}': {e}")

    performance_state.output_ports = opened_port_objects

    if not performance_state.output_ports:
        print("Advertencia: No hay puertos de salida activos. El clock no se enviará a ningún destino MIDI.")

    # Iniciar cliente y servidor OSC si está habilitado
    osc_config = main_config.get("osc_configuration", {})
    osc_server_object = None
    if osc_config.get("enabled"):
        send_ip = osc_config.get("send_ip", "127.0.0.1")
        send_port = osc_config.get("send_port", 9000)
        osc_client = udp_client.SimpleUDPClient(send_ip, send_port)
        print(f"OSC: Enviando actualizaciones a {send_ip}:{send_port}")

        disp = dispatcher.Dispatcher()
        disp.map(OSC_ADDRESSES["PLAY"], play_clock)
        disp.map(OSC_ADDRESSES["STOP"], stop_clock)
        disp.map(OSC_ADDRESSES["PAUSE"], pause_clock)
        disp.map(OSC_ADDRESSES["SET_BPM"], _handle_osc_bpm_set)

        listen_ip = osc_config.get("listen_ip", "0.0.0.0")
        listen_port = osc_config.get("listen_port", 8000)
        
        try:
            osc_server_object = osc_server.ThreadingOSCUDPServer((listen_ip, listen_port), disp)
            osc_server_thread = threading.Thread(target=osc_server_handler, args=(osc_server_object,), daemon=True)
            osc_server_thread.start()
            print(f"OSC: Escuchando comandos en {listen_ip}:{listen_port}")
        except Exception as e:
            print(f"Error fatal iniciando servidor OSC en {listen_ip}:{listen_port} - {e}")
            print("La funcionalidad de recepción OSC estará desactivada.")

    # Iniciar hilo de clock MIDI
    midi_clock_thread = threading.Thread(target=midi_clock_sender, daemon=True)
    midi_clock_thread.start()

    # Abrir puertos de entrada MIDI con callbacks si hay mapeos
    midi_input_ports = {}
    if midi_filters:
        required_dev_aliases = {m.get("device_in") for m in midi_filters if m.get("device_in")}
        
        for alias in required_dev_aliases:
            dev_substr = global_device_aliases.get(alias, alias)
            port_name = find_port_by_substring(mido.get_input_names(), dev_substr)
            if port_name and port_name not in midi_input_ports:
                try:
                    # Crear un callback que capture el nombre del puerto y lo envíe al despachador global
                    callback_func = lambda msg, name=port_name: global_midi_callback(msg, name)
                    port = mido.open_input(port_name, callback=callback_func)
                    midi_input_ports[port_name] = port
                    print(f"Puerto de entrada '{port_name}' para mapeos abierto.")
                except Exception as e:
                    print(f"Error abriendo puerto de entrada '{port_name}': {e}")
    

    status_window = Window(content=FormattedTextControl(text=get_status_text, focusable=False), height=4, style="bg:#444444 #ffffff")
    feedback_window = Window(content=FormattedTextControl(text=get_feedback_line_text, focusable=False), height=2, style="bg:#222222 #aaaaaa")
    
    layout = Layout(HSplit([status_window, feedback_window]))
    kb = build_key_bindings()
    
    global app_ui_instance
    app_ui_instance = Application(layout=layout, key_bindings=kb, full_screen=False, refresh_interval=0.1, mouse_support=False)

    print("\nIniciando interfaz de midimaster...")
    print("Controles: Números (BPM), +/- (BPM), Espacio/c (Play/Pause), Enter (Play/Stop), p (Play), s (Stop), b (Bloqueo BPM), q/Esc (Salir)")
    
    try:
        app_ui_instance.run()
    except KeyboardInterrupt: 
        SHUTDOWN_FLAG = True
    except Exception as e:
        print(f"Error en la UI o bucle principal: {e}")
        traceback.print_exc()
        SHUTDOWN_FLAG = True
    finally:
        SHUTDOWN_FLAG = True 
        print("\nCerrando midimaster...")

        # Apagar servidor OSC
        if osc_server_object:
            osc_server_object.shutdown()
        if osc_server_thread and osc_server_thread.is_alive():
            osc_server_thread.join(timeout=0.2)
            print("Servidor OSC detenido.")
        if midi_clock_thread and midi_clock_thread.is_alive():
            midi_clock_thread.join(timeout=0.2) # Reducir timeout para cierre más rápido
        
        # Cerrar puertos de salida
        # Crear una copia de la lista para iterar, ya que podríamos estar modificándola indirectamente
        ports_to_close = list(performance_state.output_ports)
        performance_state.output_ports.clear() # Limpiar la lista original
        for port in ports_to_close:
            try:
                if hasattr(port, 'panic'): port.panic() 
                if not port.closed: port.close()
                print(f"Puerto de salida '{port.name}' cerrado.")
            except Exception: pass
        
        # Cerrar puertos de entrada
        inputs_to_close = list(midi_input_ports.values())
        midi_input_ports.clear()
        for port_obj in inputs_to_close:
            try:
                if not port_obj.closed: port_obj.close()
                # print(f"Puerto de entrada '{port_obj.name}' cerrado.") # El nombre no siempre está disponible así
            except Exception: pass
        print("midimaster detenido.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler) 
    main()