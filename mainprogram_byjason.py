"""
IC-Project : Mini-Flasher GUI - build 250629.3
────────────────────────────────────────────────────────────────────────
Tested with Python 3.11, ttkbootstrap 1.10, pyserial 3.5

To-do:
*1. Poll the correct USB COM ports one-by-one when the program starts
2. Check the language for Chinese-languaged Windows PC

*Partly done here, next need to test with real hardware
"""

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import serial, serial.tools.list_ports, json, subprocess, os, time
import traceback 

import bluetooth, glob, platform, threading
"""
Package "pybluez", please follow this github comment for proper installation, make sure to 'pip install backports.tarfile' first. 
https://github.com/pybluez/pybluez/issues/431#issuecomment-2191842543
For Windows user, pls make sure Microsoft Visual C++ 14.0 is installed 
For macOS user, pls make sure to 'pip install python-lightblue', and 'brew install blueutil'
"""

# ──────────────── Tk root window ─────────────────────────────────────
root = tk.Tk()
root.title("IC-Project  ·  Mini-Flasher GUI")
cfg_wintitle = "IC-Project  ·  Configurations"

# ──────────────── Global configuration ───────────────────────────────
INIT_SCAN           = 1                 # 0 = disable USB COM polling functionality, 1 = enable
NEW_LAYOUT          = 1                 # 0 = with original layout, 1 = new layout with the buttons on LHS
CONFIG_FILE         = "config.txt"
SETTING_FILE        = "settings.txt"
POLLING_PKT         = ""                # Any payload for USB COM polling?
REQUEST_PKT         = ""                # Any payload for requesting data?
POLLING_ECHO_PKT    = ""                # These 2 not sure if needed, just put them here just in case!
REQUEST_ECHO_PKT    = ""
TARGET_PORT         = 1                 # 1 For BT-SPP!
BAUDRATE            = 115_200
READ_TIMEOUT_USB    = 1                 # USB: seconds for optional loop-back read
READ_TIMEOUT_BT     = 1               # BLUETOOTH: seconds for optional loop-back read
COOLDOWN            = 10                # Send button cooldown in seconds

# ──────────────── Packet Header configuration ────────────────────────
HEADER1, HEADER2    = 0x5A, 0xA5
LED_SETTING         = 0x00              # Type 0: Be used when clicking "Send Data"
POLL_LINK           = 0x01              # Type 1: Be used when polling the correct USB COM ports one-by-one once the program starts
READ_SETTING        = 0x02              # Type 2: Be used when clicking "Request Data"

# ──────────────── Poll-watchdog configuration ──────────────────────

POLL_INTERVAL_MS     = 1000          # watchdog tick   (1 s)
POLL_FAIL_TIMEOUT    = 30            # open config dlg after 30 s consecutive failure

_poll_lock           = threading.Lock()
_poll_sending        = threading.Event()   # raised while a user-Tx is active
_poll_fail_since     = None                # time.time() when failure streak started
_lock_acquired_at    = 0                  # for stale-lock detection
_watchdog_id         = None               # after() handle so we can stop / restart

# ──────────────── GUI/Console Elements configuration ─────────────────
device_name         = "ESP32"
buttons_width       = 15
box_mmi_width       = 15
scale_thres         = 70
row_num_text        = "Sequences: "
select_text         = "<Please Select>"
delete_text         = "X"
refresh_text        = "↻"
add_row_text        = "Add Sequence"
send_text           = "Send Data"
request_text        = "Request Data"
cfg_text            = "Configuration"
info_prefix         = "*INFO: "         # Shown in console
error_prefix        = "*ERROR: "        # Shown in console
attention_prefix    = "ATTENTION: "     # info_prefix but shown in GUI status bar instead of console

# ──────────────── GUI var configuration ──────────────────────────────
default_cycles      = 5
default_time_allow  = 10                # in minutes
max_intensity       = 255
max_on_off_time     = 100
max_row             = 250               # max no. of colour sequences

last_send_time      = 0                 # Track when last send occurred (during cooldown)

# ──────────────── GUI data structures ───────────────────────────────
# Changable by user
time_allow = tk.IntVar(value=default_time_allow)
cycles = tk.IntVar(value=default_cycles)
cycles.trace_add("write", lambda *_: update_total_time())

# Fixed by the program
bt_socket = None
usb_socket = None
rows, params = [], []                                                   # rows = structure + values shown in the boxes, params = values stored in the program
row_count_var = tk.StringVar(value=f"{row_num_text}?")
total_time = tk.DoubleVar(value=0.00)                                   # Stored in the program
total_time_var = tk.StringVar(value=f"Total Time: {total_time} min")    # Displayed in the GUI

headers = ['Remove', 'Colour', f'Intensity (0-{max_intensity})','On_Time (100 ms)', 'MMI On_Time', 'Off_Time (100 ms)', 'MMI Off_Time']
colors  = ["Red","Green","Blue","Infrared"]
colors_mapper = {
    "Red":"danger",
    "Green":"success",
    "Blue":"primary",
    "Infrared":"warning", 
    select_text:"secondary"
}
def color_enum(c): # Long-form to short-form
    return {'Red':'R','Green':'G','Blue':'B','Infrared':'I'}.get(c,'N')
def enum_color(c): # Short-form to long-form
    return {'R':'Red','G':'Green','B':'Blue','I':'Infrared'}.get(c,select_text)

