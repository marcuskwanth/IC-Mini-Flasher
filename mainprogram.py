import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

master = tk.Tk()
master.title("Mini Flasher")

# Programmable variables
intensity_color = 'dark'
off_time_color = 'secondary'
select_text = "Not Selected!"
add_row_button_text = "Add New Color"
max_on_off_time = 100

# Window Parameters
master.geometry("1000x600")
mainFrame = tk.Frame(master)
topFrame = tk.Frame(mainFrame)
bottomFrame = tk.Frame(mainFrame)

# Dropdown options and lists
headers = ['Colors', 'Intensity (0-255)', 'On_Time (100ms)', 'Off_Time (100ms)', 'MMI for On_Time', 'MMI for Off_Time']
colors = ["Red", "Green", "Blue", "Infrared"]
colors_mapper = {
    "Red": "danger",
    "Green": "success",
    "Blue": "primary",
    "Infrared": "warning",
    select_text: "secondary"
}
rows = []
params = [] # Stores parameter values

# -==FUNCTIONS==-
# Update the menubutton and on_time scale color based on selected color
def update_row_style(row_index):
    if row_index < len(rows):
        color = rows[row_index]['vars']['color'].get()
        style = colors_mapper.get(color, "secondary")
        
        # Update Menubutton style
        color_btn = rows[row_index]['widgets'][0]
        color_btn.configure(bootstyle=style)
        
        # Update Scale style
        on_time_scale = rows[row_index]['widgets'][4]
        on_time_scale.configure(bootstyle=style)

# A function for a button to add a row
def add_new_row():
    row_index = len(rows)
    row_vars = {
        'color': ttk.StringVar(value=select_text),
        'intensity': ttk.IntVar(value=255),
        'on_time': ttk.IntVar(value=1),
        'off_time': ttk.IntVar(value=1)
    }
    
    # Create labels with integer display and update them when its value changes
    on_time_label = ttk.Label(topFrame)
    def update_on_time(val):
        on_time_label.config(text=str(int(float(val))))

    off_time_label = ttk.Label(topFrame)
    def update_off_time(val):
        off_time_label.config(text=str(int(float(val))))
    
    # Create Menubutton for color selection and auto update its color upon selection
    color_btn = ttk.Menubutton(topFrame, text=row_vars['color'].get(), width=10, bootstyle="secondary")
    color_menu = tk.Menu(color_btn)
    color_btn['menu'] = color_menu
    for color in colors:
        color_menu.add_command(label=color, command=lambda c=color: set_color(row_index, c))
    def set_color(row_index, selected_color):
        row_vars['color'].set(selected_color)
        color_btn.config(text=selected_color)
        update_row_style(row_index)
    
    # Create widgets
    row_widgets = [
        color_btn,
        ttk.Spinbox(topFrame, textvariable=row_vars['intensity'], from_=1, to=255, width=3, bootstyle=intensity_color),
        on_time_label,
        off_time_label,
        ttk.Scale(topFrame, variable=row_vars['on_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=update_on_time, bootstyle="secondary"),
        ttk.Scale(topFrame, variable=row_vars['off_time'], from_=1, to=max_on_off_time, orient=HORIZONTAL, command=update_off_time, bootstyle=off_time_color)
    ]
    
    update_on_time(row_vars['on_time'].get())
    update_off_time(row_vars['off_time'].get())

    for col, widget in enumerate(row_widgets):
        widget.grid(row=row_index+1, column=col, padx=5, pady=5, sticky="nsew")
        topFrame.grid_columnconfigure(col, weight=1)  # Make columns expandable

    # Initialize structures and values for the added row
    rows.append({'widgets': row_widgets, 'vars': row_vars, 'labels': {
        'on_time': on_time_label,
        'off_time': off_time_label
    }})
    params.append([
        row_vars['color'].get(),
        int(row_vars['intensity'].get()),
        int(row_vars['on_time'].get()),
        int(row_vars['off_time'].get())
    ])
    
    # Implement an Auto-Update logic to the params in that row
    def make_tracer(idx, name):
        return lambda *_: update_params(idx, name)
    for name in row_vars:
        row_vars[name].trace_add("write", make_tracer(row_index, name))

    # Add trace specifically for color changes to update style
    def update_color_style(*_):
        update_row_style(row_index)
    row_vars['color'].trace_add("write", update_color_style) 
    update_row_style(row_index)

    print("INFO: Added new row successfully")

# Update params when values change
def update_params(row_index, var_name):
    try:
        if row_index < len(params):
            row_vars = rows[row_index]['vars']
            params[row_index] = [
                row_vars['color'].get(),
                int(row_vars['intensity'].get()),
                int(row_vars['on_time'].get()),
                int(row_vars['off_time'].get())
            ]
        print("INFO: Current params:", params)
    except:
        print("WARNING: Invalid text field detected!")

# -==PROGRAM MAIN LOGIC==-
for i, header in enumerate(headers):
    label = ttk.Label(topFrame, text=header)
    label.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")
    topFrame.grid_columnconfigure(i, weight=1)  # Make headers expandable

add_new_row()
ttk.Button(bottomFrame, text=add_row_button_text, command=add_new_row, width=15).pack(pady=10)

# Layout config
mainFrame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
topFrame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
bottomFrame.pack(side=tk.BOTTOM, fill=tk.X)
master.grid_rowconfigure(0, weight=1)
master.grid_columnconfigure(0, weight=1)

master.mainloop()