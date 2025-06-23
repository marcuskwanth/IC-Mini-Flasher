"""
IC-Project : Mini-Flasher GUI - build 0618
────────────────────────────────────────────────────────────────────────
Tested with Python 3.11, ttkbootstrap 1.10, pyserial 3.5

To-do:
1. Function to send requesting packet data to the ESP32 and reflect the settings.
"""

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import serial, serial.tools.list_ports, json, subprocess, os, time

import bluetooth, glob, platform
"""
Package "pybluez", please follow this github comment for proper installation, make sure to pip install backports.tarfile first. 
https://github.com/pybluez/pybluez/issues/431#issuecomment-2191842543
For Windows user, pls make sure Microsoft Visual C++ 14.0 is installed 
For macOS user, pls make sure to pip install python-lightblue
"""

# ──────────────── Global configuration ───────────────────────────────
CONFIG_FILE         = "config.txt"
SETTING_FILE        = "settings.txt"
TARGET_PORT         = 1                 # 1 For BT-SPP!
BAUDRATE            = 115_200
HEADER1, HEADER2    = 0x5A, 0xA5
READ_TIMEOUT        = 0.3               # seconds for optional loop-back read
COOLDOWN            = 10

device_name         = "ESP32"
last_send_time      = 0                 # Track when last send occurred
intensity_color     = 'dark'
off_time_color      = 'secondary'
row_num_text        = "Colors: "
select_text         = "Select Color"
delete_text         = "X"
refresh_text        = "↻"
add_row_text        = "Add Color Row"
send_text           = f"Send to {device_name}"
info_prefix         = "*INFO: "
error_prefix        = "*ERROR: "
default_cycles      = 5

max_intensity       = 255
max_on_off_time     = 100
max_row             = 250               # max no. of table rows

headers = ['Intensity (0-255)','On_Time (100 ms)','Off_Time (100 ms)', 'MMI On_Time','MMI Off_Time', 'Remove']
colors  = ["Red","Green","Blue","Infrared"]
colors_mapper = {
    "Red":"danger",
    "Green":"success",
    "Blue":"primary",
    "Infrared":"warning", 
    select_text:"secondary"
}

# ──────────────── Tk root window ─────────────────────────────────────
root = tk.Tk()
root.title("IC-Project  ·  Mini-Flasher GUI")
row_count_var = tk.StringVar(value=f"{row_num_text}?")

# ──────────────── Bluetooth SPP utilities ────────────────────────────
bt_socket = None
bt_connected = False
bt_mac = tk.StringVar(value="")         # bluetooth mac address 

mode_var = tk.IntVar(value=0)    # 0 = USB, 1 = Bluetooth

"""For macOS troubleshooting: List the Bluetooth devices in a macOS serial format"""
def list_bt_devices():
    print("Available Bluetooth devices in /dev:")
    print("\n".join(glob.glob("/dev/cu.*") + glob.glob("/dev/tty.*")))

"""Connect to the selected Bluetooth device"""
def connect_bluetooth():
    global bt_socket, bt_connected
    print(f"{info_prefix}Bluetooth MAC: {bt_mac.get()}")
    bt_addr = bt_mac.get()
    bt_name = bt_addr[:bt_addr.index("(")-1]
    if "(" in bt_addr and ")" in bt_addr:
        bt_addr = bt_addr[bt_addr.index("(")+1:bt_addr.index(")")]

    # macOS handling
    if platform.system() == "Darwin":
        dev_ports = glob.glob("/dev/cu.*")
        dev_path = None
        for port in dev_ports:
            if bt_name in port:
                dev_path = port
                break
        if not dev_path:
            print(f"{error_prefix}Could not find matching serial port for {bt_name}.")
            messagebox.showerror("Error", f"Could not find serial port for {bt_name}.")
            return False

        try:
            print(f"{info_prefix}Connecting to {dev_path}")
            bt_socket = serial.Serial(
                port=dev_path,
                baudrate=BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=READ_TIMEOUT,
                rtscts=False,
                dsrdtr=False
            )
            bt_connected = True
            print(f"{info_prefix}Connected via {dev_path}")
            return True
        except Exception as e:
            print(f"{error_prefix}macOS connection failed: {e}")
            messagebox.showerror("Error", f"macOS Bluetooth connection failed: {e}") 
            return False

    # Windows/Linux handling
    try:
        print(f"{info_prefix}Connecting to {bt_addr}")
        bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        bt_socket.connect((bt_addr, TARGET_PORT))
        bt_socket.settimeout(READ_TIMEOUT)
        bt_connected = True
        print(f"{info_prefix}Bluetooth connected to {bt_addr}")
        return True
    except Exception as e:
        print(f"{error_prefix}Connection failed: {e}")
        messagebox.showerror("Error", f"Bluetooth connection failed: {e}") 
        bt_connected = False
        return False

