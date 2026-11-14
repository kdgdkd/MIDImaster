# midislave.py
import mido
import time
import signal
import sys
from collections import deque
import statistics

# --- UI Imports ---
from prompt_toolkit import Application, HTML
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings

# --- Global Configuration ---
SHUTDOWN_FLAG = False
PPQN = 24

# --- Clock Monitor State ---
class ClockState:
    def __init__(self):
        self.status = "STOPPED"; self.input_port = None; self.input_port_name = ""
        self.total_bytes_received = 0; self.last_clock_time = 0
        self.clock_intervals_fast = deque(maxlen=12)
        self.clock_intervals_medium = deque(maxlen=120)
        self.clock_intervals_slow = deque(maxlen=288)
        self.bpm_fast = 0.0; self.bpm_medium = 0.0; self.bpm_slow = 0.0
        self.bpm_stability = 0.0; self.delta_history = deque(maxlen=200)
        self.avg_delta = 0.0; self.jitter_ms = 0.0
        self.last_start_time = 0; self.last_stop_time = 0

clock_state = ClockState()
app_ui_instance = None

# --- Helper Functions ---
def signal_handler(sig, frame):
    global SHUTDOWN_FLAG; SHUTDOWN_FLAG = True
    if app_ui_instance: app_ui_instance.exit(result="shutdown")

def calculate_bpm_from_intervals(intervals):
    if len(intervals) < 2: return 0.0
    try:
        avg_interval = statistics.mean(intervals)
        if avg_interval <= 0: return 0.0
        bpm = 60.0 / (avg_interval * PPQN)
        return max(0.0, min(300.0, bpm))
    except (statistics.StatisticsError, ZeroDivisionError): return 0.0

def midi_clock_callback(msg):
    global clock_state
    current_time = time.perf_counter()
    clock_state.total_bytes_received += len(msg.bytes())

    if msg.type in ['start', 'continue']:
        clock_state.status = "PLAYING"; clock_state.last_start_time = current_time
        if msg.type == 'start': # Reset only on explicit start
            clock_state.last_clock_time = 0; clock_state.clock_intervals_fast.clear()
            clock_state.clock_intervals_medium.clear(); clock_state.clock_intervals_slow.clear()
            clock_state.delta_history.clear()
    elif msg.type == 'stop':
        clock_state.status = "STOPPED"; clock_state.last_stop_time = current_time
    elif msg.type == 'clock':
        if clock_state.status == "STOPPED":
            clock_state.status = "PLAYING"; clock_state.last_clock_time = 0
            clock_state.clock_intervals_fast.clear(); clock_state.clock_intervals_medium.clear()
            clock_state.clock_intervals_slow.clear(); clock_state.delta_history.clear()
        
        if clock_state.last_clock_time > 0:
            interval = current_time - clock_state.last_clock_time
            if 0.001 < interval < 1.0:
                clock_state.clock_intervals_fast.append(interval)
                clock_state.clock_intervals_medium.append(interval)
                clock_state.clock_intervals_slow.append(interval)
                if len(clock_state.clock_intervals_medium) > 5:
                    try: clock_state.jitter_ms = statistics.stdev(clock_state.clock_intervals_medium) * 1000
                    except: pass
        
        clock_state.last_clock_time = current_time
        clock_state.bpm_fast = calculate_bpm_from_intervals(clock_state.clock_intervals_fast)
        clock_state.bpm_slow = calculate_bpm_from_intervals(clock_state.clock_intervals_slow)
        
        if clock_state.bpm_fast > 0 and clock_state.bpm_slow > 0:
            clock_state.bpm_stability = abs(clock_state.bpm_fast - clock_state.bpm_slow)
            clock_state.delta_history.append(clock_state.bpm_stability)

        if len(clock_state.delta_history) > 1:
            try: clock_state.avg_delta = statistics.mean(clock_state.delta_history)
            except: pass

