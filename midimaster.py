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
from prompt_toolkit.layout.containers import HSplit, Window # VSplit, ConditionalContainer (no usados por ahora)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
# from prompt_toolkit.document import Document # No usado por ahora

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

# --- Mapeo de MIDI ---
global_device_aliases = {}
input_mappings = []

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
    global global_device_aliases, input_mappings, performance_state
    content = _load_json_file_content(fp)
    if not content or not isinstance(content, dict): return False # Indicar fallo

    devices = content.get("device_alias", {})
    mappings = content.get("input_mappings", [])
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
                input_mappings.append(m_config)
    
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

# --- MIDI Clock Thread (con pequeño ajuste para timing) ---
def midi_clock_sender():
    global SHUTDOWN_FLAG, performance_state
    
    # Variables para un timing más preciso
    last_pulse_time = 0
    pulse_interval = 0 # Se calculará en el bucle

    while not SHUTDOWN_FLAG:
        current_time = time.perf_counter()

        if performance_state.status == "PLAYING":
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
# (Estas funciones permanecen mayormente iguales a la propuesta anterior,
#  asegúrate de que set_bpm actualice last_pulse_time = 0 en el hilo del clock si el BPM cambia en caliente)
def set_bpm(new_bpm):
    global last_pulse_time # Necesario si modificamos una global desde otra función que no es el hilo
    if performance_state.bpm_locked:
        set_feedback_message(f"BPM bloqueado en {performance_state.bpm:.2f}")
        return
    
    prev_bpm = performance_state.bpm
    new_bpm_float = max(20.0, min(300.0, float(new_bpm)))
    
    if prev_bpm != new_bpm_float:
        performance_state.bpm = new_bpm_float
        set_feedback_message(f"BPM: {prev_bpm:.2f} -> {performance_state.bpm:.2f}")
        # Forzar recalculo del timing en el hilo del clock si está PLAYING
        if performance_state.status == "PLAYING" and midi_clock_thread and midi_clock_thread.is_alive():
             # Una forma de señalar al hilo que recalcule es resetear last_pulse_time
             # Esto requiere acceso seguro o un event. No lo haremos directamente aquí por simplicidad,
             # el hilo de clock ya lo recalcula basado en el nuevo BPM.
             # El ajuste de last_pulse_time = 0 al inicio del play o cuando bpm cambia es crucial.
             pass


def send_midi_command(command_type):
    msg = mido.Message(command_type)
    for port in performance_state.output_ports:
        try:
            port.send(msg)
        except Exception: pass

def play_clock():
    global last_pulse_time # Si el hilo de clock usa esta global
    if performance_state.status == "STOPPED":
        send_midi_command('start')
        set_feedback_message("PLAYING")
    elif performance_state.status == "PAUSED":
        send_midi_command('continue')
        set_feedback_message("PLAYING (Continuado)")
    performance_state.status = "PLAYING"
    # last_pulse_time = 0 # Resetear para el hilo de clock

def pause_clock():
    if performance_state.status == "PLAYING":
        send_midi_command('stop') 
        performance_state.status = "PAUSED"
        set_feedback_message("PAUSED")

def stop_clock():
    send_midi_command('stop')
    performance_state.status = "STOPPED"
    set_feedback_message("STOPPED")
    # last_pulse_time = 0 # Resetear para el hilo de clock


def set_feedback_message(message):
    performance_state.last_feedback_message = message
    performance_state.feedback_message_time = time.time()


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
        if performance_state.status == "PLAYING" or performance_state.status == "PAUSED":
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

# --- Procesamiento de Mapeos MIDI (igual que antes) ---
def process_midi_mappings(msg, port_name):
    global performance_state
    if not input_mappings: return

    for mapping in input_mappings:
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
        break 

