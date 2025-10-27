"""
Modified index.py with initialization button functionality for the Torchlight Infinite profit tracker.
This version adds a dedicated button that allows the user to initialize the item counts by 
scanning for a bag refresh (sort action) in the game logs, using BagMgr@:InitBagData entries.
"""

import time
from datetime import datetime
import psutil
import win32gui
import win32process
import win32api
import tkinter
from tkinter import messagebox, BitmapImage, Label, Button
import threading
import re
import json
from tkinter import *
from tkinter.ttk import *
from tkinter import ttk
import ctypes
import requests as rq
import os

server = "serverp.furtorch.heili.tech"

# Initialize configuration
if not os.path.exists("config.json"):
    with open("config.json", "w", encoding="utf-8") as f:
        config_data = {
            "opacity": 1.0,
            "tax": 0,
            "user": ""
        }
        json.dump(config_data, f, ensure_ascii=False, indent=4)

# Initialize translation mapping
if not os.path.exists("translation_mapping.json"):
    with open("translation_mapping.json", "w", encoding="utf-8") as f:
        # Create empty translation mapping
        translation_mapping = {}
        json.dump(translation_mapping, f, ensure_ascii=False, indent=4)

config_data = {}

# Track bag state and initialization status
bag_state = {}
bag_initialized = False
first_scan = True

# Initialize button state
awaiting_initialization = False
initialization_complete = False
initialization_in_progress = False

# Global flag to stop background threads
app_running = True

