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
            "cost_per_map": 0,
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
    """Initialize the bag state by scanning all current items"""
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

def scan_for_bag_changes(text):
    """Scan the log for bag item modifications"""
    global bag_state, bag_initialized
    
    # Check if we need to initialize
    if not bag_initialized:
        if initialize_bag_state(text):
            return []  # Skip drop detection during initialization
    
    # Pattern to match bag item modifications
    pattern = r'\[.*?\]\[.*?\]GameLog: Display: \[Game\] BagMgr@:Modfy BagItem PageId = (\d+) SlotId = (\d+) ConfigBaseId = (\d+) Num = (\d+)'
    matches = re.findall(pattern, text)
    
    if not matches:
        return []
        
    drops = []
    
    # Track total counts of each item type before this update
    previous_totals = {}
    for item_key, qty in bag_state.items():
        _, _, item_id = item_key.split(':')
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
        _, _, item_id = item_key.split(':')
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

def process_drops(drops, item_id_table, price_table):
    """Process detected drops and update statistics"""
    global income, income_all, drop_list, drop_list_all, config_data
    
    for drop in drops:
        item_id, amount = drop
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
            
        # Update drop counters
        if item_id not in drop_list:
            drop_list[item_id] = 0
        drop_list[item_id] += amount

        if item_id not in drop_list_all:
            drop_list_all[item_id] = 0
        drop_list_all[item_id] += amount
        
        # Calculate price
        price = 0.0
        if item_id in price_table:
            price = price_table[item_id]
            if config_data.get("tax", 0) == 1 and item_id != "100300":
                price = price * 0.875
            income += price * amount
            income_all += price * amount
            
        # Log to drop.txt
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] Drop: {item_name} x{amount} ({round(price, 3)}/each)\n"
        with open("drop.txt", "a", encoding="utf-8") as f:
            f.write(log_line)
            
        print(f"Processed drop: {item_name} x{amount} ({round(price, 3)}/each)")