"""Disconnect from Bluetooth device"""
def disconnect_bluetooth():
    global bt_socket, bt_connected
    if bt_socket:
        try:
            bt_socket.close()
            print(f"{info_prefix}Bluetooth connection closed")
        except Exception as e:
            print(f"{error_prefix}Error closing Bluetooth: {e}")
        finally:
            bt_socket = None
            bt_connected = False

"""Re-scan bluetooth device and repopulate combobox."""
def refresh_bt_list(combo):
    print(f"{info_prefix}Scanning for Bluetooth devices...")
    combo.set("Scanning...")
    root.update()
    
    # macOS discovery
    if platform.system() == "Darwin":
        try:
            print(f"{info_prefix}Using macOS system profiler")
            result = subprocess.run(
                ["system_profiler", "SPBluetoothDataType", "-json"],
                capture_output=True,
                text=True
            )
            devices = []
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Parse system_profiler output
                for device in data.get("SPBluetoothDataType", [{}])[0].get("device_connected", []):
                    if "device_address" in device:
                        addr = device["device_address"]
                        name = device.get("device_name", "Unknown")
                        devices.append((addr, name))
            if not devices:
                print(f"{info_prefix}Trying blueutil fallback")
                try:
                    result = subprocess.run(
                        ["blueutil", "--paired", "--format", "json"],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        for device in json.loads(result.stdout):
                            devices.append((device["address"], device["name"]))
                except:
                    pass
            device_list = [f"{name} ({addr})" for addr, name in devices]
            root.after(0, lambda: update_bt_list(combo, device_list))
        except Exception as e:
            print(f"{error_prefix}macOS Bluetooth scanning failed: {e}")
            root.after(0, lambda: combo.set("Scan failed, try again"))
        return

    # other (Windows)
    try:
        devices = bluetooth.discover_devices(duration=8, lookup_names=True)
        print(f"{info_prefix}Found {len(devices)} Bluetooth devices")

        # Format device list: "Device Name (MAC Address)"
        device_list = [f"{name} ({addr})" for addr, name in devices]
        root.after(0, lambda: update_bt_list(combo, device_list))
    except Exception as e:
        print(f"{error_prefix}Bluetooth scanning failed: {e}")
        messagebox.showerror("Error", f"Bluetooth scanning failed: {e}") 
        root.after(0, lambda: combo.set("Scan failed, try again"))
    
    # Run scan in separate thread to prevent UI freeze
    # threading.Thread(target=scan_thread, daemon=True).start()

"""Update Bluetooth combo box with scan results"""
def update_bt_list(combo, device_list):
    if not device_list:
        combo.set("No devices found")
        combo["values"] = []
        bt_mac.set("")
        return
    
    combo["values"] = device_list
    combo.set(device_list[0])

"""Send data over Bluetooth connection"""
def send_bluetooth(packet: bytes, expect_echo: int = 0) -> bytes:
    global bt_connected
    if not bt_connected:
        if not connect_bluetooth():
            return b""
    try:
        # macOS uses serial connection
        if platform.system() == "Darwin":  
            if not bt_socket.is_open:
                bt_socket.open()  # Reopen if closed unexpectedly
            bt_socket.reset_input_buffer()
            bt_socket.reset_output_buffer()
            bt_socket.write(packet)
            bt_socket.flush()
        else:  # Windows/Linux
            bt_socket.send(packet)
        echo = b""
        if expect_echo:
            echo = bt_socket.recv(expect_echo)
            print(f"{info_prefix}Received echo: {bar_hex(echo)}")
        print(f"{info_prefix}Sent {len(packet)} bytes via Bluetooth SPP: {bt_mac.get()}")
        info_status(msg=f"Message sent to {device_name} successfully via Bluetooth!")
        return echo
    except Exception as e:
        print(f"{error_prefix}Communication error: {e}")
        messagebox.showerror("Error", f"Bluetooth failed: {e}") 
        bt_connected = False
        return b""

# ──────────────── USB Serial utilities ──────────────────────────────
usb_socket = None
port_var = tk.StringVar(value="")        # currently selected port

"""Return list of (device, description) tuples."""
def available_ports():
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]

