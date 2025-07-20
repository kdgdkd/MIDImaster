# MIDImaster

MIDImaster is a command-line tool with a Terminal User Interface (TUI) designed to be a flexible and configurable MIDI Beat Clock master. It allows you to send MIDI clock signals to multiple outputs (physical and/or virtual) and control tempo (BPM) and transport (Play/Pause/Stop) both through the terminal and via incoming MIDI messages.

## Key Features

- **MIDI Beat Clock Generator:** Sends clock, start, stop, and continue messages to selected MIDI output ports.

- **Interactive BPM Control:**
  
  - Adjust BPM via direct numeric input (three digits, e.g., 120).
  
  - Increment/decrement BPM with + and - keys.
  
  - Lock BPM to prevent accidental changes.

- **Transport Controls:**
  
  - Play, Pause, Stop via keyboard shortcuts.

- **MIDI Port Management:**
  
  - Interactive selector for physical MIDI output ports.
  
  - Support for creating virtual MIDI output ports (ideal for routing to DAWs or other applications on the same system).
  
  - Listing of available MIDI ports.

- **Rule-Based Incoming MIDI Mapping:**
  
  - Load JSON configuration files from the rules_midimaster/ directory.
  
  - Define aliases for MIDI devices for easier configuration.
  
  - Map incoming MIDI messages (Note On/Off, CC, Program Change, Start, Stop, etc.) from specific devices to internal actions such as:
    
    - Play, Stop, Pause.
    
    - Adjust BPM (with linear scaling option for CC messages).

- **Terminal User Interface (TUI):**
  
  - Displays current status (output ports, clock state, BPM).
  
  - Provides feedback for user actions.
  
  - Built with prompt_toolkit.

- **Persistent Configuration (Partial):**
  
  - Default BPM can be set in the JSON rule file.
  
  - Default output port can be suggested from the rule file.

## Requirements

- Python 3.6+

- Python Libraries:
  
  - mido (for MIDI communication)
  
  - prompt_toolkit (for the terminal user interface)