# ──────────────── Bluetooth SPP utilities ────────────────────────────
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
                timeout=READ_TIMEOUT_BT,
                write_timeout= 5,
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
        bt_socket.settimeout(READ_TIMEOUT_BT)
        bt_connected = True
        print(f"{info_prefix}Bluetooth connected to {bt_addr}")
        return True
    except Exception as e:
        print(f"{error_prefix}Connection failed: {e}")
        messagebox.showerror("Error", f"Bluetooth connection failed: {e}") 
        bt_connected = False
        return False

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
        device_list = [f"{name} ({addr})" for addr, name in devices]
        root.after(0, lambda: update_bt_list(combo, device_list))
    except Exception as e:
        print(f"{error_prefix}Bluetooth scanning failed: {e}")
        messagebox.showerror("Error", f"Bluetooth scanning failed: {e}") 
        root.after(0, lambda: combo.set("Scan failed, try again"))

"""Update Bluetooth combo box with scan results"""
def update_bt_list(combo, device_list):
    if not device_list:
        combo.set("No devices found")
        combo["values"] = []
        bt_mac.set("")
        return
    combo["values"] = device_list
    combo.set(device_list[0])

"""Disconnect from Bluetooth device"""
def disconnect_bluetooth():
    global bt_socket, bt_connected
    if bt_socket:
        try:
            bt_socket.close()
            time.sleep(1)   # A buffer for connection closing
            print(f"{info_prefix}Bluetooth connection closed")
        except Exception as e:
            print(f"{error_prefix}Error closing Bluetooth: {e}")
        finally:
            bt_socket = None
            bt_connected = False

"""Send data over Bluetooth connection"""
def send_bluetooth(packet: bytes, expect_echo: int = 0) -> bytes:
    global bt_connected, _poll_sending 
    _poll_sending.set()
    if usb_socket:
        disconnect_usb()
    if not bt_connected:
        if not connect_bluetooth():
            _poll_sending.clear()
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
        # Below echo part is just for contingency in case it needs to echo something back!
        if expect_echo:
            echo = bt_socket.recv(expect_echo)
            print(f"{info_prefix}Received echo: {bar_hex(echo)}")
        print(f"{info_prefix}Sent {len(packet)} bytes via Bluetooth SPP: {bt_mac.get()}")
        info_status(msg=f"Message sent to {device_name} successfully via Bluetooth!", fg='green')
        return echo
    except Exception as e:
        print(f"{error_prefix}Communication error: {e}")
        messagebox.showerror("Error", f"Bluetooth failed: {e}") 
        bt_connected = False
        return b""
    finally:
        _poll_sending.clear()

# ──────────────── USB Serial utilities ──────────────────────────────
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

"""Automatically detect the correct USB port by sending polling packets"""
def usb_polling():
    """
    Scan all available serial ports with a 7-byte poll packet.
    The port that echoes the packet is accepted as the Mini-Flasher.
    """
    if mode_var.get() != 0:            # skip if GUI is in Bluetooth mode
        return

    info_status("Detecting device on USB ports...", fg='grey')
    root.update()

    ports = available_ports()
    if not ports:
        info_status("No USB ports available", fg='red')
        set_poll_led(False)
        return False                 

    pkt      = build_packet(POLL_LINK, POLLING_PKT)   # 0×01, len == 0 → 7 bytes
    exp_echo = len(pkt)                               # expect exactly 7 bytes
    print(f"{info_prefix}Polling packet: {bar_hex(pkt)}")

    # first try the port remembered in config, then the remaining ones
    saved = port_var.get().split(' ')[0] if port_var.get() else ""
    order = ([saved] if saved else []) + [p[0] for p in ports if p[0] != saved]

    for dev in order:
        info_status(f"Trying {dev}...", fg='grey')
        root.update()
        try:
            echo = usb_polling_send(dev, pkt, expect_echo=exp_echo)
        except serial.SerialException as e:
            print(f"{error_prefix}opening {dev}: {e}")

            # ---- saved port vanished → forget it immediately ----------
            if dev == saved:
                print(f"{info_prefix}{dev} disappeared – clearing saved COM port")
                port_var.set("")
                save_config(mode_var.get(), "", bt_mac.get(), time_allow.get())
            return True

        ok = (echo == pkt)
        set_poll_led(ok)


        if echo == pkt:
            # --- SUCCESS -----------------------------------------------------
            desc = dict(ports).get(dev, "")
            port_var.set(f"{dev}  --  {desc}")
            info_status(f"Device found on {dev}", fg='green')
            update_status()
            info_status("USB link OK", fg='green')
            save_config(mode_var.get(), port_var.get(), bt_mac.get(),
                        time_allow.get())
            return

    info_status("Mini-Flasher not detected on USB ports.", fg='red')
    set_poll_led(False)

"""Parent function that tries to send a packet to a specific port and return echo if received"""
# ──────────────── USB helper that *propagates* errors ───────────────
def usb_polling_send(port_device: str,
                     packet: bytes,
                     expect_echo: int = 0) -> bytes:
    """
    Open one port, write the poll packet, optionally read the echo.
    Any SerialException is allowed to propagate to the caller.
    """
    usb_socket = serial.Serial(port_device, BAUDRATE, timeout=READ_TIMEOUT_USB, write_timeout=5)
    with usb_socket as ser:
        n = ser.write(packet)
        print(f"{info_prefix}PC wrote {n}/{len(packet)} bytes to {port_device}")
        if expect_echo:
            echo = ser.read(expect_echo)
            print(f"PC  echo:  {bar_hex(echo)}")
            return echo
    return b""          # (no echo requested)