"""Re-scan system ports and repopulate combobox."""
def refresh_port_list(combo):
    print(f"{info_prefix}Refreshing port list")
    ports = available_ports()
    combo["values"] = [f"{d}  –  {s}" for d, s in ports]
    # keep old selection if still present, else auto-pick first
    current = port_var.get()
    if current and any(current == d for d, _ in ports):
        pass
    elif ports:
        port_var.set(combo["values"][0])
    else:
        port_var.set("")

"""Disconnect from USB Port"""
def disconnect_usb():
    global usb_socket
    if usb_socket:
        try:
            usb_socket.close()
            print(f"{info_prefix}USB connection closed")
        except Exception as e:
            print(f"{error_prefix}Error closing USB Port: {e}")
        finally:
            usb_socket = None

"""Open selected COM port, transmit packet, optionally read echo."""
def send_usb(packet: bytes, expect_echo: int = 0)  -> bytes:
    global usb_socket
    port = port_var.get()
    if " " in port:                 # ← NEW: take only first token ► "COM4"
        port = port.split()[0]      
    if not port:
        print(f"{error_prefix}No serial port selected.")
        messagebox.showerror("Error", f"No USB serial port selected!") 
    try:
        usb_socket = serial.Serial(port, BAUDRATE, timeout=READ_TIMEOUT)
        with usb_socket as ser:
            n = ser.write(packet)
            print(f"{info_prefix}PC wrote {n}/{len(packet)} bytes to {port}")
            if expect_echo:
                echo = ser.read(expect_echo)
                print(f"PC  echo  {bar_hex(echo)}")
                return echo
            info_status(msg=f"Message sent to {device_name} successfully via USB serial {port}!")
    except serial.SerialException as e:
        print(f"{error_prefix}opening {port}: {e}")
        messagebox.showerror("Error", f"Error whilst opening port {port}!") 

    print(f"{info_prefix}Sent {len(packet)} bytes via USB Serial {port}")

# ──────────────── Packet helpers ────────────────────────────────────
"""Build the payload data"""
def build_payload() -> str:
    pieces=[]
    for i in range(len(params)):
        if params[i][0] == 'N':
            return False
        pieces.extend(map(str,params[i]))
    pieces.extend(["C", str(cycles.get())])
    return ",".join(pieces)

"""Build the packet data with the header and payload data"""
def build_packet(payload: str) -> bytes:
    sync   = bytes([HEADER1, HEADER2])
    data   = payload.encode('ascii')
    length = len(data).to_bytes(2, 'little')
    chk    = (sum(sync + length + data) & 0xFFFF).to_bytes(2, 'little')
    return sync + length + data + chk