# --- UI para selección de puertos (adaptado de MIDImod) ---
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
        
        # Unir todas las partes en una sola cadena HTML
        full_html_content = "".join(text_parts)
        # Devolver un único objeto HTML que contenga toda la cadena formateada
        return HTML(full_html_content)

    control = FormattedTextControl(text=get_text_for_port_ui, focusable=True, key_bindings=kb_ports)
    port_selector_app = Application(layout=Layout(HSplit([Window(content=control)])), full_screen=False, mouse_support=False)
    
    print(f"\nMIDImaster ")
    print(f"--- Selección de Puertos MIDI ---") # Esto se imprime antes de que la UI se inicie
    selected_names = port_selector_app.run()
    
    if selected_names is None: 
        print("Selección de puertos cancelada.")
        return None 
    return selected_names

    def get_text_for_port_ui():
        fragments = [HTML(f"<b>{prompt_title}</b>\n(↑↓: navegar, Esp: marcar/desmarcar, Enter: confirmar, Ctrl+C: salir)\n")]
        for i, port_name_str in enumerate(available_ports):
            order_num = selected_ports_ordered.get(port_name_str)
            marker = f"[{order_num}]" if order_num else "[ ]"
            line_content = f"{marker} {port_name_str}"
            if i == current_selection_index_ui:
                fragments.append(HTML(f"<style bg='ansiblue' fg='ansiwhite'>> {line_content}</style>\n"))
            else:
                fragments.append(HTML(f"  {line_content}\n"))
        return fragments

    control = FormattedTextControl(text=get_text_for_port_ui, focusable=True, key_bindings=kb_ports)
    port_selector_app = Application(layout=Layout(HSplit([Window(content=control)])), full_screen=False, mouse_support=False)
    
    print(f"\n--- Selección de Puertos MIDI ---")
    selected_names = port_selector_app.run()
    
    if selected_names is None: # Cancelado con Ctrl+C
        print("Selección de puertos cancelada.")
        return None 
    return selected_names # Puede ser una lista vacía si el usuario no seleccionó nada y dio Enter