"""Disconnect from USB Port"""
def disconnect_usb():
    global usb_socket
    if usb_socket:
        try:
            usb_socket.close()
            time.sleep(1)   # A buffer for connection closing
            print(f"{info_prefix}USB connection closed")
        except Exception as e:
            print(f"{error_prefix}Error closing USB Port: {e}")
        finally:
            usb_socket = None

"""Open selected COM port, transmit packet, optionally read echo."""
def send_usb(packet: bytes,
             expect_echo: int = 0,
             read_response: bool = False) -> bytes:
    global usb_socket
    _poll_sending.set()              # ← mark that we’re in a send operation

    try:
        # If we’re currently connected over BLE, disconnect first
        if bt_socket:
            disconnect_bluetooth()

        port = port_var.get()
        if " " in port:             # ← NEW: take only first token ► "COM4"
            port = port.split()[0]
        if not port:
            print(f"{error_prefix}No serial port selected.")
            messagebox.showerror("Error", "No USB serial port selected!")
            return b""

        try:
            usb_socket = serial.Serial(port, BAUDRATE, timeout=READ_TIMEOUT_USB,write_timeout=5)
            with usb_socket as ser:
                n = ser.write(packet)
                print(f"{info_prefix}PC wrote {n}/{len(packet)} bytes to {port}")

                if read_response:
                    response = read_one_packet(ser)
                    print(f"{info_prefix}Reading response: {bar_hex(response)}")
                    return response

                if expect_echo:
                    echo = ser.read(expect_echo)
                    print(f"PC  echo  {bar_hex(echo)}")
                    return echo

                info_status(
                    msg=f"Message sent to {device_name} successfully via USB serial {port}!",
                    fg="green"
                )
                print(f"{info_prefix}Sent {len(packet)} bytes via USB Serial {port}")
                return b""

        except serial.SerialException as e:
            print(f"{error_prefix}opening {port}: {e}")
            messagebox.showerror("Error", f"Error whilst opening port {port}!")
            return b""

    finally:
        _poll_sending.clear()        # ← always clear the flag on exit

"""Sequence for requesting configuration data from ESP32 device"""
def request_data_prerequisite():
    if mode_var.get() != 0:
        info_status(msg=f"{attention_prefix}Please select a USB serial connection first.", fg='red')
        return
    info_status(msg=f"Requesting settings from {device_name}...", fg='grey')
    result = messagebox.askyesno(request_text, "This action will override the current colour sequeence settings, are you sure you want to proceed?")
    if result:
        request_data() # Removed threading to improve performance
def request_data():
    pkt = build_packet(READ_SETTING, REQUEST_PKT) # Type 2
    print(f"{info_prefix}Requesting data with packet: {bar_hex(pkt)}")
    disconnect_bluetooth()

    response = send_usb(pkt, read_response=True)
    if not response:
        info_status(msg="No response received from device.", fg='red')
        return
    decoded = decode_packet(response)
    if not decoded:
        info_status(msg="Invalid response format.", fg='red')
        return
    sequences, cycles_val = parse_payload(decoded['payload'])
    if sequences is None:
        info_status(msg="Could not parse device settings.", fg='red')
        return

    set_data(sequences, cycles_val)
    info_status(msg=f"Settings pulled from {device_name} successfully!", fg='blue')
    print(f"{info_prefix}Loaded settings from device: {sequences} cycles={cycles_val}")

# ──────────────── Packet helpers ────────────────────────────────────
"""Build the payload data"""
def build_payload() -> str:
    pieces=[]
    for i in range(len(params)):
        if params[i][0] == 'N': # if there exists a sequence with no colour selected
            return False
        pieces.extend(map(str,params[i]))
    pieces.extend(["C", str(cycles.get())])
    return ",".join(pieces)

"""Build the packet data with the header and payload data"""
def build_packet(type, payload: str) -> bytes:
    sync   = bytes([HEADER1, HEADER2])
    datatype = bytes([type])
    data   = payload.encode('ascii')
    length = len(data).to_bytes(2, 'little')
    chk    = (sum(sync + length + datatype + data) & 0xFFFF).to_bytes(2, 'little')

    print(f"{info_prefix}Header: {sync}, dataType: {datatype}")
    return sync + length + datatype + data + chk

"""Convert bytes to grouped hex string, e.g. b'\x5a\xA5…' ⇒ '5a a5 19 00 50 | 6c 65 61 73 65 | …'"""
def bar_hex(pkt: bytes, chunk: int = 5) -> str:
    try:
        hexbytes = pkt.hex(' ').split()                    # ['5a', 'a5', ...]
        groups   = [' '.join(hexbytes[i:i+chunk])          # 5-byte slices
                    for i in range(0, len(hexbytes), chunk)]
        return ' | '.join(groups)
    except Exception as e:
        print(f"{error_prefix}Error whilst parasing hex data: {e}")

"""Read one packet at a time"""
def read_one_packet(ser, timeout=1.0) -> bytes:
    start     = time.time()
    state     = 0          # 0 = want 0x5A, 1 = want 0xA5, 2 = have hdr
    hdr       = bytearray()
    length    = 0
    payload   = bytearray()

    while time.time() - start < timeout:
        if not ser.in_waiting:
            time.sleep(0.001)
            continue
        b = ser.read(1)[0]

        # --- sync --------------------------------------------------
        if state == 0:                # waiting for 0x5A
            if b == 0x5A:
                hdr.append(b); state = 1
            continue
        if state == 1:                # waiting for 0xA5
            if b == 0xA5:
                hdr.append(b); state = 2
            else:
                hdr.clear(); state = 0
            continue

        # --- we already have 0x5A 0xA5 -----------------------------
        hdr.append(b)
        if len(hdr) == 4:             # LEN1 LEN2 just arrived
            length = int.from_bytes(hdr[2:4], 'little')

        if len(hdr) == 5 + length + 2:  # 5=hdr+type, +payload, +csum16
            return bytes(hdr)          # done

    return b''                         # timeout