def load_translation_mapping():
    """Load or create translation mapping between Chinese and English item names"""
    try:
        with open("translation_mapping.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        # If the file doesn't exist, create an empty mapping
        return {}

def save_translation_mapping(mapping):
    """Save translation mapping to file"""
    with open("translation_mapping.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=4)

def get_price_info(text):
    try:
        pattern_id = r'XchgSearchPrice----SynId = (\d+).*?\+refer \[(\d+)\]'
        match = re.findall(pattern_id, text, re.DOTALL)
        result = list(match)
        for i, item in enumerate(result, 1):
            ids = item[1]
            synid = item[0]
            pattern = re.compile(
                rf'----Socket RecvMessage STT----XchgSearchPrice----SynId = {synid}\s+'  # Match target SynId
                r'\[.*?\]\s*GameLog: Display: \[Game\]\s+'  # Match time and fixed prefix
                r'(.*?)(?=----Socket RecvMessage STT----|$)',  # Match data block content (to the next data block or end)
                re.DOTALL  # Allow . to match newlines
            )

            # Find target data block
            match = pattern.search(text)
            if not match:
                print(f'Record found: ID:{item[1]}, Price:-1')
                continue
                
            data_block = match.group(1)
            if int(item[1]) == 100300:
                continue
                
            # Extract all +number [value] values (ignore currency)
            value_pattern = re.compile(r'\+\d+\s+\[([\d.]+)\]')  # Match +number [x.x] format
            values = value_pattern.findall(data_block)
            # Get the average of the first 30 values, or all if there are fewer than 30
            if len(values) == 0:
                average_value = -1
            else:
                num_values = min(len(values), 30)
                sum_values = sum(float(values[i]) for i in range(num_values))
                average_value = sum_values / num_values
                
            with open("full_table.json", 'r', encoding="utf-8") as f:
                full_table = json.load(f)
                try:
                    full_table[ids]['last_time'] = round(time.time())
                    full_table[ids]['from'] = "FurryHeiLi"
                    full_table[ids]['price'] = round(average_value, 4)
                except:
                    pass
            with open("full_table.json", 'w', encoding="utf-8") as f:
                json.dump(full_table, f, indent=4, ensure_ascii=False)
            print(f'Updating item value: ID:{ids}, Name:{full_table[ids]["name"]}, Price:{round(average_value, 4)}')
            price_submit(ids, round(average_value, 4), get_user())
    except Exception as e:
        print(e)

def initialize_bag_state(text):
    """Initialize the bag state by scanning all current items (legacy method)"""
    global bag_state, bag_initialized, first_scan
    
    if not first_scan:
        return False  # Only try to initialize on the first scan
    
    first_scan = False
    
    # Try to find initialization marker
    if "PlayerInitPkgMgr" in text or "Login2Client" in text:
        print("Detected player login or initialization - resetting bag state")
        bag_state.clear()
        return True
    
    # Pattern to match all bag items
    pattern = r'\[.*?\]\[.*?\]GameLog: Display: \[Game\] BagMgr@:Modfy BagItem PageId = (\d+) SlotId = (\d+) ConfigBaseId = (\d+) Num = (\d+)'
    matches = re.findall(pattern, text)
    
    if len(matches) > 10:  # Assume we found a big batch of items - good for initialization
        print(f"Found {len(matches)} bag items - initializing bag state")
        for match in matches:
            page_id, slot_id, config_base_id, num = match
            # Create a unique key for this item slot
            item_key = f"{page_id}:{slot_id}:{config_base_id}"
            num = int(num)
            # Update the bag state
            bag_state[item_key] = num
            
        bag_initialized = True
        return True
    
    return False

def start_initialization():
    """Start the initialization process by scanning for bag reset in the logs"""
    global awaiting_initialization, initialization_in_progress, root
    
    if initialization_in_progress:
        messagebox.showinfo("Initialization", "Initialization already in progress. Please wait.")
        return
    
    # Set the flag to await initialization
    awaiting_initialization = True
    initialization_in_progress = True
    
    # Update the UI to show we're waiting
    root.label_initialize_status.config(text="Waiting for bag update...",
                                       foreground="blue")
    root.button_initialize.config(state="disabled")
    
    # Inform the user what to do
    messagebox.showinfo("Initialization", 
                       "Click 'OK' and then sort your bag in-game by clicking the sort button.\n\n"
                       "This will refresh your inventory and allow the tracker to initialize with the correct item counts.")

def process_initialization(text):
    """Process the log text for initialization by scanning for BagMgr@:InitBagData entries"""
    global bag_state, bag_initialized, awaiting_initialization, initialization_complete, initialization_in_progress, root
    
    if not awaiting_initialization:
        return False
    
    # Pattern to match BagMgr@:InitBagData entries (complete inventory data)
    pattern = r'\[.*?\]GameLog: Display: \[Game\] BagMgr@:InitBagData PageId = (\d+) SlotId = (\d+) ConfigBaseId = (\d+) Num = (\d+)'
    matches = re.findall(pattern, text)
    
    # Only proceed if we found a significant number of entries
    if len(matches) < 20:
        return False
    
    print(f"Found {len(matches)} BagMgr@:InitBagData entries - initializing bag state")
    
    # Clear any existing bag state
    bag_state.clear()
    
    # Dictionary to track item totals (by ConfigBaseId)
    item_totals = {}
    
    # Process all matches to get the complete bag state
    for match in matches:
        page_id, slot_id, config_base_id, count = match
        count = int(count)
        
        # Store both the slot-based entry and update the total
        slot_key = f"{page_id}:{slot_id}:{config_base_id}"
        bag_state[slot_key] = count
        
        # Track totals by item ID
        if config_base_id not in item_totals:
            item_totals[config_base_id] = 0
        item_totals[config_base_id] += count
    
    # Store the totals in the bag state with a special prefix
    for item_id, total in item_totals.items():
        init_key = f"init:{item_id}"
        bag_state[init_key] = total
    
    # Only consider initialization successful if we found items
    if matches:
        print(f"Successfully initialized {len(item_totals)} unique item types across {len(matches)} inventory slots")
        bag_initialized = True
        initialization_complete = True
        awaiting_initialization = False
        initialization_in_progress = False
        
        # Update UI in the main thread
        root.after(0, lambda: root.label_initialize_status.config(
            text=f"Initialized {len(item_totals)} items",
            foreground="green"))
        root.after(0, lambda: root.button_initialize.config(state="normal"))
        
        return True
    
    return False

def detect_bag_changes(text):
    """Detect changes to the bag and calculate both gains and losses"""
    global bag_state, bag_initialized
    
    # If bag isn't initialized yet, we can't detect changes properly
    if not bag_initialized:
        return []
    
    # Pattern to match bag item modifications
    pattern = r'\[.*?\]GameLog: Display: \[Game\] BagMgr@:Modfy BagItem PageId = (\d+) SlotId = (\d+) ConfigBaseId = (\d+) Num = (\d+)'
    matches = re.findall(pattern, text)
    
    if not matches:
        return []
    
    changes = []
    slot_changes = {}
    
    # Process all matches to calculate item changes
    for match in matches:
        page_id, slot_id, config_base_id, count = match
        count = int(count)
        
        # Check previous value in this slot
        slot_key = f"{page_id}:{slot_id}:{config_base_id}"
        prev_count = bag_state.get(slot_key, 0)
        
        # Update the bag state
        bag_state[slot_key] = count
        
        # Track changes by item ID
        if config_base_id not in slot_changes:
            slot_changes[config_base_id] = 0
        
        # Track the change in this slot
        slot_changes[config_base_id] += (count - prev_count)
    
    # Now compare with initial values to see net changes
    for item_id, slot_change in slot_changes.items():
        if slot_change == 0:
            continue
            
        init_key = f"init:{item_id}"
        initial_total = bag_state.get(init_key, 0)
        
        # Calculate current total
        current_total = 0
        for key, value in bag_state.items():
            if key.startswith("init:"):
                continue
            parts = key.split(':')
            if len(parts) == 3 and parts[2] == item_id:
                current_total += value
        
        # Calculate net change from initial state
        net_change = current_total - initial_total
        
        if net_change != 0:
            changes.append((item_id, net_change))
            
            # Update the initial count
            bag_state[init_key] = current_total
    
    return changes

def scan_for_bag_changes(text):
    """Enhanced bag change scanner that handles initialization"""
    global bag_initialized, awaiting_initialization
    
    # Check if we're in initialization mode and process accordingly
    if awaiting_initialization:
        if process_initialization(text):
            return []  # Skip drop detection during initialization
    
    # If bag is properly initialized, use the new tracking method
    if bag_initialized and initialization_complete:
        return detect_bag_changes(text)
    
    # If bag isn't initialized yet, use the old method
    if not bag_initialized:
        # Use the original initialization method as fallback
        if initialize_bag_state(text):
            return []
        
    # Legacy method for tracking changes if not properly initialized
    pattern = r'\[.*?\]\[.*?\]GameLog: Display: \[Game\] BagMgr@:Modfy BagItem PageId = (\d+) SlotId = (\d+) ConfigBaseId = (\d+) Num = (\d+)'
    matches = re.findall(pattern, text)
    
    if not matches:
        return []
        
    drops = []
    
    # Track total counts of each item type before this update
    previous_totals = {}
    for item_key, qty in bag_state.items():
        if ":" not in item_key:
            continue
        parts = item_key.split(':')
        if len(parts) != 3:
            continue
        _, _, item_id = parts
        if item_id not in previous_totals:
            previous_totals[item_id] = 0
        previous_totals[item_id] += qty
    
    # Process all matches first to get the current state
    current_state = bag_state.copy()
    for match in matches:
        page_id, slot_id, config_base_id, num = match
        # Create a unique key for this item slot
        item_key = f"{page_id}:{slot_id}:{config_base_id}"
        num = int(num)
        
        # Update the current state
        current_state[item_key] = num
    
    # Now compute total counts after the update
    current_totals = {}
    for item_key, qty in current_state.items():
        if ":" not in item_key:
            continue
        parts = item_key.split(':')
        if len(parts) != 3:
            continue
        _, _, item_id = parts
        if item_id not in current_totals:
            current_totals[item_id] = 0
        current_totals[item_id] += qty
    
    # Compare total counts to detect drops, even across stacks
    for item_id, current_total in current_totals.items():
        previous_total = previous_totals.get(item_id, 0)
        if current_total > previous_total:
            # We got more of this item
            drops.append((item_id, current_total - previous_total))
    
    # Update the bag state
    bag_state.update(current_state)
    
    return drops

def detect_map_change(text):
    """Detect entering or leaving a map from the log text"""
    # Pattern to match entering a map from the refuge
    enter_pattern = r"PageApplyBase@ _UpdateGameEnd: LastSceneName = World'/Game/Art/Maps/01SD/XZ_YuJinZhiXiBiNanSuo200/XZ_YuJinZhiXiBiNanSuo200.XZ_YuJinZhiXiBiNanSuo200' NextSceneName = World'/Game/Art/Maps"
    
    # Pattern to match returning to the refuge
    exit_pattern = r"NextSceneName = World'/Game/Art/Maps/01SD/XZ_YuJinZhiXiBiNanSuo200/XZ_YuJinZhiXiBiNanSuo200.XZ_YuJinZhiXiBiNanSuo200'"
    
    entering_map = bool(re.search(enter_pattern, text))
    exiting_map = bool(re.search(exit_pattern, text))
    
    return entering_map, exiting_map

def get_user():
    """Get or register user ID"""
    with open("config.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)
    if not config_data.get("user", False):
        try:
            r = rq.get(f"http://{server}/reg", timeout=10).json()
            config_data["user"] = r["user_id"]
            user_id = r["user_id"]
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except:
            user_id = "3b95f1d6-5357-4efb-a96b-8cc3c76b3ee0"
    else:
        user_id = config_data["user"]
    return user_id

def price_submit(ids, price, user):
    try:
        r = rq.get(f"http://{server}/submit?user={user}&ids={ids}&new_price={price}", timeout=10).json()
        print(r)
        return r
    except Exception as e:
        print(e)

def initialize_data_files():
    """Initialize the English data files"""
    # Check if we need to create full_table.json from en_id_table.json
    if os.path.exists("en_id_table.json") and not os.path.exists("full_table.json"):
        try:
            # Load English ID table
            with open("en_id_table.json", 'r', encoding="utf-8") as f:
                english_items = json.load(f)
                
            # Create initial full_table.json with prices set to 0
            full_table = {}
            for item_id, item_data in english_items.items():
                full_table[item_id] = {
                    "name": item_data["name"],
                    "type": item_data["type"],
                    "price": 0
                }
                
            # Save the initial full_table.json
            with open("full_table.json", 'w', encoding="utf-8") as f:
                json.dump(full_table, f, indent=4, ensure_ascii=False)
                
            print("Created initial full_table.json from en_id_table.json")
        except Exception as e:
            print(f"Error initializing data files: {e}")

# Track bag state and initialization status
bag_state = {}
bag_initialized = False
first_scan = True

all_time_passed = 1

# Try to find the game and log file
game_found = False
try:
    hwnd = win32gui.FindWindow(None, "Torchlight: Infinite  ")
    if hwnd:
        tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        position_game = process.exe()
        position_log = position_game + "/../../../TorchLight/Saved/Logs/UE_game.log"
        position_log = position_log.replace("\\", "/")
        print(f"Log file location: {position_log}")
        with open(position_log, "r", encoding="utf-8") as f:
            print(f"Successfully opened log file, first 100 characters: {f.read(100)}")
            # Go to the end of the file
            f.seek(0, 2)
        game_found = True
except Exception as e:
    print(f"Error finding game: {e}")
    # Use a default log path as fallback
    position_log = "UE_game.log"
    
if not game_found:
    messagebox.showwarning("Game Not Found", 
                        "Could not find Torchlight: Infinite game process or log file. "\
                        "The tool will continue running but won't be able to track drops until the game is started.\n\n"\
                        "Please make sure the game is running with logging enabled, then restart this tool.")

exclude_list = []
pending_items = {}

def process_drops(drops, item_id_table, price_table):
    """Process detected drops and consumption, update statistics"""
    global income, income_all, drop_list, drop_list_all, config_data
    
    for change in drops:
        item_id, amount = change
        item_id = str(item_id)
        
        # Check if we have a name for this item
        if item_id in item_id_table:
            item_name = item_id_table[item_id]
        else:
            # No item name found, use ID as name and add to pending queue
            item_name = f"Unknown item (ID: {item_id})"
            if item_id not in pending_items:
                print(f"[NETWORK] ID {item_id} doesn't exist locally, fetching")
                pending_items[item_id] = amount
            else:
                pending_items[item_id] += amount
                print(f"[NETWORK] ID {item_id} already in queue, accumulated: {pending_items[item_id]}")
            continue
            
        # Check exclusion list
        if exclude_list and item_name in exclude_list:
            print(f"Excluded: {item_name} x{amount}")
            continue
            
        # Update counters (positive for gains, negative for consumption)
        if item_id not in drop_list:
            drop_list[item_id] = 0
        drop_list[item_id] += amount

        if item_id not in drop_list_all:
            drop_list_all[item_id] = 0
        drop_list_all[item_id] += amount
        
        # Calculate price impact
        price = 0.0
        if item_id in price_table:
            price = price_table[item_id]
            if config_data.get("tax", 0) == 1 and item_id != "100300":
                price = price * 0.875
            # Amount can be positive (gain) or negative (consumption)
            income += price * amount
            income_all += price * amount
            
        # Log to drop.txt
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if amount > 0:
            log_line = f"[{timestamp}] Drop: {item_name} x{amount} ({round(price, 3)}/each)\n"
        else:
            log_line = f"[{timestamp}] Consumed: {item_name} x{abs(amount)} ({round(price, 3)}/each)\n"
        with open("drop.txt", "a", encoding="utf-8") as f:
            f.write(log_line)
            
        if amount > 0:
            print(f"Processed drop: {item_name} x{amount} ({round(price, 3)}/each)")
        else:
            print(f"Processed consumption: {item_name} x{abs(amount)} ({round(price, 3)}/each)")

def deal_change(changed_text):
    global root
    global is_in_map, all_time_passed, drop_list, income, t, drop_list_all, income_all, total_time, map_count
    
    # Check if entering/leaving maps based on scene changes
    entering_map, exiting_map = detect_map_change(changed_text)
    
    if entering_map:
        is_in_map = True
        drop_list = {}
        income = 0  # Start fresh for this map, costs will be tracked automatically
        map_count += 1
        
    if exiting_map:
        is_in_map = False
        total_time += time.time() - t
    
    # Load item data and prices
    id_table = {}
    price_table = {}
    try:
        with open("full_table.json", 'r', encoding="utf-8") as f:
            f_data = json.load(f)
            for i in f_data.keys():
                id_table[str(i)] = f_data[i]["name"]
                price_table[str(i)] = f_data[i]["price"]
    except Exception as e:
        print(f"Error loading item data: {e}")
        return
    
    # Scan for bag changes (drops)
    drops = scan_for_bag_changes(changed_text)
    if drops:
        process_drops(drops, id_table, price_table)
        root.reshow()
        if not is_in_map:
            is_in_map = True

# Debug function to examine log format and bag state
def debug_log_format():
    """Print recent log entries and current bag state to help diagnose issues"""
    try:
        print("=== CURRENT BAG STATE ===")
        print(f"Initialized: {bag_initialized}")
        print(f"Initialization complete: {initialization_complete}")
        print(f"Total tracked slots: {len(bag_state)}")
        
        # Group by item ID for better display
        grouped = {}
        for key, amount in bag_state.items():
            if key.startswith("init:"):
                item_id = key.split(':')[1]
            elif ":" in key and len(key.split(':')) == 3:
                _, _, item_id = key.split(':')
            else:
                item_id = key
                
            if item_id not in grouped:
                grouped[item_id] = 0
            grouped[item_id] += amount
        
        # Load item names if available
        try:
            with open("full_table.json", 'r', encoding="utf-8") as f:
                item_data = json.load(f)
            
            print("Item totals:")
            for item_id, total in grouped.items():
                name = item_data.get(item_id, {}).get("name", f"Unknown (ID: {item_id})")
                print(f"  {name}: {total}")
        except:
            print("Item IDs and totals:")
            for item_id, total in grouped.items():
                print(f"  ID {item_id}: {total}")
                
        print("\n=== RECENT LOG ENTRIES ===")
        with open(position_log, "r", encoding="utf-8") as f:
            # Get the last 50 lines of the log
            lines = f.readlines()[-50:]
            for line in lines:
                # Only print lines related to bag changes or map changes
                if "BagMgr" in line or "PageApplyBase" in line or "ItemChange@" in line or "XZ_YuJinZhiXiBiNanSuo200" in line:
                    print(line.strip())
        print("=== END OF DEBUG INFO ===")
        
        # Show in a dialog
        messagebox.showinfo("Debug Information", 
                        f"Debug information has been printed to the console.\n\n"
                        f"Bag state initialized: {bag_initialized}\n"
                        f"Initialization complete: {initialization_complete}\n"
                        f"Total items tracked: {len(grouped)}\n"
                        f"Total inventory slots: {len(bag_state)}")
    except Exception as e:
        print(f"Error in debug function: {e}")
        import traceback
        traceback.print_exc()

is_in_map = False
drop_list = {}
drop_list_all = {}
income = 0
income_all = 0
t = time.time()
show_all = False
total_time = 0
map_count = 0

class App(Tk):
    show_type = ["Compass","Currency","Special Item","Memory Material","Equipment Material","Gameplay Ticket","Map Ticket","Cube Material","Corruption Material","Dream Material","Tower Material","BOSS Ticket","Memory Glow","Divine Emblem","Overlap Material","Hard Currency"]
    # Checkmark, Circle, X
    status = ["✔", "◯", "✘"]
    
    def __init__(self):
        super().__init__()
        self.title("FurTorch v0.0.2 - English")
        self.geometry()

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        # Call API to get current scaling factor
        ScaleFactor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
        # Set scaling factor
        self.tk.call('tk', 'scaling', ScaleFactor / 75)
        basic_frame = ttk.Frame(self)
        advanced_frame = ttk.Frame(self)
        basic_frame.pack(side="top", fill="both")
        advanced_frame.pack(side="top", fill="both")
        self.basic_frame = basic_frame
        self.advanced_frame = advanced_frame
        # Remove maximize button
        self.resizable(False, False)
        # Remove minimize button
        self.attributes('-toolwindow', True)
        # Set red color
        basic_frame.config(style="Red.TFrame")
        advanced_frame.config(style="Blue.TFrame")
        style = ttk.Style()
        #style.configure("Red.TFrame", background="#ffcccc")
        #style.configure("Blue.TFrame", background="#ccccff")
        label_current_time = ttk.Label(basic_frame, text="Current: 0m00s", font=("Arial", 14), anchor="w")
        label_current_time.grid(row=0, column=0, padx=5, sticky="w")
        label_current_speed = ttk.Label(basic_frame, text="🔥 0 /min", font=("Arial", 14))
        label_current_speed.grid(row=0, column=1, padx=5, sticky="w")
        label_total_time = ttk.Label(basic_frame, text="Total: 0m00s", font=("Arial", 14), anchor="w")
        label_total_time.grid(row=1, column=0, padx=5, sticky="w")
        label_total_speed = ttk.Label(basic_frame, text="🔥 0 /min", font=("Arial", 14))
        label_total_speed.grid(row=1, column=1, padx=5, sticky="w")
        label_map_count = ttk.Label(basic_frame, text="🎫 0", font=("Arial", 14))
        label_map_count.grid(row=0, column=2, padx=5, sticky="w")
        label_current_earn = ttk.Label(basic_frame, text="🔥 0", font=("Arial", 14))
        label_current_earn.grid(row=1, column=2, padx=5, sticky="w")
        inner_pannel_drop_listbox = Listbox(advanced_frame, height=15, width=45, font=("Arial", 10))
        inner_pannel_drop_listbox.insert(END, "Drops will be displayed here")
        inner_pannel_drop_listbox.grid(row=0, column=0, columnspan=6, sticky="nsew")
        inner_pannel_drop_scroll = ttk.Scrollbar(advanced_frame, command=inner_pannel_drop_listbox.yview, orient="vertical")
        inner_pannel_drop_scroll.grid(row=0, column=6, sticky="ns")
        inner_pannel_drop_listbox.config(yscrollcommand=inner_pannel_drop_scroll.set)
        words_short = StringVar()
        words_short.set("Current Map")
        button_drops = ttk.Button(advanced_frame, text="Drops", cursor="hand2", width=7)
        button_drops.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        _settings = ttk.Button(advanced_frame, text="Settings", cursor="hand2", width=7)
        _settings.grid(row=1, column=5, sticky="e", padx=5, pady=5)
        button_change = ttk.Button(advanced_frame, textvariable=words_short, width=10, cursor="hand2")
        button_change.grid(row=1, column=3, pady=5)
        button_log = ttk.Button(advanced_frame, text="Log", width=7, cursor="hand2")
        button_log.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # Initialize button
        button_initialize = ttk.Button(basic_frame, text="Initialize", cursor="hand2", command=self.start_initialization)
        button_initialize.grid(row=0, column=3, padx=5, pady=5)
        
        # Initialize status label
        label_initialize_status = ttk.Label(basic_frame, text="Not initialized", font=("Arial", 10))
        label_initialize_status.grid(row=1, column=3, padx=5, pady=2)
        
        self.button_initialize = button_initialize
        self.label_initialize_status = label_initialize_status
        
        self.inner_pannel_drop_listbox = inner_pannel_drop_listbox
        self.inner_pannel_drop_scroll = inner_pannel_drop_scroll
        self.button_change = button_change
        self.words_short = words_short
        self.label_current_time = label_current_time
        self.label_total_time = label_total_time
        self.label_current_speed = label_current_speed
        self.label_total_speed = label_total_speed
        self.label_map_count = label_map_count
        self.label_current_earn = label_current_earn

        # Create child windows
        self.inner_pannel_settings = Toplevel(self)
        self.inner_pannel_settings.title("Settings")
        self.inner_pannel_settings.geometry()
        # Hide maximize and minimize buttons
        self.inner_pannel_settings.resizable(False, False)
        self.inner_pannel_settings.attributes('-toolwindow', True)
        # Move to the right of main window
        self.inner_pannel_settings.geometry('+0+0')
        
        # Create settings controls
        global config_data
        # Choose tax or no tax
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = f.read()
        config_data = json.loads(config_data)
        # Tax setting
        label_tax = ttk.Label(self.inner_pannel_settings, text="Tax:")
        label_tax.grid(row=0, column=0, padx=5, pady=5)
        chose = ttk.Combobox(self.inner_pannel_settings, values=["No tax", "Include tax"], state="readonly")
        chose.current(config_data.get("tax", 0))
        chose.grid(row=0, column=1, padx=5, pady=5)
        self.chose = chose
        chose.bind("<<ComboboxSelected>>", lambda event: self.change_tax(self.chose.current()))
        
        # Set opacity
        self.label_setting_2 = ttk.Label(self.inner_pannel_settings, text="Opacity:")
        self.label_setting_2.grid(row=1, column=0, padx=5, pady=5)
        # Slider
        self.scale_setting_2 = ttk.Scale(self.inner_pannel_settings, from_=0.1, to=1.0, orient=HORIZONTAL)
        self.scale_setting_2.grid(row=1, column=1, padx=5, pady=5)
        self.scale_setting_2.config(command=self.change_opacity)
        
        # Reset button
        reset_button = ttk.Button(self.inner_pannel_settings, text="Reset Tracking", command=self.reset_tracking)
        reset_button.grid(row=2, column=0, columnspan=2, padx=5, pady=10)
        
        # Setup default values
        self.scale_setting_2.set(config_data["opacity"])
        
        # Create drops panel
        self.inner_pannel_drop = Toplevel(self)
        self.inner_pannel_drop.title("Drops")
        self.inner_pannel_drop.geometry()
        # Hide maximize and minimize buttons
        self.inner_pannel_drop.resizable(False, False)
        self.inner_pannel_drop.attributes('-toolwindow', True)
        # Move to the right of main window
        self.inner_pannel_drop.geometry('+0+0')
        inner_pannel_drop_left = ttk.Frame(self.inner_pannel_drop)
        inner_pannel_drop_left.grid(row=0, column=0)
        words = StringVar()
        words.set("Current: Current Map Drops (Click to toggle All Drops)")
        inner_pannel_drop_show_all = ttk.Button(self.inner_pannel_drop, textvariable=words, width=30)
        inner_pannel_drop_show_all.grid(row=0, column=1)
        self.words = words
        self.inner_pannel_drop_show_all = inner_pannel_drop_show_all
        self.inner_pannel_drop_show_all.config(cursor="hand2", command=self.change_states)
        inner_pannel_drop_right = ttk.Frame(self.inner_pannel_drop)
        inner_pannel_drop_right.grid(row=1, column=1, rowspan=5)
        inner_pannel_drop_total = ttk.Button(self.inner_pannel_drop, text="All", width=7)
        inner_pannel_drop_total.grid(row=0, column=0, padx=5, ipady=10)
        inner_pannel_drop_tonghuo = ttk.Button(self.inner_pannel_drop, text="Currency", width=7)
        inner_pannel_drop_tonghuo.grid(row=1, column=0, padx=5, ipady=10)
        inner_pannel_drop_huijing = ttk.Button(self.inner_pannel_drop, text="Ashes", width=7)
        inner_pannel_drop_huijing.grid(row=2, column=0, padx=5, ipady=10)
        inner_pannel_drop_luopan = ttk.Button(self.inner_pannel_drop, text="Compass", width=7)
        inner_pannel_drop_luopan.grid(row=3, column=0, padx=5, ipady=10)
        inner_pannel_drop_yingguang = ttk.Button(self.inner_pannel_drop, text="Glow", width=7)
        inner_pannel_drop_yingguang.grid(row=4, column=0, padx=5, ipady=10)
        inner_pannel_drop_qita = ttk.Button(self.inner_pannel_drop, text="Others", width=7)
        inner_pannel_drop_qita.grid(row=5, column=0, padx=5, ipady=10)
        self.inner_pannel_drop_total = inner_pannel_drop_total
        self.inner_pannel_drop_tonghuo = inner_pannel_drop_tonghuo
        self.inner_pannel_drop_huijing = inner_pannel_drop_huijing
        self.inner_pannel_drop_luopan = inner_pannel_drop_luopan
        self.inner_pannel_drop_yingguang = inner_pannel_drop_yingguang
        self.inner_pannel_drop_qita = inner_pannel_drop_qita
        self.inner_pannel_drop_total.config(cursor="hand2", command=self.show_all_type)
        self.inner_pannel_drop_tonghuo.config(cursor="hand2", command=self.show_tonghuo)
        self.inner_pannel_drop_huijing.config(cursor="hand2", command=self.show_huijing)
        self.inner_pannel_drop_luopan.config(cursor="hand2", command=self.show_luopan)
        self.inner_pannel_drop_yingguang.config(cursor="hand2", command=self.show_yingguang)
        self.inner_pannel_drop_qita.config(cursor="hand2", command=self.show_qita)
        
        # Hide child windows initially
        self.inner_pannel_drop.withdraw()
        self.inner_pannel_settings.withdraw()
        
        # Set window closing protocols
        self.inner_pannel_drop.protocol("WM_DELETE_WINDOW", self.close_diaoluo)
        self.inner_pannel_settings.protocol("WM_DELETE_WINDOW", self.close_settings)
        
        # Now that all windows are created, set up opacity
        self.change_opacity(config_data["opacity"])
        
        # Keep all windows on top
        self.attributes('-topmost', True)
        self.inner_pannel_drop.attributes('-topmost', True)
        self.inner_pannel_settings.attributes('-topmost', True)
        
        # Set up proper window close handling
        self.protocol("WM_DELETE_WINDOW", self.exit_app)
        
        # Connect buttons
        button_change.config(command=self.change_states, cursor="hand2")
        _settings.config(command=self.show_settings, cursor="hand2")
        button_drops.config(command=self.show_diaoluo, cursor="hand2")
        # Add debug button for log format
        button_log.config(command=debug_log_format, cursor="hand2")
        
        # Add exit button
        button_exit = ttk.Button(basic_frame, text="Exit", cursor="hand2", command=self.exit_app)
        button_exit.grid(row=0, column=4, padx=5, pady=5)
        
    def start_initialization(self):
        """Start the initialization process"""
        start_initialization()
    
    def exit_app(self):
        """Exit the application gracefully"""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            global app_running
            app_running = False
            
            # Close all child windows first
            try:
                self.inner_pannel_drop.destroy()
            except:
                pass
            try:
                self.inner_pannel_settings.destroy()
            except:
                pass
            
            # Close main window
            self.destroy()
            self.quit()

    def reset_tracking(self):
        """Reset all tracking data"""
        global bag_state, bag_initialized, first_scan, drop_list, drop_list_all, income, income_all, total_time, map_count
        global initialization_complete, awaiting_initialization, initialization_in_progress
        
        if messagebox.askyesno("Reset Tracking", 
                         "Are you sure you want to reset all tracking data? This will clear all drop statistics."):
            bag_state.clear()
            bag_initialized = False
            initialization_complete = False
            awaiting_initialization = False
            initialization_in_progress = False
            first_scan = True
            drop_list.clear()
            drop_list_all.clear()
            income = 0
            income_all = 0
            total_time = 0
            map_count = 0
            
            # Update UI
            self.label_current_earn.config(text=f"🔥 0")
            self.label_map_count.config(text=f"🎫 0")
            self.inner_pannel_drop_listbox.delete(1, END)
            self.label_initialize_status.config(text="Not initialized")
            
            messagebox.showinfo("Reset Complete", "All tracking data has been reset.")
            
    def change_tax(self, value):
        global config_data
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = f.read()
        config_data = json.loads(config_data)
        config_data["tax"] = int(value)
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

    def change_states(self):
        global show_all
        show_all = not show_all
        if not show_all:
            self.words.set("Current: Current Map Drops (Click to toggle All Drops)")
            self.words_short.set("Current Map")
        else:
            self.words.set("Current: All Drops (Click to toggle Current Map Drops)")
            self.words_short.set("All Drops")
        self.reshow()
    def show_diaoluo(self):
        this = self.inner_pannel_drop
        # Check if window is hidden
        if this.state() == "withdrawn":
            this.deiconify()
        else:
            this.withdraw()

    def close_diaoluo(self):
        self.inner_pannel_drop.withdraw()

    def close_settings(self):
        self.inner_pannel_settings.withdraw()

    def show_settings(self):
        this = self.inner_pannel_settings
        if this.state() == "withdrawn":
            this.deiconify()
        else:
            this.withdraw()

    def change_opacity(self, value):
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = f.read()
        config_data = json.loads(config_data)
        config_data["opacity"] = float(value)
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        
        # Apply opacity to main window
        self.attributes('-alpha', float(value))
        
        # Only set opacity for child windows if they exist
        if hasattr(self, 'inner_pannel_drop') and self.inner_pannel_drop.winfo_exists():
            self.inner_pannel_drop.attributes('-alpha', float(value))
        
        if hasattr(self, 'inner_pannel_settings') and self.inner_pannel_settings.winfo_exists():
            self.inner_pannel_settings.attributes('-alpha', float(value))
    def reshow(self):
        global drop_list, drop_list_all
        with open("full_table.json", 'r', encoding="utf-8") as f:
            full_table = json.load(f)
        self.label_map_count.config(text=f"🎫 {map_count}")
        if show_all:
            tmp = drop_list_all
            self.label_current_earn.config(text=f"🔥 {round(income_all, 2)}")
        else:
            tmp = drop_list
            self.label_current_earn.config(text=f"🔥 {round(income, 2)}")
        self.inner_pannel_drop_listbox.delete(1, END)
        for i in tmp.keys():
            item_id = str(i)
            if item_id not in full_table:
                continue
                
            item_name = full_table[item_id]["name"]
            item_type = full_table[item_id]["type"]
            if item_type not in self.show_type:
                continue
            now = time.time()
            last_time = full_table[item_id].get("last_update", 0)
            time_passed = now - last_time
            if time_passed < 180:
                status = self.status[0]
            elif time_passed < 900:
                status = self.status[1]
            else:
                status = self.status[2]
            item_price = full_table[item_id]["price"]
            if config_data.get("tax", 0) == 1 and item_id != "100300":
                item_price = item_price * 0.875
            self.inner_pannel_drop_listbox.insert(END, f"{status} {item_name} x{tmp[i]} [{round(tmp[i] * item_price, 2)}]")

    def show_all_type(self):
        self.show_type = ["Compass","Currency","Special Item","Memory Material","Equipment Material","Gameplay Ticket","Map Ticket","Cube Material","Corruption Material","Dream Material","Tower Material","BOSS Ticket","Memory Glow","Divine Emblem","Overlap Material", "Hard Currency"]
        self.reshow()
    def show_tonghuo(self):
        self.show_type = ["Currency", "Hard Currency"]
        self.reshow()
    def show_huijing(self):
        self.show_type = ["Equipment Material", "Ashes"]
        self.reshow()
    def show_luopan(self):
        self.show_type = ["Compass"]
        self.reshow()
    def show_yingguang(self):
        self.show_type = ["Memory Glow", "Memory Fluorescence"]
        self.reshow()
    def show_qita(self):
        self.show_type = ["Special Item","Memory Material","Gameplay Ticket","Map Ticket","Cube Material","Corruption Material","Dream Material","Tower Material","BOSS Ticket","Divine Emblem","Overlap Material"]
        self.reshow()

class MyThread(threading.Thread):
    history = ""
    def run(self):
        global all_time_passed, income, drop_list, t, root
        try:
            self.history = open(position_log, "r", encoding="utf-8")
            self.history.seek(0, 2)
        except:
            print(f"Could not open log file at {position_log}")
            self.history = None
            
        while app_running:
            try:
                time.sleep(1)
                if not app_running:
                    break
                    
                if self.history:
                    things = self.history.read()
                    # Process log changes
                    deal_change(things)
                    get_price_info(things)
                if is_in_map:
                    m = int((time.time() - t) // 60)
                    s = int((time.time() - t) % 60)
                    root.label_current_time.config(text=f"Current: {m}m{s}s")
                    
                    # Calculate current speed (can be negative)
                    current_time_minutes = max((time.time() - t) / 60, 0.01)
                    current_speed = income / current_time_minutes
                    root.label_current_speed.config(text=f"🔥 {round(current_speed, 2)} /min")
                    
                    tmp_total_time = total_time + (time.time() - t)
                    m = int(tmp_total_time // 60)
                    s = int(tmp_total_time % 60)
                    root.label_total_time.config(text=f"Total: {m}m{s}s")
                    
                    # Calculate total speed (can be negative)
                    total_time_minutes = max(tmp_total_time / 60, 0.01)
                    total_speed = income_all / total_time_minutes
                    root.label_total_speed.config(text=f"🔥 {round(total_speed, 2)} /min")
                else:
                    t = time.time()
            except Exception as e:
                print("-------------Exception-----------")
                # Output error line number
                import traceback
                traceback.print_exc()
        
        # Clean up
        if self.history:
            self.history.close()

def price_update():
    """Get price updates from the server and handle translations"""
    while app_running:
        try:
            time.sleep(600)
            if not app_running:
                break
                
            # Get data from server (in Chinese)
            response = rq.get(f"http://{server}/get", timeout=10)
            
            # Check if response is successful and has content
            if response.status_code != 200:
                print(f"Server returned status code: {response.status_code}")
                time.sleep(60)
                continue
                
            if not response.text.strip():
                print("Server returned empty response")
                time.sleep(60)
                continue
            
            # Try to parse JSON
            try:
                r = response.json()
            except json.JSONDecodeError as json_err:
                print(f"Failed to parse JSON from server. Response content: {response.text[:200]}...")
                time.sleep(60)
                continue
            
            # Get current data
            with open("full_table.json", 'r', encoding="utf-8") as f:
                data = json.load(f)
                
            # Update prices from server
            for item_id, item_data in r.items():
                if item_id in data:
                    data[item_id]["price"] = item_data["price"]
                    data[item_id]["last_update"] = time.time()
            
            # Save updated data
            with open("full_table.json", 'w', encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
            print(f"Updated prices for {len(r)} items from server")
            # Wait before next update
            time.sleep(30)
        except Exception as e:
            print(f"Error in price update: {e}")
            time.sleep(60)

# Initialize data files before starting the application
initialize_data_files()

# Create the main application
root = App()
root.wm_attributes('-topmost', 1)

# Start the log reading thread
MyThread().start()

# Start the price update thread
import _thread
_thread.start_new_thread(price_update, ())

# Start the main loop
root.mainloop()