# --- Main Application ---
def main():
    global SHUTDOWN_FLAG, performance_state, midi_clock_thread, app_ui_instance
    global global_device_aliases, input_mappings # Necesario para que load_rule_file funcione

    parser = argparse.ArgumentParser(prog=Path(sys.argv[0]).name, description="midimaster - MIDI Beat Clock Maestro")
    parser.add_argument("rule_file", nargs='?', default=None, help=f"Archivo de reglas JSON opcional de './{RULES_DIR_NAME}/'.")
    parser.add_argument("--virtual-ports", action="store_true", help="Activa puerto MIDI virtual de SALIDA (nombre por defecto: midimaster_OUT).")
    parser.add_argument("--vp-out", type=str, default="midimaster_OUT", metavar="NOMBRE", help="Nombre para el puerto virtual de SALIDA.")
    parser.add_argument("--list-ports", action="store_true", help="Lista puertos MIDI y sale.")
    args = parser.parse_args()

    if args.list_ports:
        print("Puertos de ENTRADA MIDI disponibles:")
        for name in mido.get_input_names(): print(f"  - '{name}'")
        print("\nPuertos de SALIDA MIDI disponibles:")
        for name in mido.get_output_names(): print(f"  - '{name}'")
        return

    RULES_DIR.mkdir(parents=True, exist_ok=True)
    json_loaded_successfully = False
    if args.rule_file:
        file_path = RULES_DIR / f"{args.rule_file}.json"
        json_loaded_successfully = load_rule_file(file_path)
        if json_loaded_successfully:
            print(f"Archivo de reglas '{file_path.name}' cargado.")
            # performance_state.bpm ya se actualizó en load_rule_file si default_bpm estaba presente
    
    # Seleccionar puertos de salida físicos si no es modo virtual exclusivo O si se quiere añadir a virtual
    selected_physical_port_names = []
    # if not args.virtual_ports or (args.virtual_ports and not json_setting_prevents_physical_selection): # Lógica más compleja aquí
    # Por ahora, siempre ofrecemos seleccionar puertos físicos, que se sumarán al virtual si está activo.
    
    available_physical_outputs = mido.get_output_names()
    if available_physical_outputs:
        # Si hay un device_out por defecto en JSON y no se usa selector, se podría usar eso en lugar del selector.
        # Pero si estamos aquí, es probable que queramos el selector.
        # Si se carga un JSON con "device_out" y el usuario NO selecciona nada, ¿debería usarse el del JSON?
        # Decisión: el selector interactivo tiene precedencia si se muestra.
        
        # No mostrar selector si solo se especifica --virtual-ports y no hay archivo de reglas con device_out,
        # o si el archivo de reglas no indica un device_out físico.
        # Simplificación: si no es virtual-ports exclusivo, o si hay puertos físicos disponibles, mostrar selector.
        
        # Mostrar selector si no estamos en modo SOLO virtual y hay puertos físicos
        # O si estamos en modo virtual Y el usuario podría querer añadir salidas físicas ADEMÁS del virtual.
        # Por ahora, vamos a mostrarlo si hay puertos físicos, y luego filtramos.
        
        print_port_selection_prompt = True
        if args.virtual_ports and not available_physical_outputs : # Solo virtual y no hay físicos, no mostrar
            print_port_selection_prompt = False
        # Podríamos añadir lógica para no mostrarlo si un JSON ya define un device_out y el usuario no quiere cambiarlo.

        if print_port_selection_prompt:
            user_selected_names = interactive_port_selector(available_physical_outputs)
            if user_selected_names is None: # Usuario canceló con Ctrl+C
                print("Saliendo de midimaster.")
                return
            if user_selected_names: # Si devolvió una lista (puede ser vacía)
                selected_physical_port_names.extend(user_selected_names)


    # Abrir puertos
    opened_port_objects = [] # Usar una lista temporal para evitar modificar performance_state.output_ports directamente aquí

    if args.virtual_ports:
        try:
            vp_name = args.vp_out
            port = mido.open_output(vp_name, virtual=True) 
            opened_port_objects.append(port)
            performance_state.virtual_port_name = port.name 
            print(f"Puerto virtual de salida '{port.name}' abierto.")
        except Exception as e:
            print(f"Error abriendo puerto virtual '{args.vp_out}': {e}")
            print("Asegúrate de tener un backend MIDI que soporte creación/uso de puertos virtuales (ej. loopMIDI en Windows, o IAC en macOS).")
            
    for name in selected_physical_port_names:
        # Evitar abrir el mismo puerto si el virtual tiene el mismo nombre que uno físico (improbable pero posible)
        if performance_state.virtual_port_name and name == performance_state.virtual_port_name:
            continue
        try:
            port = mido.open_output(name)
            opened_port_objects.append(port)
            print(f"Puerto de salida físico '{name}' abierto.")
        except Exception as e:
            print(f"Error abriendo puerto físico '{name}': {e}")

    # Si después de todo no hay puertos abiertos, y un JSON especificó un default_device_out_alias_from_json
    if not opened_port_objects and hasattr(performance_state, 'default_device_out_alias_from_json'):
        alias = performance_state.default_device_out_alias_from_json
        dev_substr = global_device_aliases.get(alias, alias)
        port_name_from_json = find_port_by_substring(mido.get_output_names(), dev_substr)
        if port_name_from_json:
            try:
                port = mido.open_output(port_name_from_json)
                opened_port_objects.append(port)
                print(f"Puerto de salida físico '{port_name_from_json}' (de JSON) abierto.")
            except Exception as e:
                print(f"Error abriendo puerto físico '{port_name_from_json}' (de JSON): {e}")
        else:
            print(f"Advertencia: Dispositivo de salida por defecto '{alias}' del JSON no encontrado.")

    performance_state.output_ports = opened_port_objects # Asignar finalmente

    if not performance_state.output_ports:
        print("Advertencia: No hay puertos de salida activos. El clock no se enviará a ningún destino MIDI.")
        # Decidir si continuar o salir. Para un master clock, es poco útil sin salidas.
        # Pero podría ser útil para controlar la UI y ver el BPM, o si se usa solo para mapeos internos (no es el caso aquí).
        # Por ahora, permitimos continuar, el usuario verá "Salida: Ninguno".

    # Iniciar hilo de clock MIDI
    midi_clock_thread = threading.Thread(target=midi_clock_sender, daemon=True)
    midi_clock_thread.start()

    # Iniciar hilo para escuchar MIDI IN si hay mapeos
    midi_input_ports = {}
    if input_mappings:
        required_dev_aliases = set()
        for m in input_mappings:
            dev_in_alias = m.get("device_in")
            if dev_in_alias:
                required_dev_aliases.add(dev_in_alias)
        
        for alias in required_dev_aliases:
            dev_substr = global_device_aliases.get(alias, alias)
            port_name = find_port_by_substring(mido.get_input_names(), dev_substr)
            if port_name and port_name not in midi_input_ports:
                try:
                    midi_input_ports[port_name] = mido.open_input(port_name)
                    print(f"Puerto de entrada '{port_name}' para mapeos abierto.")
                except Exception as e:
                    print(f"Error abriendo puerto de entrada '{port_name}': {e}")
    
    def midi_input_listener():
        while not SHUTDOWN_FLAG:
            active = False
            for port_name, port_obj in midi_input_ports.items():
                if port_obj and not port_obj.closed: # Verificar si el puerto está activo
                    msg = port_obj.poll()
                    if msg:
                        process_midi_mappings(msg, port_name)
                        active = True
            if not active and midi_input_ports: # Si hay puertos definidos pero ninguno activo, pequeña pausa
                 time.sleep(0.01)
            elif not midi_input_ports: # No hay puertos de input, el hilo no necesita hacer mucho
                 time.sleep(0.1)
            else: # Hubo actividad o no hay puertos
                 time.sleep(0.001)


    if midi_input_ports:
        midi_input_thread = threading.Thread(target=midi_input_listener, daemon=True)
        midi_input_thread.start()

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