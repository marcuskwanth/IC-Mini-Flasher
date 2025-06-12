"""
IC-Project : Mini-Flasher GUI - build 0612
────────────────────────────────────────────────────────────────────────
Tested with Python 3.11, ttkbootstrap 1.10, pyserial 3.5
"""

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import serial, serial.tools.list_ports, os

import bluetooth
"""
Package "pybluez", please follow this github comment for proper installation, and 
make sure Microsoft Visual C++ 14.0 is installed: 
https://github.com/pybluez/pybluez/issues/431#issuecomment-2191842543
"""

# ──────────────── Global configuration ───────────────────────────────
CONFIG_FILE         = "config.txt"
TARGET_PORT         = 1         # 1 For BT-SPP!
BAUDRATE            = 115_200
HEADER1, HEADER2    = 0x5A, 0xA5
READ_TIMEOUT        = 0.3       # seconds for optional loop-back read

intensity_color     = 'dark'
off_time_color      = 'secondary'
select_text         = "Select Color"
delete_text         = "X"
refresh_text        = "↻"
info_prefix         = "*INFO: "
error_prefix        = "*ERROR: "
default_cycles      = 5
max_on_off_time     = 100
max_row             = 250     # max no. of table rows

headers = ['Colors','Intensity (0-255)','On_Time (100 ms)','Off_Time (100 ms)', 'MMI On','MMI Off', 'Action']
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

# ──────────────── Bluetooth SPP utilities ────────────────────────────
bt_socket = None
bt_connected = False
bt_mac = tk.StringVar(value="")         # bluetooth mac address 

"""Connect to the selected Bluetooth device"""
# THE PART THAT NEEDS TROUBLESHOOTING!!!!!!!
def connect_bluetooth():
    global bt_socket, bt_connected
    print(f"{info_prefix}Bluetooth MAC: {bt_mac.get()}")
    bt_addr = bt_mac.get()
    bt_addr = bt_addr[bt_addr.index("(")+1:bt_addr.index(")")]
    try:
        # Create and connect socket
        print(f"{info_prefix}Attempting connection with {bt_mac.get()}")
        bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        bt_socket.connect((bt_addr, TARGET_PORT))
        bt_socket.settimeout(READ_TIMEOUT)
        bt_connected = True
        print(f"{info_prefix}Bluetooth connected to {bt_addr}")
        return True
    except Exception as e:
        print(f"{error_prefix}Bluetooth connection failed: {e}")
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
        except:
            pass
    bt_socket = None
    bt_connected = False

"""Send data over Bluetooth connection"""
def send_bluetooth(packet: bytes):
    global bt_connected
    if not bt_connected:
        if not connect_bluetooth():
            return
    try:
        # Send packet
        bt_socket.send(packet)
        print(f"{info_prefix}Sent {len(packet)} bytes via Bluetooth")
        messagebox.showinfo("Info", f"Message sent to ESP32 successfully via Bluetooth {bt_mac}!")
    except Exception as e:
        print(f"{error_prefix}Bluetooth communication error: {e}")
        messagebox.showerror("Error", f"Bluetooth communication failed: {e}") 
        bt_connected = False

"""Re-scan bluetooth device and repopulate combobox."""
def refresh_bt_list(combo):
    print(f"{info_prefix}Scanning for Bluetooth devices...")
    combo.set("Scanning...")
    root.update()
    
    try:
        # Discover nearby devices
        devices = bluetooth.discover_devices(duration=8, lookup_names=True)
        print(f"{info_prefix}Found {len(devices)} Bluetooth devices")
            
        # Format device list: "Device Name (MAC Address)"
        device_list = []
        for addr, name in devices:
            device_list.append(f"{name} ({addr})")
            
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

# ──────────────── USB Serial utilities ──────────────────────────────
port_var = tk.StringVar(value="")        # currently selected port
mode_var = tk.IntVar(value=0)            # 0 = USB, 1 = Bluetooth

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

