# midimaster - Comprehensive Reference Guide

**midimaster** is a powerful MIDI Beat Clock Master application written in Python. It provides a terminal-based interface for managing MIDI clock synchronization, device control, and complex MIDI routing scenarios. This guide covers all configuration options and practical examples.

## Table of Contents
- [Overview](#overview)
- [Configuration Files](#configuration-files)
- [Main Configuration File](#main-configuration-file)
- [Rule Files Structure](#rule-files-structure)
- [Device Aliases](#device-aliases)
- [Clock Settings](#clock-settings)
- [MIDI Mappings](#midi-mappings)
- [OSC Integration](#osc-integration)
- [Command Line Usage](#command-line-usage)
- [Practical Examples](#practical-examples)
- [Troubleshooting](#troubleshooting)

## Overview

midimaster acts as a MIDI clock generator and router that can:
- Generate and send MIDI clock signals to multiple devices
- Respond to MIDI transport commands (start/stop/continue)
- Map MIDI events to transport actions and BPM control
- Provide OSC control capabilities
- Support both physical and virtual MIDI ports
- Offer an interactive terminal interface for real-time control

## Configuration Files

### Main Configuration File

The main configuration file `midimaster.conf.json` contains global application settings:

```json
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

#### General Settings
- `default_bpm`: Default BPM value when starting (20.0-300.0)
- `default_virtual_port_name`: Name for virtual MIDI output ports

#### OSC Configuration
- `enabled`: Enable/disable OSC functionality
- `listen_ip`: IP address to listen for OSC commands (use "0.0.0.0" for all interfaces)
- `listen_port`: Port for receiving OSC commands
- `send_ip`: Target IP for sending OSC status updates
- `send_port`: Target port for sending OSC status updates

### Rule Files Structure

Rule files are stored in the `rules/` directory and define MIDI mappings and device configurations. They support two naming conventions for MIDI mappings:

1. `input_mappings` (recommended, newer format)
2. `midi_filter` (legacy format, still supported)

## Device Aliases

Device aliases simplify configuration by creating short names for MIDI devices:

```json
{
  "device_alias": {
    "my_controller": "X-TOUCH MINI",
    "my_synth": "JUNO-60",
    "drum_machine": "TR-808",
    "virtual_daw": "LoopMIDI Port 1"
  }
}
```

Device matching is case-insensitive and uses substring matching. For example, "X-TOUCH" will match "Behringer X-TOUCH MINI".

## Clock Settings

Configure the default BPM and output device for MIDI clock:

```json
{
  "clock_settings": {
    "default_bpm": 128.0,
    "device_out": "my_synth"
  }
}
```

- `default_bpm`: Starting BPM (overrides main config default)
- `device_out`: Default output device (uses device alias or partial name)

Note: `device_out` only applies if no other selection method is used (interactive selector or `--virtual-ports`).

## MIDI Mappings

MIDI mappings define how incoming MIDI events trigger actions. Both `input_mappings` and `midi_filter` arrays are supported.

### Basic Structure

```json
{
  "input_mappings": [
    {
      "device_in": "my_controller",
      "event_in": "note_on",
      "ch_in": 0,
      "value_1_in": 60,
      "action": "play"
    }
  ]
}
```

### Required Fields
- `device_in`: Device alias or partial name for input device
- `event_in`: Type of MIDI event to capture
- `action`: Action to trigger

### Optional Fields
- `ch_in`: MIDI channel (0-15, where 0 = channel 1)
- `value_1_in`: Specific value to match (note number, CC number, program number)
- `bpm_scale`: Configuration for BPM control actions

### Event Types

#### Transport Events
- `start`: MIDI Start message
- `stop`: MIDI Stop message
- `continue`: MIDI Continue message

#### Note Events
- `note`: Matches both note_on and note_off
- `note_on`: Note on events only
- `note_off`: Note off events only

#### Control Events
- `cc`: Control Change messages
- `pc`: Program Change messages

### Actions

#### Transport Actions
- `play`: Start playback (or continue if paused)
- `stop`: Stop playback
- `pause`: Pause playback (only works if currently playing)
- `continue`: Continue from pause (only works if currently paused)

#### BPM Control
- `bpm`: Control BPM using incoming values

### BPM Scaling

For BPM control actions, use `bpm_scale` to map input ranges to BPM ranges:

```json
{
  "device_in": "my_controller",
  "event_in": "cc",
  "ch_in": 0,
  "value_1_in": 74,
  "action": "bpm",
  "bpm_scale": {
    "range_in": [0, 127],
    "range_out": [80, 160]
  }
}
```

- `range_in`: Input value range [min, max]
- `range_out`: Output BPM range [min_bpm, max_bpm]

## OSC Integration

midimaster supports OSC for external control and status reporting.

### Incoming OSC Commands

- `/midimaster/play`: Start playback
- `/midimaster/stop`: Stop playback
- `/midimaster/pause`: Pause playback
- `/midimaster/bpm/set <float>`: Set BPM value

### Outgoing OSC Messages

- `/midimaster/status <string>`: Current status ("PLAYING", "STOPPED", "PAUSED")
- `/midimaster/bpm/current <float>`: Current BPM value

## Command Line Usage

```bash
python midimaster.py [rule_file] [options]
```

### Arguments
- `rule_file`: Optional rule file name from `rules/` directory (without .json extension)

### Options
- `--virtual-ports`: Enable virtual MIDI output port
- `--vp-out NAME`: Set virtual port name (default from config)
- `--list-ports`: List available MIDI ports and exit

### Examples

```bash
# Use default.json rule file (if exists)
python midimaster.py

# Use specific rule file
python midimaster.py my_setup

# Use virtual ports
python midimaster.py --virtual-ports

# Custom virtual port name
python midimaster.py my_setup --virtual-ports --vp-out "MyCustomPort"

# List available MIDI ports
python midimaster.py --list-ports
```

## Practical Examples

### Example 1: Basic Transport Control

Control playback using MIDI start/stop messages from a hardware sequencer:

```json
{
  "device_alias": {
    "sequencer": "KEYSTEP",
    "drum_machine": "TR-8S"
  },
  "input_mappings": [
    {
      "device_in": "sequencer",
      "event_in": "start",
      "action": "play"
    },
    {
      "device_in": "sequencer",
      "event_in": "stop",
      "action": "stop"
    },
    {
      "device_in": "sequencer",
      "event_in": "continue",
      "action": "play"
    }
  ],
  "clock_settings": {
    "default_bpm": 120.0,
    "device_out": "drum_machine"
  }
}
```

### Example 2: Advanced BPM Control

Use a MIDI controller with knobs/faders to control BPM and transport:

```json
{
  "device_alias": {
    "controller": "X-TOUCH MINI",
    "synth": "JUNO-106"
  },
  "input_mappings": [
    {
      "_comment": "Play button - Note C1 on channel 10",
      "device_in": "controller",
      "event_in": "note_on",
      "ch_in": 9,
      "value_1_in": 36,
      "action": "play"
    },
    {
      "_comment": "Stop button - Note C#1 on channel 10",
      "device_in": "controller",
      "event_in": "note_on",
      "ch_in": 9,
      "value_1_in": 37,
      "action": "stop"
    },
    {
      "_comment": "Pause button - Note D1 on channel 10",
      "device_in": "controller",
      "event_in": "note_on",
      "ch_in": 9,
      "value_1_in": 38,
      "action": "pause"
    },
    {
      "_comment": "BPM control - CC 74 maps to 80-160 BPM",
      "device_in": "controller",
      "event_in": "cc",
      "ch_in": 0,
      "value_1_in": 74,
      "action": "bpm",
      "bpm_scale": {
        "range_in": [0, 127],
        "range_out": [80, 160]
      }
    }
  ],
  "clock_settings": {
    "default_bpm": 120.0,
    "device_out": "synth"
  }
}
```

### Example 3: Multiple Device Setup

Configure multiple input and output devices for complex setups:

```json
{
  "device_alias": {
    "foot_controller": "FCB1010",
    "keyboard": "nanoKEY2",
    "drum_machine": "TR-8S",
    "daw_port": "Virtual_Port_1"
  },
  "input_mappings": [
    {
      "_comment": "Foot controller Program Change 0 = Play",
      "device_in": "foot_controller",
      "event_in": "pc",
      "ch_in": 15,
      "value_1_in": 0,
      "action": "play"
    },
    {
      "_comment": "Foot controller Program Change 1 = Stop",
      "device_in": "foot_controller",
      "event_in": "pc",
      "ch_in": 15,
      "value_1_in": 1,
      "action": "stop"
    },
    {
      "_comment": "Keyboard modwheel controls BPM",
      "device_in": "keyboard",
      "event_in": "cc",
      "ch_in": 0,
      "value_1_in": 1,
      "action": "bpm",
      "bpm_scale": {
        "range_in": [0, 127],
        "range_out": [60, 180]
      }
    }
  ],
  "clock_settings": {
    "default_bpm": 100.0
  }
}
```

### Example 4: OSC-Enabled Setup

Configuration with OSC support for DAW integration:

```json
{
  "device_alias": {
    "control_surface": "PUSH2",
    "virtual_out": "IAC_OUT"
  },
  "input_mappings": [
    {
      "device_in": "control_surface",
      "event_in": "note_on",
      "ch_in": 0,
      "value_1_in": 85,
      "action": "play"
    },
    {
      "device_in": "control_surface",
      "event_in": "note_on",
      "ch_in": 0,
      "value_1_in": 86,
      "action": "stop"
    }
  ],
  "clock_settings": {
    "default_bpm": 128.0,
    "device_out": "virtual_out"
  }
}
```

Main config for OSC:
```json
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

### Example 5: Legacy Format Support

Using the legacy `midi_filter` format (still supported):

```json
{
  "device_alias": {
    "input_device": "ARTURIA"
  },
  "midi_filter": [
    {
      "_comment": "Legacy format - still works",
      "device_in": "input_device",
      "event_in": "start",
      "action": "play"
    },
    {
      "device_in": "input_device",
      "event_in": "stop",
      "action": "stop"
    }
  ],
  "clock_settings": {
    "default_bpm": 140.0
  }
}
```

## Keyboard Controls

When running midimaster, the following keyboard controls are available:

### Transport Control
- **Space** or **c**: Play/Pause toggle
- **Enter**: Play when stopped, Stop when playing/paused
- **p**: Play (only when not playing)
- **s**: Stop (only when not stopped)

### BPM Control
- **0-9**: Enter BPM digits (3 digits maximum, auto-applies)
- **Enter**: Apply entered BPM immediately
- **+**: Increase BPM by 1
- **-**: Decrease BPM by 1
- **b**: Toggle BPM lock (prevents BPM changes)

### Device Management
- **i**: Change input device (opens selector)
- **o**: Change output device (opens selector)

### Navigation (when selectors are active)
- **↑/↓**: Navigate device list
- **Enter**: Select device
- **Esc**: Cancel selection

### Application Control
- **q** or **Esc**: Quit application
- **Ctrl+C**: Force quit

## Troubleshooting

### Common Issues

#### No MIDI Ports Found
- Ensure MIDI devices are connected and recognized by the operating system
- Use `--list-ports` to verify available ports
- Check device drivers and MIDI software

#### Device Not Responding
- Verify device aliases match actual device names (substring matching)
- Check MIDI channels and event types in mappings
- Ensure devices are set to send/receive on correct channels

#### BPM Control Not Working
- Verify `bpm_scale` ranges are correct
- Check that CC numbers match your controller
- Ensure BPM lock is not enabled (press 'b' to toggle)

#### OSC Not Working
- Verify IP addresses and ports in configuration
- Check firewall settings
- Ensure target application is listening on specified port

### Performance Tips

- Use specific device name substrings to avoid conflicts
- Limit the number of active MIDI mappings for better performance
- Close unused MIDI ports to free system resources

### Configuration Validation

- JSON files must be valid (use a JSON validator if unsure)
- Device aliases are case-insensitive but should be consistent
- BPM values are clamped to 20.0-300.0 range
- MIDI channels are 0-indexed (0 = channel 1, 15 = channel 16)

## Advanced Usage Notes

### Channel Handling
- When `ch_in` is specified, only messages on that channel will trigger the action
- Messages without channels (start/stop/continue) ignore `ch_in` requirements
- Use different channels to separate control functions

### Value Matching
- `value_1_in` matches note numbers for note events
- `value_1_in` matches CC numbers for control_change events
- `value_1_in` matches program numbers for program_change events
- Omit `value_1_in` to match any value of the specified event type

### Multiple Mappings
- Multiple mappings can respond to the same device/event combination
- Mappings are processed in order
- Use comments (`_comment`) to document complex configurations

### Virtual Ports
- Virtual ports allow communication with DAWs and software
- Use `--virtual-ports` flag or configure in rule files
- Virtual port names should be unique in your system

This reference guide covers all major functionality of midimaster. For specific use cases not covered here, combine the basic concepts and refer to the provided examples as templates.