# ──────────────── NEW: prettier hex printer ──────────────────────────
"""
Convert bytes to grouped hex string, e.g.
b'\x5a\xA5…' ⇒ '5a a5 19 00 50 | 6c 65 61 73 65 | …'
"""
def bar_hex(pkt: bytes, chunk: int = 5) -> str:
    hexbytes = pkt.hex(' ').split()                    # ['5a', 'a5', ...]
    groups   = [' '.join(hexbytes[i:i+chunk])          # 5-byte slices
                for i in range(0, len(hexbytes), chunk)]
    return ' | '.join(groups)

# ──────────────── GUI data structures ───────────────────────────────
rows, params = [], []   # rows = structure + values shown in the boxes, params = values stored in the program
cycles = tk.IntVar(value=default_cycles)

# ──────────────── GUI Setting file save/load ────────────────────────
"""Save current settings to file"""
def save_settings():
    debug_print_value()
    settings = {
        "rows": [],
        "cycles": cycles.get()
    }
    for row in params:
        settings["rows"].append({
            "color": row[0],
            "intensity": row[1],
            "on_time": row[2],
            "off_time": row[3]
        })
    # File I/O
    try:
        with open(SETTING_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"{info_prefix}Settings saved to {SETTING_FILE}")
        info_status(msg=f"Settings saved to {SETTING_FILE} successfully!")
    except Exception as e:
        print(f"{error_prefix}Saving settings: {e}")
        messagebox.showerror("Error", f"Failed to save settings: {e}")

"""Load settings from file"""
def load_settings():
    if not os.path.exists(SETTING_FILE): return False
    # File I/O
    try:
        with open(SETTING_FILE, 'r') as f:
            settings = json.load(f)
        # Clear existing rows then load new rows
        while len(rows) > 0:
            delete_row(0)   
        for row in settings.get("rows", []):
            add_new_row()
            i = len(rows) - 1
            rows[i]['vars']['color'].set(enum_color(row.get("color")))         # Update color button's color
            rows[i]['widgets'][0].config(text=enum_color(row.get("color")))    # Update color button's text
            rows[i]['vars']['intensity'].set(row.get("intensity", max_intensity))
            rows[i]['vars']['on_time'].set(row.get("on_time", 1))
            rows[i]['vars']['off_time'].set(row.get("off_time", 1))
            update_params(i)
            update_row_style(i)
        cycles.set(settings.get("cycles", default_cycles))

        print(f"{info_prefix}Settings loaded from {SETTING_FILE}")
        info_status(msg=f"Settings loaded from {SETTING_FILE} successfully!")
        debug_print_value()
        return True
    except Exception as e:
        print(f"{error_prefix}Loading settings: {e}")
        messagebox.showerror("Error", f"Failed to load settings: {e}")
        return False

# ──────────────── GUI connection cfg file r/w ────────────────────────
"""Load configuration from file or return defaults"""
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"mode": 0, "com_port": "", "bt_mac": ""}
    
    config = {"mode": 0, "com_port": "", "bt_mac": ""}
    try:
        print(f"{info_prefix}Configuration loading")
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                if key == "mode":
                    config["mode"] = int(value)
                elif key == "com_port":
                    config["com_port"] = value
                elif key == "bt_mac":
                    config["bt_mac"] = value
    except Exception as e:
        print(f"{error_prefix}Loading config: {e}")
        messagebox.showerror("Error", f"Error whilst loading {CONFIG_FILE}: {e}!") 
    return config

"""Save configuration to file"""
def save_config(mode, com_port, bt_mac):
    try:
        with open(CONFIG_FILE, 'w') as f:
            f.write(f"mode={mode}\n")
            f.write(f"com_port={com_port}\n")
            f.write(f"bt_mac={bt_mac}\n")
        print(f"{info_prefix}Configuration saved, now using mode {mode}")
    except Exception as e:
        print(f"{error_prefix}Saving config: {e}")
        messagebox.showerror("Error", f"Error whilst saving {CONFIG_FILE}: {e}!") 