"""Open selected COM port, transmit packet, optionally read echo."""
def send_usb(packet: bytes):
    port = port_var.get()
    if " " in port:                 # ← NEW: take only first token ► "COM4"
        port = port.split()[0]      
    if not port:
        print(f"{error_prefix}No serial port selected.")
        messagebox.showerror("Error", f"No USB serial port selected!") 
    try:
        with serial.Serial(port, BAUDRATE, timeout=READ_TIMEOUT) as ser:
            n = ser.write(packet)
            print(f"{info_prefix}PC wrote {n}/{len(packet)} bytes to {port}")
            messagebox.showinfo("Info", f"Message sent to ESP32 successfully via USB serial {port}!")
    except serial.SerialException as e:
        print(f"{error_prefix}opening {port}: {e}")
        messagebox.showerror("Error", f"Error whilst opening port {port}!") 

    print(f"{info_prefix}Sent {len(packet)} bytes via USB Serial {port}")

# ──────────────── Packet helpers ────────────────────────────────────
"""Enumate color into single letter for packet data"""
def color_enum(c):
    return {'Red':'R','Green':'G','Blue':'B','Infrared':'I'}.get(c,'N')

"""Build the payload data"""
def build_payload() -> str:
    pieces=[]
    for row in params:
        pieces.extend(map(str,row))
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
rows, params = [], []
cycles = tk.IntVar(value=default_cycles)

# ──────────────── GUI configuration file r/w ────────────────────────
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

"""Sequence for saving the config values to the variables"""
def config_setval():
    config = load_config()
    mode_var.set(config["mode"])
    port_var.set(config["com_port"])
    bt_mac.set(config["bt_mac"])

# ──────────────── GUI configuration ──────────────────────────────
"""The code for the connection setting window"""
def config_window():
    config_win = tk.Toplevel(root)
    config_win.title("IC-Project  ·  Connection Settings")
    config_win.resizable(False, False)
    config_win.grab_set()
    config_setval()
    
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
    ttk.Button(btn_frame, text="Save", command=on_save, bootstyle="success", width=10).pack(side='right', padx=10)
    ttk.Button(btn_frame, text="Cancel", command=config_win.destroy, bootstyle="secondary", width=10).pack(side='right')

    config_win.wait_window(config_win)

# ──────────────── GUI callbacks ─────────────────────────────────────
"""Synchronise params list when a widget variable changes."""
def update_params(i, _=None):
    if i >= len(params): return
    values = rows[i]['vars']
    params[i] = [color_enum(values['color'].get()),
                 int(values['intensity'].get()),
                 int(values['on_time'].get()),
                 int(values['off_time'].get())]

"""Update the color of the sliders when the color selection changes"""
def update_row_style(i):
    if i >= len(rows): return
    style = colors_mapper.get(rows[i]['vars']['color'].get(), "secondary")
    rows[i]['widgets'][0].configure(bootstyle=style)
    rows[i]['widgets'][4].configure(bootstyle=style)

