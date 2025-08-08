Version 2500808.1
- ESP32 INO
    - Reverted the logic of the color LEDs

Version 250722.1
- ESP32 INO
    - Modified the TTL output to be set to HIGH if any LED is on, not 200ms pulse

Version 250721.2
- ESP32 INO
    - Removed mini flashing indication (Green LED)
    - Re-enabled blinking LED (Red LED, 100ms) after valid key presses

Version 250721.1
- GUI App
    - Updated the USB COM polling toggle: Now requires manual repolling, and auto-disabled in Bluetooth mode
    - Watchdog now stops upon switching to Bluetooth mode, and restarts after switching to USB mode
    - Added requesting data functionality for Bluetooth mode
    - Bluetooth now connects upon saving config instead of after clicking the Send button
- ESP32 INO
    - Updated the data request function to support both USB and Bluetooth mode
    - Fixed variable (mode) inconsistency between GUI App and ESP32 INO

Version 250718.3
- GUI App
    - Updated the COM opening error message
- ESP32 INO
    - Fixed LED ON_TIME inconsistency
    - Fixed Bluetooth / Low battery flashing interval to be 1 second

Version 250718.2
- GUI App
    - Added a USB COM polling toggle
    - Removed INIT_SCAN function entirely (combined polling + USB scanning)
- ESP32 INO
    - Amended the low battery ADC pin to 26
    - Changed the button input logic to be internal PULL UP

Version 250717.2
- GUI App
    - Fixed GUI USB polling issue related to watchdog
    - Fixed polling becoming fail to a correct port if the app sends large packet to ESP32
    - Added a menu bar to store non-essential operations (e.g. save/load setting, configuration)
    - Updated the font size for some texts
    - Removed the parameter to use old style layout

Version 250717.1
- ESP32 INO
    - Renamed some symbols in ESP32 .ino file

Version 250716.2
- ESP32 INO
    - Removed USB Mode light indication, and blinking on quick press
    - Added mini-flasher ON/OFF status light indication (GREEN)

Version 250716.1
- ESP32 INO
    - Added two-button logic (Power button + Multi-function button)
    - Added a tiny flash to the ESP32 indicator light whenever receiving a packet, including USB polling
    - Fixed ESP32 freezes when receiving packet whilst in Bluetooth (pairing) mode
    - The mini-flasher will stop when ESP32 switched into Bluetooth pairing mode
    - FIxed mini-flasher will not turn off when clicking the MFB right after receiving type 0 packet
    - Updated ESP32 LCD Display status
    - Added a 2 second delay for powering on the ESP32 from deep sleep (off)

Version 250715.1
- ESP32 INO
    - Updated the intensity values in the program to invert them to fit into the new color LEDs

Version 250713.2
- ESP32 INO
    - Updated ESP32 firmware that the LEDs will flash immediately after receiving type 0 packet

Version 250713.1
- ESP32 INO
    - Integrated complete ESP32 program (Button + Bluetooth + LED Packeting + Sleep)

Version 250712.3
- GUI App
    - Temporary fix for macOS can't read / write files when it is executed in app

Version 250712.2
- GUI App
    - Added pyInstaller to build exe / app

Version 250712.1
- GUI App
    - Bug fix: Not stating poll fail if ESP32 device disconnects
- ESP32 INO
    - Added newest code for ESP32 packet receiving 
- Other
    - Removed unneeded code

Version 250630.3
- GUI App
    - Update the polling time interval.

Version 250630.2
- GUI App
    - Fixed USB COM not continuously polling after matched saved COM port
    - Fixed configuration window poping up even after correctly polled a USB COM port
    - Added a dedicate button for polling USB COM ports
    - Updated window's geometry to be resizable (still not adjustable automatically)

Version 250630.1
- GUI App
    - Added USB COM port polling functionality, with COM port retrying and write timeout ability
    - Fixed configuration window not poping up when using standard (non-COM polling) mode
- ESP32 INO
    - In order for the polling to work, please flash the sketch .ino file to the ESP32 from the repo

Version 250629.4
- GUI App
    - Minor update on the Save Settings and Load Settings positions

Version 250629.3
- GUI App
    - Implemented a new layout (buttons are now on the left side), the old layout can still be used by changing a parameter (NEW_LAYOUT)
    - Updated the rows table so that it is now scrollable if its number grows
    - Updated the position on the MMI_OnTime column
    - Updated the delete button to the left side instead of the right side
    - Added a confirmation box on Send Data, Request Data, Save Settings, and Load Settings buttons
    - Updated the logic on deleting a row

Version 250629.2
- GUI App
    - Added a try-catch when parasing hex data

Version 250629.1
- GUI App
    - Updated the packet reading function when requesting data

Version 250627.1
- GUI App
    - Added proper data request function (to be tested with real hardware)
    - Added a variable (INIT_SCAN) to switch between COM polling and standard refreshing mode
    - Added threading during send / request data

Version 250625.3
- GUI App
    - Added USB COM port polling logic
    - Updated the refreshing button of USB to polling instead of scanning

Version 250625.2
- GUI App
    - Removed mode saving so that everytime it defaults to USB mode
    - Updated the config text file structure

Version 250625.1
- GUI App
    - Added total time count display, with its limit changable in the configuration window

Version 250624.2
- GUI App
    - Minor code edit

Version 250624.1
- GUI App
    - Added request data button (functionality to be added later)

Version 250623.4
- GUI App
    - Fixed quotation mark issue in line 408
    - Added 1-second buffer after closing the sockets

Version 250623.3
- GUI App
    - Minor code edit

Version 250623.2
- GUI App
    - Updated all info message boxes into status bar text

Version 250623.1
- GUI App
    - Added status bar text
    - Added colour sequence counting display

Version 250620.1
- GUI App
    - Added colour sequence setting saving and loading functions inside a settings text file
    - Added input validations to the input boxes
    - Fixed delete row bug (tracing issue)
    - Updated the GUI layout

Version 250618.1
- GUI App
    - Fixed macOS Bluetooth connection
    - Added help dialogue in connection setting window

Version 250613.1
- GUI App
    - Updated the code structure

Version 250612.2:
- GUI App
    - Ability to save connection settings inside a config text file
    - Added Bluetooth implementation

Version 250612.1:
- GUI App
    - Ability to send packet data to ESP32

Version 250609.3:
- GUI App
    - Code simplification

Version 250609.2:
- GUI App
    - Minor improvement on the packet structure

Version 250609.1:
- GUI App
    - Added changable cycle count
    - Added delete row button
    - Added basic packet building functionality

Version 250607.2:
- GUI App
    - Minor bug fixes.

Version 250607.1:
- GUI App
    - First commit.