"""Decode the received packet in requesting data (Type 2)"""
def decode_packet(packet: bytes) -> dict:
    try:
        if len(packet) < 7 or packet[0] != HEADER1 or packet[1] != HEADER2:
            print(f"{error_prefix}Invalid packet header")
            return None
        # Extract components
        length = int.from_bytes(packet[2:4], 'little')
        data_type = packet[4]
        payload = packet[5:5+length].decode('ascii')
        checksum = int.from_bytes(packet[-2:], 'little')

        calculated_csum = sum(packet[:-2]) & 0xFFFF
        if checksum != calculated_csum:
            print(f"{error_prefix}Checksum mismatch: {checksum} vs {calculated_csum}")
            return None 
        
        print(f"{info_prefix}Received valid packet: type={data_type}, payload={payload}")
        return {'type': data_type, 'payload': payload}
    except Exception as e:
        messagebox.showerror("Error", f"Payload decoding failed: {e}")
        print(f"{error_prefix}Decoding failed: {e}")
        return None

"""Parse the payload data from the decoded payload above"""
def parse_payload(payload: str) -> tuple:
    try:
        # Split payload into components
        parts = payload.split(',')
        if len(parts) < 4 or (len(parts) - 2) % 4 != 0:  # Account for cycles marker
            print(f"{error_prefix}Invalid payload structure")
            return None, None
        sequences = []
        cycles_val = default_cycles
        i = 0

        while i < len(parts):
            if parts[i] == 'C':  # Cycle marker
                cycles_val = int(parts[i+1])
                break
            color_char = parts[i]
            intensity = int(parts[i+1])
            on_time = int(parts[i+2])
            off_time = int(parts[i+3])
            sequences.append({
                'color': color_char,
                'intensity': intensity,
                'on_time': on_time,
                'off_time': off_time
            })
            i += 4
        return sequences, cycles_val
    except Exception as e:
        messagebox.showerror("Error", f"Payload parsing failed: {e}")
        print(f"{error_prefix}Payload parsing failed: {e}")
        return None, None
    
def start_watchdog():
    """arm the watchdog exactly once"""
    global _watchdog_id
    if _watchdog_id is None:
        _watchdog_id = root.after(50, polling_watchdog)

def stop_watchdog():
    """cancel the periodic after() if it is running"""
    global _watchdog_id
    if _watchdog_id is not None:
        root.after_cancel(_watchdog_id)
        _watchdog_id = None

def polling_watchdog():
    print("*DEBUG* mode =", mode_var.get(),
      "sending =", _poll_sending.is_set(),
      "lock =", _poll_lock.locked())
    """
    Periodically tries usb_polling().  Extra features:
      • releases stale locks
      • keeps track of continuous failures and re-opens the config window
        after POLL_FAIL_TIMEOUT seconds
    """
    global _lock_acquired_at, _poll_fail_since, _watchdog_id

    # ---------- salvage a stuck lock (e.g. PySerial hangs) --------------
    if _poll_lock.locked() and time.time() - _lock_acquired_at > 5:
        try:
            _poll_lock.release()
            print("*WARN* watchdog lock was stale – force-released")
        except RuntimeError:
            pass

    # ---------- worker that does the actual polling ---------------------
    def _worker():
        global _poll_fail_since
        ok = False
        try:
            ok = usb_polling()          # True  ==> device found
        finally:
            _poll_lock.release()

        if ok:
            _poll_fail_since = None
        else:

            if _poll_fail_since is None:
                _poll_fail_since = time.time()
            elif time.time() - _poll_fail_since >= POLL_FAIL_TIMEOUT:
                _poll_fail_since = None          # pop dlg only once
                root.after(0, config_window)

    # ---------- schedule worker if allowed ------------------------------
    if mode_var.get() == 0 and not _poll_sending.is_set():
        if _poll_lock.acquire(blocking=False):
            _lock_acquired_at = time.time()
            threading.Thread(target=_worker, daemon=True).start()

    _watchdog_id = root.after(POLL_INTERVAL_MS, polling_watchdog)


# ──────────────── GUI File I/O ──────────────────────────────────────
"""Save current settings to file"""
def save_settings():
    result = messagebox.askyesno("Save Settings", "This action will override the settings file, are you sure you want to proceed?")
    if not result:
        return
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
        info_status(msg=f"Settings saved to {SETTING_FILE} successfully!", fg='blue')
    except Exception as e:
        print(f"{error_prefix}Saving settings: {e}")
        messagebox.showerror("Error", f"Failed to save to {SETTING_FILE}: {e}")

"""Load settings from file"""
def load_settings():
    result = messagebox.askyesno("Load Settings", "This action will override the current colour sequeence settings, are you sure you want to proceed?")
    if not result:
        return
    if not os.path.exists(SETTING_FILE): 
        info_status(msg=f"{attention_prefix}{SETTING_FILE} not found. Save settings first to create such file!", fg='red')
        return False
    # File I/O
    try:
        with open(SETTING_FILE, 'r') as f:
            settings = json.load(f)
        # Clear existing rows then load new rows
        set_data(settings.get("rows", []), settings.get("cycles", default_cycles))
        debug_print_value()
        return True
    except Exception as e:
        print(f"{error_prefix}Loading settings: {e}")
        messagebox.showerror("Error", f"Failed to load from {SETTING_FILE}: {e}")
        return False