"""Callback for the add row button"""
def add_new_row():
    if len(rows) >= max_row:
        print(f"{info_prefix}maximum rows reached")
        messagebox.showerror("Error", f"Maximum row reached! ({max_row})") 
        return
    i = len(rows)
    v = {'color':     ttk.StringVar(value=select_text),
         'intensity': ttk.IntVar(value=255),
         'on_time':   ttk.IntVar(value=1),
         'off_time':  ttk.IntVar(value=1)}
    on_label, off_label = ttk.Label(table), ttk.Label(table)

    on_update  = lambda val: on_label.config(text=str(int(float(val))))
    off_update = lambda val: off_label.config(text=str(int(float(val))))
    
    col_button = ttk.Menubutton(table, text=v['color'].get(), width=12, bootstyle="secondary")
    menu = tk.Menu(col_button); col_button['menu'] = menu
    def choose(c):
        v['color'].set(c); col_button.config(text=c); update_row_style(i)
    for c in colors:
        menu.add_command(label=c, command=lambda c=c: choose(c))

    del_button = ttk.Button(table, text=delete_text, width=2, command=lambda idx=i: delete_row(idx), bootstyle="danger")

    # widgets
    w = [
        col_button,
        ttk.Spinbox(table, textvariable=v['intensity'], from_=1, to=255, width=3, bootstyle=intensity_color),
        on_label, 
        off_label,
        ttk.Scale(table, variable=v['on_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=on_update, bootstyle="secondary"),
        ttk.Scale(table, variable=v['off_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=off_update, bootstyle=off_time_color),
        del_button
    ]

    on_update(v['on_time'].get()); off_update(v['off_time'].get())

    for col, widget in enumerate(w):
        widget.grid(row=i+1, column=col, padx=5, pady=5, sticky="nsew")
        table.grid_columnconfigure(col, weight=1)

    rows.append({'widgets': w, 
                 'vars': v})
    params.append([v['color'].get(), 
                   int(v['intensity'].get()), 
                   int(v['on_time'].get()), 
                   int(v['off_time'].get())])

    # variable traces
    for name in v:
        v[name].trace_add("write", lambda *_,idx=i, n=name: update_params(idx, n))

    v['color'].trace_add("write", lambda *_: update_row_style(i))
    update_row_style(i)
    print(f"{info_prefix}added row {i}, current number of rows: {len(rows)}")

"""Callback for the delete button on each row"""
def delete_row(i):
    if i >= len(rows): return
    for w in rows[i]['widgets']:
        w.destroy()
    del rows[i], params[i]
    # re-grid rows below
    for idx in range(i, len(rows)):
        for col, widget in enumerate(rows[idx]['widgets']):
            widget.grid(row=idx+1, column=col)
    print(f"{info_prefix}deleted row {i}, current number of rows: {len(rows)}")

"""Callback for the send to ESP32 button"""
def send_action():
    if len(rows) < 1:
        messagebox.showerror("Error", f"Cannot send with less than 1 row!")
        return
    payload = build_payload()
    pkt     = build_packet(payload)
    print(f"{info_prefix}PC payload: {payload}")
    print(f"{info_prefix}PC packet : {bar_hex(pkt)}")   # ← uses grouped view
    
    if mode_var.get() == 0:  # USB mode
        send_usb(pkt)
    else:  # Bluetooth mode
        send_bluetooth(pkt)

"""Callback for the send test packet button"""
def send_test_packet():
    demo = "R,255,1,1,C,3"
    pkt  = build_packet(demo)
    print(f"{info_prefix}PC TEST packet : {bar_hex(pkt)}")  # ← grouped view

    if mode_var.get() == 0:  # USB mode
        send_usb(pkt)
    else:  # Bluetooth mode
        send_bluetooth(pkt)

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

# ──────────────── GUI layout ────────────────────────────────────────
main   = ttk.Frame(root); 
main.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
table  = ttk.Frame(main)
footer = ttk.Frame(main, relief='ridge')
status_frame = ttk.Frame(footer)
status_frame.grid(row=0, column=5, padx=(30, 5), pady=5)

# table header
for col, h in enumerate(headers):
    ttk.Label(table, text=h).grid(row=0, column=col, padx=5, pady=5, sticky="nsew")
    table.grid_columnconfigure(col, weight=1)
add_new_row()  # first empty row

# footer buttons
ttk.Button(footer, text="Add Row", width=15, bootstyle="danger", command=add_new_row).grid(row=0, column=0, padx=5, pady=5)
ttk.Button(footer, text="Send to ESP32", width=15, bootstyle="success", command=send_action).grid(row=0, column=1, padx=5, pady=5)
#ttk.Button(footer, text="Send TEST pkt", width=15, bootstyle="warning", command=send_test_packet).grid(row=0, column=2, padx=5, pady=5)

ttk.Label(footer, text="Cycles").grid(row=0, column=2, padx=(20, 5), pady=5)
ttk.Spinbox(footer, from_=1, to=100, textvariable=cycles, width=5).grid(row=0, column=3, padx=5, pady=5)
ttk.Button(footer, text="Configure Connection", width=25, bootstyle="warning", command=config_window).grid(row=0, column=4, padx=5, pady=5)

# Connection type and port status
mode_indicator = ttk.Label(status_frame, text="Unknown", bootstyle="danger")
mode_indicator.pack(side="left", padx=(0, 10))
port_indicator = ttk.Label(status_frame, text="Unknown")
port_indicator.pack(side="left")
update_status()

# ──────────────── GUI window ────────────────────────────────────────
table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
footer.pack(side=tk.BOTTOM, pady=(10,0), fill=tk.X)
root.after(50, config_window)
root.mainloop()