def deal_change(changed_text):
    global root
    global is_in_map, all_time_passed, drop_list, income, t, drop_list_all, income_all, total_time, map_count
    
    # Check if entering/leaving maps based on scene changes
    entering_map, exiting_map = detect_map_change(changed_text)
    
    if entering_map:
        is_in_map = True
        drop_list = {}
        income = -root.cost
        income_all += -root.cost
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
        print(f"Total tracked slots: {len(bag_state)}")
        
        # Group by item ID for better display
        grouped = {}
        for key, amount in bag_state.items():
            _, _, item_id = key.split(':')
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
                if "BagMgr" in line or "PageApplyBase" in line or "XZ_YuJinZhiXiBiNanSuo200" in line:
                    print(line.strip())
        print("=== END OF DEBUG INFO ===")
        
        # Show in a dialog
        messagebox.showinfo("Debug Information", 
                        f"Debug information has been printed to the console.\n\n"
                        f"Bag state initialized: {bag_initialized}\n"
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
pending_items = {}

class App(Tk):
    show_type = ["Compass","Currency","Special Item","Memory Material","Equipment Material","Gameplay Ticket","Map Ticket","Cube Material","Corruption Material","Dream Material","Tower Material","BOSS Ticket","Memory Glow","Divine Emblem","Overlap Material","Hard Currency"]
    # Checkmark, Circle, X
    status = ["✔", "◯", "✘"]
    cost = 0
    def __init__(self):
        super().__init__()
        self.title("FurTorch v0.0.1a5 - English")
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
        label_current_time.grid(row=0, column=0, padx = 5, sticky="w")
        label_current_speed = ttk.Label(basic_frame, text="🔥 0 /min", font=("Arial", 14))
        label_current_speed.grid(row=0, column=2, sticky="e", padx = 5)
        label_total_time = ttk.Label(basic_frame, text="Total: 00m00s", font=("Arial", 14), anchor="w")
        label_total_time.grid(row=1, column=0, padx = 5, sticky="w")
        label_total_speed = ttk.Label(basic_frame, text="🔥 0 /min", font=("Arial", 14))
        label_total_speed.grid(row=1, column=2, sticky="e", padx = 5)
        self.label_current_time = label_current_time
        self.label_current_speed = label_current_speed
        self.label_total_time = label_total_time
        self.label_total_speed = label_total_speed
        # Separator line
        separator = ttk.Separator(basic_frame, orient='horizontal')
        separator.grid(row=2, columnspan=3, sticky="ew", pady=5)
        # Label spanning two columns
        label_current_earn = ttk.Label(basic_frame, text="🔥 0", font=("Algerian", 20, "bold"))
        label_current_earn.grid(row=3, column=0, padx=5)
        label_map_count = ttk.Label(basic_frame, text="🎫 0", font=("Arial", 14))
        label_map_count.grid(row=3, column=1, padx=5)
        # Button in one column
        words_short = StringVar()
        words_short.set("Current Map")
        self.words_short = words_short
        button_show_advanced = ttk.Button(basic_frame, textvariable=words_short)
        button_show_advanced.grid(row=3, column=2, padx=5)
        button_show_advanced.config(command=self.change_states)
        self.label_current_earn = label_current_earn
        self.label_map_count = label_map_count
        self.button_show_advanced = button_show_advanced

        # Buttons: Drops, Filter, Log, Settings with equal height and width
        button_drops = ttk.Button(advanced_frame, text="Drops", width=7)
        button_filter = ttk.Button(advanced_frame, text="Filter", width=7)
        button_log = ttk.Button(advanced_frame, text="Debug", width=7)
        button_settings = ttk.Button(advanced_frame, text="Settings", width=7)
        button_drops.grid(row=0, column=0, padx=5, ipady=10)
        button_filter.grid(row=0, column=1, padx=5, ipady=10)
        button_log.grid(row=0, column=2, padx=5, ipady=10)
        button_settings.grid(row=0, column=3, padx=5, ipady=10)
        # Four new windows
        self.button_drops = button_drops
        self.button_filter = button_filter
        self.button_log = button_log
        self.button_settings = button_settings

        self.button_settings.config(command=self.show_settings, cursor="hand2")
        self.button_drops.config(command=self.show_diaoluo, cursor="hand2")
        # Add debug button for log format
        self.button_log.config(command=debug_log_format, cursor="hand2")

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
        self.inner_pannel_drop_total.config(command=self.show_all_type, cursor="hand2")
        self.inner_pannel_drop_tonghuo.config(command=self.show_tonghuo, cursor="hand2")
        self.inner_pannel_drop_huijing.config(command=self.show_huijing, cursor="hand2")
        self.inner_pannel_drop_luopan.config(command=self.show_luopan, cursor="hand2")
        self.inner_pannel_drop_yingguang.config(command=self.show_yingguang, cursor="hand2")
        self.inner_pannel_drop_qita.config(command=self.show_qita, cursor="hand2")
        # Vertical scrollbar
        self.inner_pannel_drop_scrollbar = Scrollbar(inner_pannel_drop_right)
        self.inner_pannel_drop_scrollbar.config(orient=VERTICAL)
        self.inner_pannel_drop_scrollbar.pack(side=RIGHT, fill=Y)
        self.inner_pannel_drop_listbox = Listbox(inner_pannel_drop_right, yscrollcommand=self.inner_pannel_drop_scrollbar.set, width=50, height=20)
        self.inner_pannel_drop_listbox.pack(side=LEFT, fill=BOTH)
        self.inner_pannel_drop_scrollbar.config(command=self.inner_pannel_drop_listbox.yview)
        self.inner_pannel_drop_listbox.insert(END, f"{self.status[0]} <3min {self.status[1]} <15min {self.status[2]} >15min")
        # Set row height
        self.inner_pannel_drop_listbox.config(font=("Consolas", 12))
        # Set width
        self.inner_pannel_drop_listbox.config(width=30)

        # Settings page
        self.inner_pannel_settings = Toplevel(self)
        self.inner_pannel_settings.title("Settings")
        self.inner_pannel_settings.geometry()
        # Hide maximize and minimize buttons
        self.inner_pannel_settings.resizable(False, False)
        self.inner_pannel_settings.attributes('-toolwindow', True)
        # Move to the right of main window
        self.inner_pannel_settings.geometry('+300+0')
        # Label + text box
        label_setting_1 = ttk.Label(self.inner_pannel_settings, text="Cost per map:")
        label_setting_1.grid(row=0, column=0, padx=5, pady=5)
        entry_setting_1 = ttk.Entry(self.inner_pannel_settings)
        entry_setting_1.grid(row=0, column=1, padx=5, pady=5)
        global config_data
        # Choose tax or no tax
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = f.read()
        config_data = json.loads(config_data)
        chose = ttk.Combobox(self.inner_pannel_settings, values=["No tax", "Include tax"], state="readonly")
        chose.current(config_data.get("tax", 0))
        chose.grid(row=2, column=1, padx=5, pady=5)
        self.chose = chose
        chose.bind("<<ComboboxSelected>>", lambda event: self.change_tax(self.chose.current()))
        self.label_setting_1 = label_setting_1
        self.entry_setting_1 = entry_setting_1
        # Set opacity
        self.label_setting_2 = ttk.Label(self.inner_pannel_settings, text="Opacity:")
        self.label_setting_2.grid(row=1, column=0, padx=5, pady=5)
        # Slider
        self.scale_setting_2 = ttk.Scale(self.inner_pannel_settings, from_=0.1, to=1.0, orient=HORIZONTAL)
        self.scale_setting_2.grid(row=1, column=1, padx=5, pady=5)
        self.scale_setting_2.config(command=self.change_opacity)
        
        # Reset button
        reset_button = ttk.Button(self.inner_pannel_settings, text="Reset Tracking", command=self.reset_tracking)
        reset_button.grid(row=3, column=0, columnspan=2, padx=5, pady=10)
        
        print(config_data)
        self.entry_setting_1.insert(0, str(config_data["cost_per_map"]))
        self.entry_setting_1.bind("<Return>", lambda event: self.change_cost(self.entry_setting_1.get()))
        self.scale_setting_2.set(config_data["opacity"])
        self.change_opacity(config_data["opacity"])
        self.change_cost(config_data["cost_per_map"])
        self.inner_pannel_drop.withdraw()
        self.inner_pannel_settings.withdraw()
        self.inner_pannel_drop.protocol("WM_DELETE_WINDOW", self.close_diaoluo)
        self.inner_pannel_settings.protocol("WM_DELETE_WINDOW", self.close_settings)
        # Keep on top
        self.attributes('-topmost', True)
        self.inner_pannel_drop.attributes('-topmost', True)
        self.inner_pannel_settings.attributes('-topmost', True)
        
    def reset_tracking(self):
        """Reset all tracking data"""
        global bag_state, bag_initialized, first_scan, drop_list, drop_list_all, income, income_all, total_time, map_count
        
        if messagebox.askyesno("Reset Tracking", 
                         "Are you sure you want to reset all tracking data? This will clear all drop statistics."):
            bag_state.clear()
            bag_initialized = False
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
    def change_cost(self, value):
        value = str(value)
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = f.read()
        config_data = json.loads(config_data)
        config_data["cost_per_map"] = float(value)
        with open("config.json", "w", encoding="utf-8") as f:
            print(config_data)
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        self.cost = float(value)
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
        try:
            value = float(self.entry_setting_1.get())
            self.change_cost(value)
        except:
            pass
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
        self.attributes('-alpha', float(value))
        self.inner_pannel_drop.attributes('-alpha', float(value))
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
            
        while True:
            try:
                time.sleep(1)
                if self.history:
                    things = self.history.read()
                    # Process log changes
                    deal_change(things)
                    get_price_info(things)
                if is_in_map:
                    m = int((time.time() - t) // 60)
                    s = int((time.time() - t) % 60)
                    root.label_current_time.config(text=f"Current: {m}m{s}s")
                    root.label_current_speed.config(text=f"🔥 {round(income / max((time.time() - t) / 60, 0.01), 2)} /min")
                    tmp_total_time = total_time + (time.time() - t)
                    m = int(tmp_total_time // 60)
                    s = int(tmp_total_time % 60)
                    root.label_total_time.config(text=f"Total: {m}m{s}s")
                    root.label_total_speed.config(text=f"🔥 {round(income_all / max(tmp_total_time / 60, 0.01), 2)} /min")
                else:
                    t = time.time()
            except Exception as e:
                print("-------------Exception-----------")
                # Output error line number
                import traceback
                traceback.print_exc()

def price_update():
    """Get price updates from the server and handle translations"""
    while True:
        try:
            # Get data from server (in Chinese)
            r = rq.get(f"http://{server}/get", timeout=10).json()
            
            # Load our English version of the items
            with open("en_id_table.json", 'r', encoding="utf-8") as f:
                english_items = json.load(f)
                
            # Create the translation mapping if needed
            translation_mapping = load_translation_mapping()
            
            # Update the translation mapping
            for item_id, item_data in r.items():
                chinese_name = item_data["name"]
                
                # If we have an English name for this ID in our translation table
                if item_id in english_items:
                    english_name = english_items[item_id]["name"]
                    english_type = english_items[item_id]["type"]
                    
                    # Store the translation mapping
                    translation_mapping[chinese_name] = english_name
                    
                    # Update the item data with English info
                    r[item_id]["name"] = english_name
                    r[item_id]["type"] = english_type
            
            # Save the updated mapping
            save_translation_mapping(translation_mapping)
            
            # Save the English version of the data
            with open("full_table.json", 'w', encoding="utf-8") as f:
                json.dump(r, f, indent=4, ensure_ascii=False)
                
            print("Price update successful")
            
            # Process pending items
            n = pending_items.copy()
            for i in n.keys():
                try:
                    r = rq.get(f"http://{server}/gowork?id="+i, timeout=10).json()
                    del pending_items[i]
                    print(f"[NETWORK] ID {i} fetch completed")
                except Exception as e:
                    print(f"Error processing pending item {i}: {e}")
                
            time.sleep(90)
        except Exception as e:
            print("Price update failed: " + str(e))
            time.sleep(10)


def price_submit(ids, price, user):
    """Submit price data to the server"""
    print(price)
    try:
        r = rq.get(f"http://{server}/update?user={user}&ids={ids}&new_price={price}", timeout=10).json()
        print(r)
        return r
    except Exception as e:
        print(e)

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