- **For virtual MIDI ports:**
  
  - **Windows:** A MIDI loopback driver like [loopMIDI](https://www.google.com/url?sa=E&q=https%3A%2F%2Fwww.tobias-erichsen.de%2Fsoftware%2Floopmidi.html).
  
  - **macOS:** The built-in "IAC Driver" (activated in "Audio MIDI Setup").
  
  - **Linux:** The snd-virmidi kernel module (usually available, may require modprobe snd-virmidi).

## Installation

1. **Clone the repository or download midimaster.py**.

2. **Install dependencies:**

```
pip install mido prompt_toolkit
```

1. **Create the rules directory (optional, but recommended for using mappings):**  
   In the same directory where midimaster.py is located, create a folder named rules_midimaster:

```
mkdir rules_midimaster
```

## Usage

### Basic Execution

To start MIDImaster:

```
python midimaster.py
```

Upon startup, if physical MIDI output ports are available, you will be presented with an interactive selector to choose where to send the clock.

### Command-Line Arguments

- python midimaster.py [rule_filename]
  
  - Loads a specific rule file from the rules_midimaster/ directory. Do not include the .json extension.
  
  - Example: python midimaster.py my_setup will load rules_midimaster/my_setup.json.

- --virtual-ports
  
  - Creates a virtual MIDI output port. By default, it's named midimaster_OUT.

- --vp-out NAME
  
  - Specifies a custom name for the virtual MIDI output port.
  
  - Example: python midimaster.py --virtual-ports --vp-out "MyVirtualClock"

- --list-ports
  
  - Lists all available MIDI input and output ports and then exits.

### Interactive TUI Controls

Once MIDImaster is running:

- **BPM:**
  
  - 0-9: Enter a new BPM (3 digits, e.g., 1, 2, 5 for 125 BPM).
  
  - +: Increment BPM by 1.
  
  - -: Decrement BPM by 1.
  
  - b: Lock/Unlock BPM control.

- **Transport:**
  
  - Space or c: Toggles between Play/Pause. If Stopped, starts Play.
  
  - Enter: If Stopped, starts Play. If Playing or Paused, Stops.
  
  - p: Starts Play (if not already playing).
  
  - s: Stops the clock.

- **Exit:**
  
  - q or Esc: Quits the application.
  
  - Ctrl+C: Quits the application (force quit).

### Rules Files (JSON)

Rules files allow you to customize MIDImaster's behavior, especially for incoming MIDI mapping and default settings. They must be located in the rules_midimaster/ directory and have the .json extension.

The basic structure of a rule file is:

```
{
  "device_alias": {
    "my_controller": "Arturia KeyStep", // An alias for a port name containing "Arturia KeyStep"
    "my_preferred_output": "UM-ONE"
  },
  "clock_settings": {
    "default_bpm": 125.0,
    "device_out": "my_preferred_output" // Attempt to use this alias as default output if no ports are selected interactively
  },
  "input_mappings": [
    // Mappings here
  ]
}
```

#### device_alias Section

Define friendly names (aliases) for your MIDI devices. MIDImaster will search for the provided substring in the actual MIDI port names.

- "alias_name": "substring_of_actual_port_name"

#### clock_settings Section

Settings related to the outgoing MIDI clock.

- default_bpm (optional): Number (int or float). Sets the initial BPM when the file is loaded.

- device_out (optional): String (an alias defined in device_alias or a direct substring). If no ports are selected interactively and --virtual-ports is not used exclusively, MIDImaster will attempt to open this port as an output.

#### input_mappings Section

A list of objects, each defining how a specific incoming MIDI message should trigger an action in MIDImaster.

Each mapping object can contain:

- device_in: (String, required) The alias (from device_alias) of the input MIDI port.

- ch_in: (Integer, optional, 0-15) The MIDI channel of the incoming message. If omitted, applies to any channel.

- event_in: (String, required) The type of MIDI message:
  
  - "note" (covers note_on and note_off)
  
  - "note_on"
  
  - "note_off"
  
  - "cc" (for control_change)
  
  - "pc" (for program_change)
  
  - "start", "stop", "continue" (system messages)
  
  - Other Mido types (e.g., "pitchwheel", "aftertouch")

- value_1_in: (Integer, optional) The first value of the MIDI message:
  
  - For note_on/note_off: note number (0-127).
  
  - For control_change: CC number (0-127).
  
  - For program_change: program number (0-127).

- action: (String, required) The action to perform:
  
  - "play": Starts the clock (or continues if paused).
  
  - "stop": Stops the clock.
  
  - "pause": Pauses the clock (only if playing).
  
  - "bpm": Adjusts the BPM. Typically used with event_in: "cc".
    
    - If event_in is cc, the CC value (0-127) is used directly as BPM, unless bpm_scale is defined.

- bpm_scale: (Object, optional, only for action: "bpm" and event_in: "cc")  
  Allows scaling the incoming CC value to a BPM range.
  
  - range_in: (List of 2 numbers, e.g., [0, 127]) Input CC value range.
  
  - range_out: (List of 2 numbers, e.g., [60.0, 180.0]) Output BPM range.

**Example of input_mappings:**

```
"input_mappings": [
  {
    "device_in": "my_controller",
    "event_in": "start",
    "action": "play"
  },
  {
    "device_in": "my_controller",
    "event_in": "stop",
    "action": "stop"
  },
  {
    "device_in": "my_controller",
    "ch_in": 0, // Channel 1
    "event_in": "note_on",
    "value_1_in": 36, // Note C2
    "action": "play"
  },
  {
    "device_in": "my_controller",
    "ch_in": 0,
    "event_in": "note_on",
    "value_1_in": 37, // Note C#2
    "action": "stop"
  },
  {
    "device_in": "my_controller",
    "ch_in": 9, // Channel 10
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

## Full Rule File Example

Filename: rules_midimaster/my_live_setup.json

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
      "ch_in": 15,          // Channel 16
      "value_1_in": 48,     // Note C3
      "action": "play"
    },
    {
      "device_in": "akai_mpk",
      "event_in": "note_on",
      "ch_in": 15,
      "value_1_in": 49,     // Note C#3
      "action": "stop"
    },
    {
      "device_in": "akai_mpk",
      "event_in": "cc",
      "ch_in": 0,           // Channel 1
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

To use this file:

```
python midimaster.py my_live_setup
```

## Troubleshooting

- **"No physical MIDI output ports available."**: Ensure your MIDI devices are connected and recognized by the OS before starting MIDImaster.

- **"Error opening virtual port..."**: Verify you have a working virtual MIDI backend (loopMIDI, IAC Driver, etc.).

- **Input mappings are not working**:
  
  - Check that the alias in device_in matches an entry in device_alias, and that the value in device_alias is a substring of the actual MIDI input port name (visible with --list-ports).
  
  - Ensure your MIDI controller is sending on the specified channel (ch_in) and with the specified values (event_in, value_1_in). Use a MIDI monitor to verify the messages your device sends.

- **The TUI looks strange or is unresponsive**: It might be a compatibility issue with your terminal. Try a different terminal or ensure prompt_toolkit is up to date.

## License

GNU AGPLv3 License. See LICENSE file.

## Contributions

Contributions, ideas, and bug reports are welcome. Please open an issue on the GitHub repository.