# --- UI Functions ---
def get_status_text():
    port_display = clock_state.input_port_name or "Ninguno"
    datos_recibidos = f"{clock_state.total_bytes_received} bytes"
    
    status_line =  f"Source:      {port_display}  [{clock_state.status}] {datos_recibidos}\n\n"
    
    bpm_fast_str = f"{clock_state.bpm_fast:6.2f}" if clock_state.bpm_fast > 0 else "  -.--"
    bpm_slow_str = f"{clock_state.bpm_slow:6.2f}" if clock_state.bpm_slow > 0 else "  -.--"
    
    status_line += f"BPM:         {bpm_fast_str}  (12 tics)\n"
    status_line += f"             {bpm_slow_str}  (288 tics)\n"
    
    if clock_state.bpm_stability > 0:
        stability_str = f"{clock_state.bpm_stability:5.2f}"
        avg_delta_str = f"({clock_state.avg_delta:.2f} avg 4s)" if clock_state.avg_delta > 0 else ""
        if clock_state.bpm_stability < 0.5: stability_color = "ansibrightgreen"
        elif clock_state.bpm_stability < 2.0: stability_color = "ansibrightyellow"
        else: stability_color = "ansibrightred"
        status_line += f"BPM \u0394:      <style fg='{stability_color}'>  {stability_str}</style>  {avg_delta_str}\n"
    else:
        status_line += "BPM \u0394:         -.--\n"

    if clock_state.jitter_ms > 0:
        jitter_val_str = f"{clock_state.jitter_ms:5.3f} ms"
        if clock_state.jitter_ms < 0.5: jitter_color = "ansibrightgreen"
        elif clock_state.jitter_ms < 1.5: jitter_color = "ansibrightyellow"
        else: jitter_color = "ansibrightred"
        status_line += f"Jitter:      <style fg='{jitter_color}'> {jitter_val_str}</style>  (stdev)"
    else:
        status_line += "Jitter:       -.--- ms"
        
    return HTML(status_line)

def get_delta_bar(): 
    if clock_state.bpm_stability <= 0.25: return HTML("[----------------------------------------]")
    max_diff = 5.0; bar_length = 40
    normalized_diff = min(clock_state.bpm_stability / max_diff, 1.0)
    filled_chars = int(normalized_diff * bar_length)
    bar = ['-'] * bar_length
    char_symbol = '█' if normalized_diff < 0.2 else ('▓' if normalized_diff < 0.6 else '░')
    for i in range(filled_chars): bar[i] = char_symbol
    bar_str = ''.join(bar)

    if clock_state.bpm_stability < 0.5: color = "ansibrightgreen"
    elif clock_state.bpm_stability < 2.0: color = "ansibrightyellow"
    else: color = "ansibrightred"
    return HTML(f"<style fg='{color}'>[{bar_str}]</style>")

def get_jitter_bar(): 
    """Genera una barra horizontal que muestra el jitter."""
    if clock_state.jitter_ms <= 0.1: return HTML("[----------------------------------------]")
    max_jitter = 2.5; bar_length = 40 # Escala: 0-2.5 ms
    normalized_jitter = min(clock_state.jitter_ms / max_jitter, 1.0)
    filled_chars = int(normalized_jitter * bar_length)
    bar = ['-'] * bar_length
    char_symbol = '█' if normalized_jitter < 0.2 else ('▓' if normalized_jitter < 0.6 else '░')
    for i in range(filled_chars): bar[i] = char_symbol
    bar_str = ''.join(bar)

    if clock_state.jitter_ms < 0.5: color = "ansibrightgreen"
    elif clock_state.jitter_ms < 1.5: color = "ansibrightyellow"
    else: color = "ansibrightred"
    return HTML(f"<style fg='{color}'>[{bar_str}]</style>")

def build_key_bindings():
    kb = KeyBindings()
    @kb.add('escape', 'q', eager=True)
    def _(event): global SHUTDOWN_FLAG; SHUTDOWN_FLAG = True; event.app.exit(result="quit")
    @kb.add('c-c', eager=True)
    def _(event): global SHUTDOWN_FLAG; SHUTDOWN_FLAG = True; event.app.exit(result="shutdown_critical")
    @kb.add('enter') 
    def _(event):
        clock_state.__init__() # La forma más fácil de resetear todo el estado
    @kb.add(' ')
    def _(event): event.app.exit(result="change_port")
    return kb