"""Parent function to load new settings into the program and replaces the old one"""
def set_data(new_settings, new_cycles):
    try:
        while len(rows) > 0:
            delete_row(0)   
        for row in new_settings:
            add_new_row()
            i = len(rows) - 1
            '''
            color_name = row.get("color", select_text)
            rows[i]['vars']['color'].set(color_name)
            rows[i]['widgets'][0].config(text=color_name)
            '''
            rows[i]['vars']['color'].set(enum_color(row.get("color")))         # Update color button's color
            rows[i]['widgets'][1].config(text=enum_color(row.get("color")))    # Update color button's text
            rows[i]['vars']['intensity'].set(row.get("intensity", max_intensity))
            rows[i]['vars']['on_time'].set(row.get("on_time", 1))
            rows[i]['vars']['off_time'].set(row.get("off_time", 1))
            update_params(i)
            update_row_style(i)
        cycles.set(new_cycles)
        info_status(msg=f"Settings loaded successfully from {SETTING_FILE}!", fg='blue')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load from {SETTING_FILE}: {e}")

"""Save connection configuration to file"""
def save_config(mode, com_port, bt_mac, time):
    try:
        with open(CONFIG_FILE, 'w') as f:
            f.write(f"USB_COM={com_port}\n")
            f.write(f"BT_MAC={bt_mac}\n")
            f.write(f"MAX_LED_Time={time}\n")
        info_status(msg=f"Configurations saved, now using {'USB' if mode == 0 else 'Bluetooth'}. Total time allowed set to {time_allow.get()} minute(s).", fg='grey')
    except Exception as e:
        print(f"{error_prefix}Saving config: {e}")
        messagebox.showerror("Error", f"Error whilst saving {CONFIG_FILE}: {e}!") 

"""Load connection configuration from file or return defaults"""
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"USB_COM": "", "BT_MAC": "", "MAX_LED_Time": default_time_allow}
    config = {"USB_COM": "", "BT_MAC": "", "MAX_LED_Time": default_time_allow}
    try:
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                if key == "USB_COM":
                    config["USB_COM"] = value
                elif key == "BT_MAC":
                    config["BT_MAC"] = value
                elif key == "MAX_LED_Time":
                    config["MAX_LED_Time"] = value
                # Sequence for setting the config values into the variables
                port_var.set(config["USB_COM"])
                bt_mac.set(config["BT_MAC"])
                time_allow.set(config["MAX_LED_Time"])
    except Exception as e:
        print(f"{error_prefix}Loading config: {e}")
        messagebox.showerror("Error", f"Error whilst loading {CONFIG_FILE}, now falling back to default config: {e}!") 
        save_config(0, "", "", default_time_allow) # Reset config file if it went wrong.
    return config

# ──────────────── GUI connection cfg ──────────────────────────────
"""The code for the connection setting window"""
def config_window():
    config_win = tk.Toplevel(root)
    config_win.title(cfg_wintitle)
    config_win.resizable(False, False)
    config_win.grab_set()
    load_config()

    def on_usb_refresh():
        if INIT_SCAN == 1:
            config_win.destroy()
            usb_polling()
        else: 
            refresh_port_list(port_combo)
        # start periodic polling from now on
        root.after(POLL_INTERVAL_MS, polling_watchdog)

    def on_cancel():
        config_win.destroy()

    def on_save():
        save_config(mode_var.get(), port_var.get(), bt_mac.get(), time_allow.get())
        update_status()
        start_watchdog()
        config_win.destroy()

    # HELP FUNCTION: Shows instructions for finding ports/devices
    def show_help():
        help_text = f"""
        Help: How to find USB Serial Port / Bluetooth Host?
        
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
        4. If device doesn't appear / cannot connect:
           - Ensure it's not connected to another PC
           - Unpair and pair the {device_name} again
        """
        messagebox.showinfo("Connection Help", help_text)
    
    # Mode selection
    mode_frame = ttk.Frame(config_win)
    mode_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(mode_frame, text="Connection Mode:").grid(row=0, column=0, sticky='w', padx=(0,10))
    ttk.Radiobutton(mode_frame, text="USB Serial", variable=mode_var, value=0).grid(row=0, column=1, sticky='w', padx=5)
    ttk.Radiobutton(mode_frame, text="Bluetooth SPP", variable=mode_var, value=1).grid(row=0, column=2, sticky='w', padx=5)
    
    # Port selection
    val_frame = ttk.Frame(config_win)
    val_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(val_frame, text="USB COM Port:").grid(row=0, column=0, sticky='w', padx=(0,10))
    port_combo = ttk.Combobox(val_frame, textvariable=port_var, width=20)
    port_combo.grid(row=0, column=1, sticky='ew', padx=5)
    refresh_port_btn = ttk.Button(val_frame, text=refresh_text, width=3, command=on_usb_refresh, bootstyle="secondary-outline") # before: command=lambda: refresh_port_list(port_combo)
    refresh_port_btn.grid(row=0, column=2, padx=(5, 0))

    ttk.Label(val_frame, text="Bluetooth Host:").grid(row=1, column=0, sticky='w', padx=(0,10))
    btmac_combo = ttk.Combobox(val_frame, textvariable=bt_mac, width=20)
    btmac_combo.grid(row=1, column=1, sticky='ew', padx=5)
    refresh_bt_btn = ttk.Button(val_frame, text=refresh_text, width=3, command=lambda: refresh_bt_list(btmac_combo), bootstyle="secondary-outline")
    refresh_bt_btn.grid(row=1, column=2, padx=(5, 0))

    # Other selection
    other_frame = ttk.Frame(config_win)
    other_frame.pack(fill='x', padx=20, pady=10)

    ttk.Label(other_frame, text="Total Time Allowed:").grid(row=2, column=0, sticky='w', padx=(0,10))
    ttk.Spinbox(other_frame, textvariable=time_allow, from_=1, to=100, width=5).grid(row=2, column=1, sticky='ew', padx=5)
    ttk.Label(other_frame, text="minute(s)").grid(row=2, column=2, sticky='w', padx=(0,10))

    # Buttons
    btn_frame = ttk.Frame(config_win)
    btn_frame.pack(fill='x', pady=20)

    ttk.Button(btn_frame, text="Help", command=show_help, bootstyle="info-outline", width=5).pack(side='left', padx=20)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel, bootstyle="secondary-outline", width=8).pack(side='right', padx=20)
    ttk.Button(btn_frame, text="Save", command=on_save, bootstyle="success-outline", width=8).pack(side='right')

    config_win.wait_window(config_win)
    
