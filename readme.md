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