def interactive_input_port_selector(available_ports):
    if not available_ports: print("No hay puertos MIDI de entrada disponibles."); return None
    current_selection = 0; kb_ports = KeyBindings()
    @kb_ports.add('c-c', 'c-q', eager=True)
    def _(event): event.app.exit(result=None)
    @kb_ports.add('up', eager=True)
    def _(event): nonlocal current_selection; current_selection = (current_selection - 1 + len(available_ports)) % len(available_ports)
    @kb_ports.add('down', eager=True)
    def _(event): nonlocal current_selection; current_selection = (current_selection + 1) % len(available_ports)
    @kb_ports.add('enter', eager=True)
    def _(event): event.app.exit(result=available_ports[current_selection])
    def get_port_selection_text():
        text_parts = ["<b>Selecciona puerto de ENTRADA para monitorear clock MIDI</b>\n", "(↑↓: navegar, Enter: confirmar, Ctrl+C: salir)\n\n"]
        for i, port_name in enumerate(available_ports):
            if i == current_selection: text_parts.append(f"<style bg='ansiblue' fg='ansiwhite'>> {port_name}</style>\n")
            else: text_parts.append(f"  {port_name}\n")
        return HTML("".join(text_parts))
    control = FormattedTextControl(text=get_port_selection_text, focusable=True, key_bindings=kb_ports)
    selector_app = Application(layout=Layout(HSplit([Window(content=control)])), full_screen=False, mouse_support=False)
    print("MIDIslave - Monitor de Clock MIDI\n--- Selección de Puerto ---")
    selected_port = selector_app.run()
    if selected_port is None: print("Selección de puerto cancelada.")
    return selected_port

def main():
    global SHUTDOWN_FLAG, clock_state, app_ui_instance
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("midislave - Monitor de Clock MIDI\nUso: python midislave.py\n\nControles:\n  Enter   - Reset\n  Espacio - Cambiar puerto\n  q/Esc   - Salir")
        return

    while not SHUTDOWN_FLAG:
        available_input_ports = mido.get_input_names()
        if not available_input_ports: print("Error: No hay puertos MIDI de entrada disponibles."); return
        selected_port_name = interactive_input_port_selector(available_input_ports)
        if not selected_port_name: print("Saliendo de midislave."); return

        if clock_state.input_port and not clock_state.input_port.closed:
            try: clock_state.input_port.close(); print(f"Puerto anterior '{clock_state.input_port_name}' cerrado.")
            except: pass

        clock_state = ClockState()
        try:
            clock_state.input_port = mido.open_input(selected_port_name, callback=midi_clock_callback)
            clock_state.input_port_name = selected_port_name
            print(f"Puerto de entrada '{selected_port_name}' abierto.")
        except Exception as e: print(f"Error abriendo puerto '{selected_port_name}': {e}"); continue

        status_window = Window(content=FormattedTextControl(text=get_status_text, focusable=False), height=7, style="bg:#444444 #ffffff")
        delta_bar_window = Window(content=FormattedTextControl(text=get_delta_bar, focusable=False), height=2, style="bg:#222222 #aaaaaa")
        jitter_bar_window = Window(content=FormattedTextControl(text=get_jitter_bar, focusable=False), height=2, style="bg:#222222 #aaaaaa") 
        
        layout = Layout(HSplit([status_window, delta_bar_window, jitter_bar_window])) 
        kb = build_key_bindings()
        app_ui_instance = Application(layout=layout, key_bindings=kb, full_screen=False, refresh_interval=0.1, mouse_support=False)

        print("\nIniciando monitor...\nControles: Enter (Reset), Espacio (Cambiar puerto), q/Esc (Salir)\nEsperando señales MIDI...\n")
        
        try:
            result = app_ui_instance.run()
            if result == "change_port": print("\n--- Cambiando puerto fuente ---"); continue
            else: break
        except Exception as e: print(f"Error en la aplicación: {e}"); SHUTDOWN_FLAG = True; break
    
    print("\nCerrando midislave...")
    if clock_state.input_port and not clock_state.input_port.closed:
        try: clock_state.input_port.close(); print(f"Puerto de entrada '{clock_state.input_port_name}' cerrado.")
        except: pass
    print("midislave detenido.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    main()