# ──────────────── GUI callbacks ─────────────────────────────────────
"""Debugging: Printing out the values of rows and params"""
def debug_print_value():
    print(f"====================")
    for i in range(len(rows)):
        print(f"{rows[i]['vars']['color'].get()}, {rows[i]['vars']['intensity'].get()}, {rows[i]['vars']['on_time'].get()}, {rows[i]['vars']['off_time'].get()}; ", end="")
    print(f"\ntotal_time: {total_time.get()}")
    print(f"\n{params} \n====================\n")
    
"""Validate spinbox input and clamp to min/max values"""
def validate_spinbox(var, min_val, max_val):
    current = var.get()
    if current < min_val:
        info_status(msg=f"{attention_prefix}Minimum value reached! ({min_val})", fg='red')
        var.set(min_val)
    elif current > max_val:
        info_status(msg=f"{attention_prefix}Maximum value reached! ({max_val})", fg='red')
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
    
    update_total_time()
    debug_print_value()

"""Update the color of the sliders when the color selection changes"""
def update_row_style(i):
    if i >= len(rows): return
    style = colors_mapper.get(rows[i]['vars']['color'].get(), "secondary")
    rows[i]['widgets'][1].configure(bootstyle=style)  # Colour button
    rows[i]['widgets'][3].configure(bootstyle=style)  # On spinbox
    rows[i]['widgets'][4].configure(bootstyle=style)  # On scale