"""Sequence for loading the config values to the variables"""
def config_setval():
    config = load_config()
    mode_var.set(config["mode"])
    port_var.set(config["com_port"])
    bt_mac.set(config["bt_mac"])

# ──────────────── GUI connection cfg ──────────────────────────────
"""The code for the connection setting window"""
def config_window():
    config_win = tk.Toplevel(root)
    config_win.title("IC-Project  ·  Connection Settings")
    config_win.resizable(False, False)
    config_win.grab_set()
    config_setval()
    info_status(msg=f"Connection Setting is opened.")
    
    # Mode selection
    mode_frame = ttk.Frame(config_win)
    mode_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(mode_frame, text="Connection Mode:").grid(row=0, column=0, sticky='w', padx=(0, 10))
    ttk.Radiobutton(mode_frame, text="USB Serial", variable=mode_var, value=0).grid(row=0, column=1, sticky='w', padx=5)
    ttk.Radiobutton(mode_frame, text="Bluetooth SPP", variable=mode_var, value=1).grid(row=0, column=2, sticky='w', padx=5)
    
    # Port selection
    val_frame = ttk.Frame(config_win)
    val_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(val_frame, text="USB COM Port:").grid(row=0, column=0, sticky='w', padx=(0, 10))
    port_combo = ttk.Combobox(val_frame, textvariable=port_var, width=25)
    port_combo.grid(row=0, column=1, sticky='ew', padx=5)

    ttk.Label(val_frame, text="Bluetooth Host:").grid(row=1, column=0, sticky='w', padx=(0,10))
    btmac_combo = ttk.Combobox(val_frame, textvariable=bt_mac, width=25)
    btmac_combo.grid(row=1, column=1, sticky='ew', padx=5)
    
    refresh_port_btn = ttk.Button(val_frame, text=refresh_text, width=3, command=lambda: refresh_port_list(port_combo), bootstyle="secondary-outline")
    refresh_port_btn.grid(row=0, column=2, padx=(5, 0))

    refresh_bt_btn = ttk.Button(val_frame, text=refresh_text, width=3, command=lambda: refresh_bt_list(btmac_combo), bootstyle="secondary-outline")
    refresh_bt_btn.grid(row=1, column=2, padx=(5, 0))
    
    # Buttons
    btn_frame = ttk.Frame(config_win)
    btn_frame.pack(fill='x', pady=20)

    def on_save():
        save_config(mode_var.get(), port_var.get(), bt_mac.get())
        update_status()
        config_win.destroy()

    # HELP FUNCTION: Shows instructions for finding ports/devices
    def show_help():
        help_text = f"""
        How to find USB Serial Port / Bluetooth Host:
        
        USB Serial Port (COM Port):
        1. Connect your {device_name} via USB
        2. For Windows:
           - Open Device Manager
           - Expand 'Ports (COM & LPT)'
           - Look for 'USB Serial Device (COMx)' or similar
        3. For macOS:
           - Open Terminal
           - Run: ls /dev/cu.*
           - Look for /dev/cu.usbserial-xxxx or similar
        4. Click the Refresh button to update the list
        
        Bluetooth Device:
        1. Ensure the {device_name} is powered on and in pairing mode
        2. For Windows:
           - Open Bluetooth settings
           - Pair with the correct device
           - Click the Refresh button to update the list
        3. For macOS:
           - Open System Preferences > Bluetooth
           - Pair with the correct device
           - Click the Refresh button to update the list
        4. If device doesn't appear:
           - Ensure it's not connected to another PC
           - Re-pair the {device_name}
        """
        messagebox.showinfo("Connection Help", help_text)

    # Add Help button to button frame
    ttk.Button(btn_frame, text="Help", command=show_help, bootstyle="info", width=5).pack(side='left', padx=20)
    ttk.Button(btn_frame, text="Cancel", command=config_win.destroy, bootstyle="secondary", width=8).pack(side='right', padx=20)
    ttk.Button(btn_frame, text="Save", command=on_save, bootstyle="success", width=8).pack(side='right')

    config_win.wait_window(config_win)
    info_status(msg=f"Ready to send to {device_name}.")

