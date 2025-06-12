"""
IC-Project : Mini-Flasher GUI - build 0610
────────────────────────────────────────────────────────────────────────
Adds to the previous diagnostic build
    • automatic COM-port detection
    • combobox to pick / refresh the port
    • robust error handling (no more Tkinter crashes)
    • unchanged packet generator and GUI workflow
-----------------------------------------------------------------------
Tested with Python 3.11, ttkbootstrap 1.10, pyserial 3.5
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import serial, serial.tools.list_ports

# ──────────────── global configuration ───────────────────────────────
BAUDRATE        = 115_200
HEADER1, HEADER2 = 0x5A, 0xA5
DEBUG_LOOPBACK  = False   # True  = TX and RX pins shorted → expect echo
READ_TIMEOUT    = 0.3     # seconds for optional loop-back read

intensity_color = 'dark'
off_time_color  = 'secondary'
select_text     = "Please Select"
default_cycles  = 5
max_on_off_time = 100
max_row         = 250     # max table rows

headers = ['Colors','Intensity (0-255)','On_Time (100 ms)',
           'Off_Time (100 ms)', 'MMI On','MMI Off']
colors  = ["Red","Green","Blue","Infrared"]
colors_mapper = {"Red":"danger","Green":"success","Blue":"primary",
                 "Infrared":"warning", select_text:"secondary"}

# ──────────────── Tk root window ─────────────────────────────────────
root = tk.Tk()
root.title("IC-Project  ·  Mini-Flasher GUI")

# ──────────────── Serial-port utilities ─────────────────────────────
port_var = tk.StringVar(value="")        # currently selected port

def available_ports():
    """Return list of (device, description) tuples."""
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]

def auto_select_port():
    """Pick first USB-UART-looking port (CH340 / CP210 / FTDI / USB)."""
    for dev, desc in available_ports():
        if any(tag in desc for tag in ("CH340", "CP210", "FTDI", "USB")):
            return dev
    return ""

def refresh_port_list():
    """Re-scan system ports and repopulate combobox."""
    ports = available_ports()
    combo["values"] = [f"{d}  –  {s}" for d, s in ports]
    # keep old selection if still present, else auto-pick first
    current = port_var.get()
    if current and any(current == d for d, _ in ports):
        pass
    elif ports:
        port_var.set(ports[0][0])
    else:
        port_var.set("")

def send_usb(packet: bytes, expect_echo: int = 0) -> bytes:
    """Open selected COM port, transmit packet, optionally read echo."""
    port = port_var.get()
    if " " in port:                 # ← NEW: take only first token
        port = port.split()[0]      #     ► "COM4"
    if not port:
        print("ERROR  No serial port selected.")
        return b""
    try:
        with serial.Serial(port, BAUDRATE, timeout=READ_TIMEOUT) as ser:
            n = ser.write(packet)
            print(f"PC  wrote {n}/{len(packet)} bytes to {port}")
            if expect_echo:
                echo = ser.read(expect_echo)
                print(f"PC  echo  {bar_hex(echo)}")
                return echo
    except serial.SerialException as e:
        print(f"ERROR opening {port}: {e}")
    return b""

# ──────────────── Packet helpers ────────────────────────────────────
def color_enum(c):
    return {'Red':'R','Green':'G','Blue':'B','Infrared':'I'}.get(c,'N')

def build_payload() -> str:
    pieces=[]
    for row in params:
        pieces.extend(map(str,row))
    pieces.extend(["C", str(cycles.get())])
    return ",".join(pieces)

def build_packet(payload: str) -> bytes:
    sync   = bytes([HEADER1, HEADER2])
    data   = payload.encode('ascii')
    length = len(data).to_bytes(2, 'little')
    chk    = (sum(sync + length + data) & 0xFFFF).to_bytes(2, 'little')
    return sync + length + data + chk

# ──────────────── NEW: prettier hex printer ──────────────────────────
def bar_hex(pkt: bytes, chunk: int = 5) -> str:
    """
    Convert bytes to grouped hex string, e.g.
    b'\x5a\xA5…' ⇒ '5a a5 19 00 50 | 6c 65 61 73 65 | …'
    """
    hexbytes = pkt.hex(' ').split()                    # ['5a', 'a5', ...]
    groups   = [' '.join(hexbytes[i:i+chunk])          # 5-byte slices
                for i in range(0, len(hexbytes), chunk)]
    return ' | '.join(groups)

# ──────────────── GUI data structures ───────────────────────────────
rows, params = [], []
cycles = tk.IntVar(value=default_cycles)

# ──────────────── GUI callbacks ─────────────────────────────────────
def update_params(i, _=None):
    """Synchronise params list when a widget variable changes."""
    if i >= len(params): return
    rv = rows[i]['vars']
    params[i] = [color_enum(rv['color'].get()),
                 int(rv['intensity'].get()),
                 int(rv['on_time'].get()),
                 int(rv['off_time'].get())]

def update_row_style(i):
    if i >= len(rows): return
    style = colors_mapper.get(rows[i]['vars']['color'].get(), "secondary")
    rows[i]['widgets'][0].configure(bootstyle=style)
    rows[i]['widgets'][4].configure(bootstyle=style)

def add_new_row():
    if len(rows) >= max_row:
        print("INFO  maximum rows reached")
        return
    i = len(rows)
    v = {'color':     ttk.StringVar(value=select_text),
         'intensity': ttk.IntVar(value=255),
         'on_time':   ttk.IntVar(value=1),
         'off_time':  ttk.IntVar(value=1)}
    on_lbl, off_lbl = ttk.Label(table), ttk.Label(table)

    on_upd  = lambda val: on_lbl.config(text=str(int(float(val))))
    off_upd = lambda val: off_lbl.config(text=str(int(float(val))))

    col_btn = ttk.Menubutton(table, text=v['color'].get(), width=10,
                             bootstyle="secondary")
    menu = tk.Menu(col_btn); col_btn['menu'] = menu
    def choose(c):
        v['color'].set(c); col_btn.config(text=c); update_row_style(i)
    for c in colors:
        menu.add_command(label=c, command=lambda c=c: choose(c))

    del_btn = ttk.Button(table, text="DELETE", width=2,
                         command=lambda idx=i: delete_row(idx),
                         bootstyle="danger")

    w = [
        col_btn,
        ttk.Spinbox(table, textvariable=v['intensity'], from_=1, to=255,
                    width=3, bootstyle=intensity_color),
        on_lbl, off_lbl,
        ttk.Scale(table, variable=v['on_time'], from_=1, to=max_on_off_time,
                  orient=HORIZONTAL, command=on_upd, bootstyle="secondary"),
        ttk.Scale(table, variable=v['off_time'], from_=1, to=max_on_off_time,
                  orient=HORIZONTAL, command=off_upd, bootstyle=off_time_color),
        del_btn
    ]

    on_upd(v['on_time'].get()); off_upd(v['off_time'].get())
    for col, widget in enumerate(w):
        widget.grid(row=i+1, column=col, padx=5, pady=5, sticky="nsew")
        table.grid_columnconfigure(col, weight=1)

    rows.append({'widgets': w, 'vars': v})
    params.append([v['color'].get(), int(v['intensity'].get()),
                   int(v['on_time'].get()), int(v['off_time'].get())])

    # variable traces
    for name in v:
        v[name].trace_add("write", lambda *_,
                          idx=i, n=name: update_params(idx, n))
    v['color'].trace_add("write", lambda *_: update_row_style(i))
    update_row_style(i)

def delete_row(i):
    if i >= len(rows): return
    for w in rows[i]['widgets']:
        w.destroy()
    del rows[i], params[i]
    # re-grid rows below
    for idx in range(i, len(rows)):
        for col, widget in enumerate(rows[idx]['widgets']):
            widget.grid(row=idx+1, column=col)
    print(f"INFO  deleted row {i}")

def send_action():
    payload = build_payload()
    pkt     = build_packet(payload)
    print(f"PC  payload: {payload}")
    print(f"PC  packet : {bar_hex(pkt)}")   # ← uses grouped view
    send_usb(pkt, len(pkt) if DEBUG_LOOPBACK else 0)

def send_test_packet():
    demo = "R,255,1,1,C,3"
    pkt  = build_packet(demo)
    print(f"PC  TEST packet : {bar_hex(pkt)}")  # ← grouped view
    send_usb(pkt, len(pkt) if DEBUG_LOOPBACK else 0)

# ──────────────── GUI layout ────────────────────────────────────────
main   = ttk.Frame(root); main.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
table  = ttk.Frame(main)
footer = ttk.Frame(main)

# table header
for col, h in enumerate(headers):
    ttk.Label(table, text=h).grid(row=0, column=col, padx=5, pady=5, sticky="nsew")
    table.grid_columnconfigure(col, weight=1)

add_new_row()  # first empty row

# footer buttons
ttk.Button(footer, text="Add Row", width=15, bootstyle="danger",
           command=add_new_row).grid(row=0, column=0, padx=5, pady=5)

ttk.Button(footer, text="Send to ESP32", width=15, bootstyle="success",
           command=send_action).grid(row=0, column=1, padx=5, pady=5)

ttk.Button(footer, text="Send TEST pkt", width=15, bootstyle="warning",
           command=send_test_packet).grid(row=0, column=2, padx=5, pady=5)

ttk.Label(footer, text="Cycles").grid(row=0, column=3, padx=(20, 5), pady=5)
ttk.Spinbox(footer, from_=1, to=100, textvariable=cycles,
            width=5).grid(row=0, column=4, padx=5, pady=5)

# serial port selector
port_frame = ttk.Frame(footer)
ttk.Label(port_frame, text="Serial port").pack(side="left", padx=(0, 5))

combo = ttk.Combobox(port_frame, textvariable=port_var,
                     state="readonly", width=28)
combo.pack(side="left")

ttk.Button(port_frame, text="↻", width=3, bootstyle="secondary-outline",
           command=refresh_port_list).pack(side="left", padx=(3, 0))

port_frame.grid(row=0, column=5, padx=(30, 5), pady=5)

table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
footer.pack(side=tk.BOTTOM, fill=tk.X)

# populate port list at start-up
port_var.set(auto_select_port())
refresh_port_list()

root.mainloop()