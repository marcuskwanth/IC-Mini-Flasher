Version 250716.1
- Added two-button logic (Power button + Multi-function button)
- Added a tiny flash to the ESP32 indicator light whenever receiving a packet, including USB polling
- Fixed ESP32 freezes when receiving packet whilst in Bluetooth (pairing) mode
- The mini-flasher will stop when ESP32 switched into Bluetooth pairing mode
- FIxed mini-flasher will not turn off when clicking the MFB right after receiving type 0 packet
- Updated ESP32 LCD Display status
- Added a 2 second delay for powering on the ESP32 from deep sleep (off)

Version 250715.1
- Updated the intensity values in the program to invert them to fit into the new color LEDs

Version 250713.2
- Updated ESP32 firmware that the LEDs will flash immediately after receiving type 0 packet

Version 250713.1
- Integrated complete ESP32 program (Button + Bluetooth + LED Packeting + Sleep)

Version 250712.3
- Temporary fix for macOS can't read / write files when it is executed in app

Version 250712.2
- Added pyInstaller to build exe / app

Version 250712.1
- Bug fix: Not stating poll fail if ESP32 device disconnects
- Added newest code for ESP32 packet receiving 
- Removed unneeded code

Version 250630.3
- Update the polling time interval.

Version 250630.2
- Fixed USB COM not continuously polling after matched saved COM port
- Fixed configuration window poping up even after correctly polled a USB COM port
- Added a dedicate button for polling USB COM ports
- Updated window's geometry to be resizable (still not adjustable automatically)

Version 250630.1
- Added USB COM port polling functionality, with COM port retrying and write timeout ability
(In order for the polling to work, please flash the sketch .ino file to the ESP32 from the repo)
- Fixed configuration window not poping up when using standard (non-COM polling) mode

Version 250629.4
- Minor update on the Save Settings and Load Settings positions

Version 250629.3
- Implemented a new layout (buttons are now on the left side), the old layout can still be used by changing a parameter (NEW_LAYOUT)
- Updated the rows table so that it is now scrollable if its number grows
- Updated the position on the MMI_OnTime column
- Updated the delete button to the left side instead of the right side
- Added a confirmation box on Send Data, Request Data, Save Settings, and Load Settings buttons
- Updated the logic on deleting a row

Version 250629.2
- Added a try-catch when parasing hex data

Version 250629.1
- Updated the packet reading function when requesting data

Version 250627.1
- Added proper data request function (to be tested with real hardware)
- Added a variable (INIT_SCAN) to switch between COM polling and standard refreshing mode
- Added threading during send / request data

Version 250625.3
- Added USB COM port polling logic
- Updated the refreshing button of USB to polling instead of scanning

Version 250625.2
- Removed mode saving so that everytime it defaults to USB mode
- Updated the config text file structure

Version 250625.1
- Added total time count display, with its limit changable in the configuration window

Version 250624.2
- Minor code edit

Version 250624.1
- Added request data button (functionality to be added later)

Version 250623.4
- Fixed quotation mark issue in line 408
- Added 1-second buffer after closing the sockets

Version 250623.3
- Minor code edit

Version 250623.2
- Updated all info message boxes into status bar text

Version 250623.1
- Added status bar text
- Added colour sequence counting display

Version 250620.1
- Added colour sequence setting saving and loading functions inside a settings text file
- Added input validations to the input boxes
- Fixed delete row bug (tracing issue)
- Updated the GUI layout

Version 250618.1
- Fixed macOS Bluetooth connection
- Added help dialogue in connection setting window

Version 250613.1
- Updated the code structure

Version 250612.2:
- Ability to save connection settings inside a config text file
- Added Bluetooth implementation

Version 250612.1:
- Ability to send packet data to ESP32

Version 250609.3:
- Code simplification

Version 250609.2:
- Minor improvement on the packet structure

Version 250609.1:
- Added changable cycle count
- Added delete row button
- Added basic packet building functionality

Version 250607.2:
- Minor bug fixes.

Version 250607.1:
- First commit.