# ──────────────── GUI callbacks ─────────────────────────────────────
"""Printing out the values of rows and params"""
def debug_print_value():
    print(f"====================")
    for i in range(len(rows)):
        print(f"{rows[i]['vars']['color'].get()}, {rows[i]['vars']['intensity'].get()}, {rows[i]['vars']['on_time'].get()}, {rows[i]['vars']['off_time'].get()}; ", end="")
    print(f"\n{params} \n====================\n")
    
"""TWO functions for enumating color into single letter or full letter"""
def color_enum(c): # Long-form to short-form
    return {'Red':'R','Green':'G','Blue':'B','Infrared':'I'}.get(c,'N')
def enum_color(c): # Short-form to long-form
    return {'R':'Red','G':'Green','B':'Blue','I':'Infrared'}.get(c,select_text)

"""Validate spinbox input and clamp to min/max values"""
def validate_spinbox(var, min_val, max_val):
    current = var.get()
    if current < min_val:
        messagebox.showinfo("Info", f"Minimum value reached! ({min_val})") 
        var.set(min_val)
    elif current > max_val:
        messagebox.showinfo("Info", f"Maximum value reached! ({max_val})") 
        var.set(max_val)
    return True

"""Synchronise params list when a widget variable changes."""
def update_params(i, _=None):
    if i >= len(params): return
    values = rows[i]['vars']

    # Validate and clamp values before updating params
    validate_spinbox(values['intensity'], 1, max_intensity)
    validate_spinbox(values['on_time'], 1, max_on_off_time)
    validate_spinbox(values['off_time'], 1, max_on_off_time)

    params[i] = [color_enum(values['color'].get()),
                 int(values['intensity'].get()),
                 int(values['on_time'].get()),
                 int(values['off_time'].get())]
    debug_print_value()

"""Update the color of the sliders when the color selection changes"""
def update_row_style(i):
    if i >= len(rows): return
    style = colors_mapper.get(rows[i]['vars']['color'].get(), "secondary")
    rows[i]['widgets'][0].configure(bootstyle=style)
    rows[i]['widgets'][2].configure(bootstyle=style)
    rows[i]['widgets'][4].configure(bootstyle=style)

