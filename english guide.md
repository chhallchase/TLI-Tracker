# FurTorch English Version - Installation Guide

This is the English version of the FurTorch Torchlight Infinite income statistics tool.

## Installation

1. Ensure you have Python installed (version 3.6 or higher)
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the English version of the application:
   ```
   python indexh.py
   ```

## Building Executable

To create a standalone executable:
1. Install py2exe:
   ```
   pip install py2exe
   ```
2. Run the setup script:
   ```
   python setup_english.py py2exe
   ```
3. The executable will be created in the `dist` folder

## Usage Instructions

1. Before starting the application, make sure to enable logging in Torchlight Infinite:
   - Open the game
   - Go to Settings -> Other Settings
   - Enable logging option

2. Start the application (either run the Python script or the executable)

3. The application will automatically track:
   - Time spent in maps
   - Items dropped
   - Income per minute
   - Total earnings

4. Use the "Drops" button to view detailed drop information
   - Filter by item type using the buttons on the left
   - Toggle between current map drops and all-time drops

5. Use the "Settings" button to:
   - Set the cost per map (will be deducted from profits)
   - Adjust the window opacity
   - Set tax calculation preference

## Notes

- The application reads the Torchlight Infinite game log in real-time
- Item prices are updated automatically from the server
- All drop information is also saved to `drop.txt` in the same folder

## Troubleshooting

If the application doesn't work:
- Ensure logging is enabled in the game
- Check that the game path is correctly detected
- The game log format may have changed in a game update; check for newer versions of FurTorch

For questions or issues, please submit them on GitHub or contact the developer.