"""Callback for the add row button"""
def add_new_row():
    if len(rows) >= max_row:
        print(f"{info_prefix}maximum rows reached")
        info_status(msg=f"{attention_prefix}Maximum row reached! ({max_row})", fg='red')
        return
    i = len(rows)
    v = {'color':     ttk.StringVar(value=select_text),     # v = row's values in this function!
         'intensity': ttk.IntVar(value=max_intensity),
         'on_time':   ttk.IntVar(value=1),
         'off_time':  ttk.IntVar(value=1)}
    
    row_ref = {'id': i}  # Create a unique reference for this row

    del_button = ttk.Button(table, text=delete_text, width=2, command=lambda idx=i: delete_row(idx), bootstyle="danger")
    col_button = ttk.Menubutton(table, text=v['color'].get(), width=buttons_width, bootstyle="secondary")
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
        width=box_mmi_width, bootstyle='dark', command=lambda: validate_spinbox(v['intensity'], 1, max_intensity)
    )
    on_spin = ttk.Spinbox(
        table, textvariable=v['on_time'], from_=1, to=max_on_off_time, 
        width=box_mmi_width, bootstyle='secondary', command=lambda: validate_spinbox(v['on_time'], 1, max_on_off_time)
    )
    off_spin = ttk.Spinbox(
        table, textvariable=v['off_time'], from_=1, to=max_on_off_time, 
        width=box_mmi_width, bootstyle='secondary', command=lambda: validate_spinbox(v['off_time'], 1, max_on_off_time)
    )
    on_update  = lambda val: v['on_time'].set(int(float(val)))
    off_update = lambda val: v['off_time'].set(int(float(val)))

    # widgets
    w = [
        del_button,
        col_button,
        intensity_spin,
        on_spin,
        ttk.Scale(table, variable=v['on_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, length=max_on_off_time+scale_thres, command=on_update, bootstyle='secondary'),
        off_spin,
        ttk.Scale(table, variable=v['off_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, length=max_on_off_time+scale_thres, command=off_update, bootstyle='secondary'),
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
        'color_trace': color_trace,
        'ref': row_ref
    })
    params.append([color_enum(v['color'].get()), 
                   int(v['intensity'].get()), 
                   int(v['on_time'].get()), 
                   int(v['off_time'].get())])
    update_row_style(i)

    row_count_var.set(f"{row_num_text}{len(rows)}")
    update_total_time()

    info_status(msg=f"Added colour row {i+1} successfully!", fg='grey')
    print(f"{info_prefix}added row {i+1}, current number of rows: {len(rows)}")
    debug_print_value()

"""Callback for the delete button on each row"""
def delete_row_by_ref(row_ref):
    # Find the row index by reference
    for i, row in enumerate(rows):
        if row['ref'] == row_ref:
            delete_row(i)
            break
def delete_row(i):
    if i >= len(rows): return
    
    for name in rows[i]['traces']:
        rows[i]['vars'][name].trace_remove("write", rows[i]['traces'][name])
    rows[i]['vars']['color'].trace_remove("write", rows[i]['color_trace'])
    
    for w in rows[i]['widgets']:
        w.destroy()
    del rows[i]
    del params[i]
    
    # Re-grid all remaining rows to ensure proper indexing
    for idx, row in enumerate(rows):
        for col, widget in enumerate(row['widgets']):
            widget.grid(row=idx+1, column=col)
        
        row['widgets'][0].config(command=lambda r=row['ref']: delete_row_by_ref(r))
        
        for name in row['traces']:
            row['vars'][name].trace_remove("write", row['traces'][name])
        row['traces'] = {}
        for name in row['vars']:
            row['traces'][name] = row['vars'][name].trace_add(
                "write", lambda *_, idx=idx, n=name: update_params(idx, n))
        
        row['vars']['color'].trace_remove("write", row['color_trace'])
        row['color_trace'] = row['vars']['color'].trace_add(
            "write", lambda *_, idx=idx: update_row_style(idx))

    row_count_var.set(f"{row_num_text}{len(rows)}")
    update_total_time()

    info_status(msg=f"Deleted colour row {i+1} successfully!", fg='grey')
    print(f"{info_prefix}deleted row {i+1}, current number of rows: {len(rows)}")
    debug_print_value()

"""Callback for the send to ESP32 button"""
def send_action():
    # First, check cooldown
    global last_send_time
    current_time = time.time()
    if current_time - last_send_time < COOLDOWN:
        remaining = int(COOLDOWN - (current_time - last_send_time))
        info_status(msg=f"{attention_prefix}Please wait for {remaining} seconds before sending again.", fg='red')
        return
    # Second, check number of rows
    if len(rows) < 1:
        info_status(msg=f"{attention_prefix}Please add at least 1 colour sequence!", fg='red')
        return
    # Third, check if the payload is valid (e.g. no invalid colour)
    payload = build_payload()
    if not payload:
        info_status(msg=f"{attention_prefix}Please select a colour on 1 or more colour sequence(s)!", fg='red')
        return
    # Forth, check if the total time exceed the time allowed set
    if (total_time.get() > time_allow.get()):
        info_status(msg=f"{attention_prefix}Total time exceeded the time allowed! ({time_allow.get()} minutes)", fg='red')
        return
    result = messagebox.askyesno(send_text, f"This action will override the {device_name}'s current setting in the flash memory, are you sure you want to proceed?")
    if not result:
        return
    pkt = build_packet(LED_SETTING, payload) # Type 0
    print(f"{info_prefix}PC payload: {payload}")
    print(f"{info_prefix}PC packet : {bar_hex(pkt)}")   # ← uses grouped view

    last_send_time = current_time
    send_btn.config(state="disabled")
    root.after(1000, update_send_button)
    
    if mode_var.get() == 0:  # USB mode
        info_status(msg=f"Attempting to send via USB serial.", fg='grey')
        threading.Thread(target=lambda: send_usb(pkt), daemon=True).start()
    else:  # Bluetooth mode
        info_status(msg=f"Attempting to send via Bluetooth.", fg='grey')
        threading.Thread(target=lambda: send_bluetooth(pkt), daemon=True).start()

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

"""Calculate the total time of all sequences"""
def update_total_time():
    global total_time
    total_ms = 0
    for row in params:
        cycle_ms = (row[2] + row[3]) * 100
        total_ms += cycle_ms * cycles.get()
    total_min = total_ms / (1000 * 60)  # Convert to minutes
    total_time.set(total_min)
    total_time_var.set(f"Total Time: {total_time.get():.2f} min")

"""Update connection status indicators"""
def update_status():
    mode_text = "USB" if mode_var.get() == 0 else "Bluetooth"
    mode_color = "info" if mode_var.get() == 0 else "primary"
    mode_indicator.config(text=mode_text, bootstyle=mode_color)

    port_indicator_text = "Port: " if mode_var.get() == 0 else "Host: "
    port = port_var.get()
    host = bt_mac.get()
    port_indicator.config(text=f"{port_indicator_text} {port if mode_var.get() == 0 else host}")
    if mode_var.get() == 1:
        set_poll_led(None)

"""Update the status indicator text"""
def info_status(msg="Unknown.", fg='grey'):
    status_indicator.config(text=msg, foreground=fg)

def set_poll_led(ok: bool | None):
    if ok is None:
        poll_indicator.config(text="POLL ?", bootstyle="secondary")
    elif ok:
        poll_indicator.config(text="POLL OK", bootstyle="success")
    else:
        poll_indicator.config(text="POLL FAIL", bootstyle="danger")

# ──────────────── GUI layout ────────────────────────────────────────

if NEW_LAYOUT == 1: # New layout
    root.geometry("1200x600")
    root.resizable(False, False)  # Allow vertical resizing

    main = ttk.Frame(root)
    main.pack(side="top", fill=tk.BOTH, expand=True, padx=10, pady=10)
    controls = ttk.Frame(main)
    controls.pack(side="left", fill=tk.Y, padx=(0, 10))
    table = ttk.Frame(main)
    table.pack(side="right", fill=tk.BOTH, expand=True, padx=(0, 3))

    footer = ttk.Frame(root)
    footer.pack(side="bottom", fill=tk.X, padx=10, pady=10)
    status_frame = ttk.Frame(footer, borderwidth=1)
    status_frame.pack(fill=tk.X, pady=(5, 0))

    # left-side buttons, labels, and spinbox
    ttk.Button(controls, text=add_row_text, width=buttons_width, bootstyle="danger-outline", command=add_new_row).pack(pady=5, anchor="w")
    send_btn = ttk.Button(controls, text=send_text, width=buttons_width, bootstyle="success-outline", command=send_action)
    send_btn.pack(pady=5, anchor="w")
    ttk.Button(controls, text=request_text, width=buttons_width, bootstyle="dark-outline", command=request_data_prerequisite).pack(pady=5, anchor="w")

    row_counter = ttk.Label(controls, textvariable=row_count_var)
    row_counter.pack(pady=5, anchor="w")

    total_time_label = ttk.Label(controls, textvariable=total_time_var)
    total_time_label.pack(pady=5, anchor="w")

    cycleframe = ttk.Frame(controls)
    cycleframe.pack(pady=5, anchor="w")
    ttk.Label(cycleframe, text="Cycles").pack(side="left")
    ttk.Spinbox(cycleframe, from_=1, to=100, textvariable=cycles, width=5).pack(side="left", padx=5)

    ttk.Button(controls, text=cfg_text, width=buttons_width, bootstyle="warning-outline", command=config_window).pack(pady=5, anchor="w")
    ttk.Button(controls, text="Load Settings", width=buttons_width, bootstyle="info-outline", command=load_settings).pack(pady=5, side="bottom", anchor="w")
    ttk.Button(controls, text="Save Settings", width=buttons_width, bootstyle="primary-outline", command=save_settings).pack(pady=5, side="bottom", anchor="w")

    # Create scrollable table in right panel
    canvas = tk.Canvas(table, borderwidth=0, highlightthickness=0)
    scrollbar = ttk.Scrollbar(table, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    # Configure canvas scrolling
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    
    # Function to update scroll region
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    scrollable_frame.bind("<Configure>", on_frame_configure)
    
    # Pack canvas and scrollbar
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Create table inside the scrollable frame
    table = ttk.Frame(scrollable_frame)
    table.pack(fill="both", expand=True, anchor="nw")  # Anchor to northwest
    
    # Bind mouse wheel for scrolling
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    canvas.bind_all("<MouseWheel>", on_mousewheel)
    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

else: # Old layout
    main = ttk.Frame(root); 
    main.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    table  = ttk.Frame(main)
    table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    status_frame = ttk.Frame(main)
    status_frame.pack(side=tk.BOTTOM, pady=(10,0), fill=tk.X)
    footer = ttk.Frame(main, relief='ridge')
    footer.pack(side=tk.BOTTOM, pady=(10,0), fill=tk.X)

    # footer buttons, labels, and spinbox
    ttk.Button(footer, text=add_row_text, width=buttons_width, bootstyle="danger-outline", command=add_new_row).grid(row=0, column=0, padx=5, pady=5)
    send_btn = ttk.Button(footer, text=send_text, width=buttons_width, bootstyle="success-outline", command=send_action)
    send_btn.grid(row=0, column=1, padx=5, pady=5)
    ttk.Button(footer, text=request_text, width=buttons_width, bootstyle="dark-outline", command=request_data_prerequisite).grid(row=0, column=2, padx=5, pady=5)

    row_counter = ttk.Label(footer, textvariable=row_count_var)
    row_counter.grid(row=0, column=3, padx=10, pady=5)
    total_time_label = ttk.Label(footer, textvariable=total_time_var)
    total_time_label.grid(row=0, column=4, padx=10, pady=5)

    ttk.Label(footer, text="Cycles").grid(row=0, column=5, padx=(20, 5), pady=5)
    ttk.Spinbox(footer, from_=1, to=100, textvariable=cycles, width=5).grid(row=0, column=6, padx=5, pady=5)

    ttk.Button(footer, text=cfg_text, width=buttons_width, bootstyle="warning-outline", command=config_window).grid(row=0, column=7, padx=5, pady=5)
    ttk.Button(footer, text="Save Settings", width=buttons_width, bootstyle="primary-outline", command=save_settings).grid(row=0, column=8, padx=5, pady=5)
    ttk.Button(footer, text="Load Settings", width=buttons_width, bootstyle="info-outline", command=load_settings).grid(row=0, column=9, padx=5, pady=5)

# Create table header
for col, h in enumerate(headers):
    width = 8 if col == 0 else None
    ttk.Label(table, text=h, width=width).grid(row=0, column=col, padx=5, pady=5, sticky="nsew")
    table.grid_columnconfigure(col, weight=1 if col > 0 else 0)  # Don't expand remove column

# Status at the bottom
port_indicator = ttk.Label(status_frame, text="Unknown")
port_indicator.pack(side="right")
mode_indicator = ttk.Label(status_frame, text="Unknown", bootstyle="danger")
mode_indicator.pack(side="right", padx=(20, 10))

# NEW badge showing poll result
poll_indicator = ttk.Label(status_frame, text="POLL ?", bootstyle="secondary")
poll_indicator.pack(side="right", padx=(10, 0))

status_indicator = ttk.Label(status_frame, text="Unknown", foreground='grey')
status_indicator.pack(side="left")

# initialise badge
set_poll_led(None)
# ──────────────── GUI window ────────────────────────────────────────
add_new_row()  # first empty row
update_total_time()
load_config()
update_status()


def on_closing():
    stop_watchdog()
    print(f"{info_prefix}Closing app")
    disconnect_bluetooth()
    disconnect_usb()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()