"""Callback for the add row button"""
def add_new_row():
    if len(rows) >= max_row:
        print(f"{info_prefix}maximum rows reached")
        messagebox.showinfo("Info", f"Maximum row reached! ({max_row})") 
        return
    i = len(rows)
    v = {'color':     ttk.StringVar(value=select_text),     # v = row's values in this function!
         'intensity': ttk.IntVar(value=max_intensity),
         'on_time':   ttk.IntVar(value=1),
         'off_time':  ttk.IntVar(value=1)}
    
    col_button = ttk.Menubutton(table, text=v['color'].get(), width=12, bootstyle="secondary")
    menu = tk.Menu(col_button); 
    col_button['menu'] = menu
    def choose(c):
        v['color'].set(c); 
        col_button.config(text=c); 
        update_row_style(i)
    for c in colors:
        menu.add_command(label=c, command=lambda c=c: choose(c))

    intensity_spin = ttk.Spinbox(
        table, textvariable=v['intensity'], from_=1, to=max_intensity, 
        width=2, bootstyle=intensity_color, command=lambda: validate_spinbox(v['intensity'], 1, max_intensity)
    )
    on_spin = ttk.Spinbox(
        table, textvariable=v['on_time'], from_=1, to=max_on_off_time, 
        width=2, bootstyle="secondary", command=lambda: validate_spinbox(v['on_time'], 1, max_on_off_time)
    )
    off_spin = ttk.Spinbox(
        table, textvariable=v['off_time'], from_=1, to=max_on_off_time, 
        width=2, bootstyle=off_time_color, command=lambda: validate_spinbox(v['off_time'], 1, max_on_off_time)
    )
    on_update  = lambda val: v['on_time'].set(int(float(val)))
    off_update = lambda val: v['off_time'].set(int(float(val)))

    del_button = ttk.Button(table, text=delete_text, width=2, command=lambda idx=i: delete_row(idx), bootstyle="danger")

    # widgets
    w = [
        col_button,
        intensity_spin,
        on_spin,
        off_spin,
        ttk.Scale(table, variable=v['on_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=on_update, bootstyle="secondary"),
        ttk.Scale(table, variable=v['off_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=off_update, bootstyle=off_time_color),
        del_button
    ]
    for col, widget in enumerate(w):
        widget.grid(row=i+1, column=col, padx=5, pady=5, sticky="nsew")
        table.grid_columnconfigure(col, weight=1)

    traces = {}
    for name in v:
        traces[name] = v[name].trace_add("write", lambda *_, idx=i, n=name: update_params(idx, n))
    color_trace = v['color'].trace_add("write", lambda *_, idx=i: update_row_style(idx))

    rows.append({
        'widgets': w, 
        'vars': v,
        'traces': traces,
        'color_trace': color_trace
    })
    params.append([color_enum(v['color'].get()), 
                   int(v['intensity'].get()), 
                   int(v['on_time'].get()), 
                   int(v['off_time'].get())])
    update_row_style(i)

    row_count_var.set(f"{row_num_text}{len(rows)}")
    info_status(msg=f"Added row {i+1} successfully!")
    print(f"{info_prefix}added row {i+1}, current number of rows: {len(rows)}")
    debug_print_value()

"""Callback for the delete button on each row"""
def delete_row(i):
    if i >= len(rows): return
    for w in rows[i]['widgets']:
        w.destroy()
    del rows[i], params[i]

    # re-grid rows and update the variable traces below
    for idx in range(i, len(rows)):
        for col, widget in enumerate(rows[idx]['widgets']):
            widget.grid(row=idx+1, column=col)

        for name in rows[idx]['traces']:
            rows[idx]['vars'][name].trace_remove("write", rows[idx]['traces'][name])
        rows[idx]['traces'] = {}
        for name in rows[idx]['vars']:
            rows[idx]['traces'][name] = rows[idx]['vars'][name].trace_add(
                "write", lambda *_, idx=idx, n=name: update_params(idx, n))
        
        rows[idx]['vars']['color'].trace_remove("write", rows[idx]['color_trace'])
        rows[idx]['color_trace'] = rows[idx]['vars']['color'].trace_add(
            "write", lambda *_, idx=idx: update_row_style(idx))

    row_count_var.set(f"{row_num_text}{len(rows)}")
    info_status(msg=f"Deleted row {i+1} successfully!")
    print(f"{info_prefix}deleted row {i+1}, current number of rows: {len(rows)}")
    debug_print_value()

"""Callback for the send to ESP32 button"""
def send_action():
    # Check cooldown first
    global last_send_time
    current_time = time.time()
    if current_time - last_send_time < COOLDOWN:
        remaining = int(COOLDOWN - (current_time - last_send_time))
        messagebox.showinfo("Info", f"Please wait for {remaining} seconds before sending again.")
        return
    if len(rows) < 1:
        messagebox.showerror("Error", f"Cannot send with less than 1 row!")
        return
    payload = build_payload()
    if not payload:
        print(f"{error_prefix}No color selected in 1 or more row(s)")
        messagebox.showerror("Error", f"No color selected in 1 or more row(s)!")
        return
    pkt = build_packet(payload)
    print(f"{info_prefix}PC payload: {payload}")
    print(f"{info_prefix}PC packet : {bar_hex(pkt)}")   # ← uses grouped view

    last_send_time = current_time
    send_btn.config(state="disabled")
    root.after(1000, update_send_button)
    
    if mode_var.get() == 0:  # USB mode
        info_status(msg=f"Attempting to send via USB serial.")
        disconnect_bluetooth()
        send_usb(pkt)
    else:  # Bluetooth mode
        info_status(msg=f"Attempting to send via Bluetooth.")
        disconnect_usb()
        send_bluetooth(pkt)

# Additional Function to update button status during cooldown
def update_send_button():
    global last_send_time
    current_time = time.time()
    remaining = int(COOLDOWN - (current_time - last_send_time))
    if remaining > 0:
        send_btn.config(text=f"Wait ({remaining}s)", state="disabled")
        root.after(1000, update_send_button)
    else:
        send_btn.config(text=send_text, state="normal")

"""Update connection status indicators"""
def update_status():
    config_setval()
    mode_text = "USB" if mode_var.get() == 0 else "Bluetooth"
    mode_color = "info" if mode_var.get() == 0 else "primary"
    mode_indicator.config(text=mode_text, bootstyle=mode_color)

    port_indicator_text = "Port: " if mode_var.get() == 0 else "Host: "
    port = port_var.get()
    host = bt_mac.get()
    port_indicator.config(text=f"{port_indicator_text} {port if mode_var.get() == 0 else host}")

"""Update the status indicator text"""
def info_status(msg="Unknown."):
    status_indicator.config(text=msg)

# ──────────────── GUI layout ────────────────────────────────────────
main   = ttk.Frame(root); 
main.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
table  = ttk.Frame(main)
footer = ttk.Frame(main, relief='ridge')
status_frame = ttk.Frame(main)

# table header
color_label = ttk.Label(table, text="Colours").grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
table.grid_columnconfigure(0, weight=1)
for col, h in enumerate(headers):
    ttk.Label(table, text=h).grid(row=0, column=col+1, padx=5, pady=5, sticky="nsew")
    table.grid_columnconfigure(col, weight=1)

# footer buttons
ttk.Button(footer, text=add_row_text, width=15, bootstyle="danger-outline", command=add_new_row).grid(row=0, column=0, padx=5, pady=5)
send_btn = ttk.Button(footer, text=send_text, width=15, bootstyle="success-outline", command=send_action)
send_btn.grid(row=0, column=1, padx=5, pady=5)

row_counter = ttk.Label(footer, textvariable=row_count_var)
row_counter.grid(row=0, column=2, padx=10, pady=5)

ttk.Label(footer, text="Cycles").grid(row=0, column=3, padx=(20, 5), pady=5)
ttk.Spinbox(footer, from_=1, to=100, textvariable=cycles, width=5).grid(row=0, column=4, padx=5, pady=5)
ttk.Button(footer, text="Configure Connection", width=18, bootstyle="warning-outline", command=config_window).grid(row=0, column=5, padx=5, pady=5)
ttk.Button(footer, text="Save Settings", width=12, bootstyle="primary-outline", command=save_settings).grid(row=0, column=6, padx=5, pady=5)
ttk.Button(footer, text="Load Settings", width=12, bootstyle="info-outline", command=load_settings).grid(row=0, column=7, padx=5, pady=5)

# Connection type and port status
mode_indicator = ttk.Label(status_frame, text="Unknown", bootstyle="danger")
mode_indicator.pack(side="left", padx=(0, 10))
port_indicator = ttk.Label(status_frame, text="Unknown")
port_indicator.pack(side="left")
status_indicator = ttk.Label(status_frame, text="Unknown")
status_indicator.pack(side="right")

add_new_row()  # first empty row
update_status()

# ──────────────── GUI window ────────────────────────────────────────
table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
status_frame.pack(side=tk.BOTTOM, pady=(10,0), fill=tk.X)
footer.pack(side=tk.BOTTOM, pady=(10,0), fill=tk.X)

root.after(50, config_window)
def on_closing():
    print(f"{info_prefix}Closing app")
    disconnect_bluetooth()
    disconnect_usb()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()