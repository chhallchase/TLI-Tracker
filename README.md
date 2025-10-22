# FurTorch
 FurTorch Torchlight Income Statistics Tool - Test Version
## Packaging Method
``` 
pip install -r requirements.txt
python setup.py py2exe
```

## Code Explanation
<s>Since I originally only intended to use it myself, the code is written somewhat chaotically. To prevent only God knowing what each section means in the future, and to facilitate secondary development, I've written this section</s>

### Global Variable Definitions
| Variable     | Definition                               |
|--------------|------------------------------------------|
| `t`          | Map start timestamp, used to track map time |
| `show_all`   | Display current map drops/total drops      |
| `is_in_map`  | Whether in map                           |

### UI Component Names
| Component Name     | Definition                           |
|-------------------|-------------------------------------|
| `label_time`      | Display map time, label             |
| `label_drop`      | Display drops, label                |
| `label_drop_all`  | Display drop item value, label      |
| `button_change`   | Toggle current map drops/total drops display, button |

### Function Definitions
| Function Name         | Definition                                                      |
|----------------------|----------------------------------------------------------------|
| `parse_log_structure`| Parse log structure into JSON format (modified after AI generation) |
| `scanned_log`        | Search for drop-related parts in log file, pass to parse function |
| `deal_change`        | Search for entering/leaving map info<br>Pass to scanner_log to search for drops<br>Parse dropped item categories, quantities<br>Write info to array |
| `change_states`      | Triggered by `button_change`, change drop display |
| `get_price_info`     | When you check prices on the exchange, automatically read log file<br>Update currency price (average of first 30 sell orders) |

### Configuration File Structure
### id_table.conf 
Match log file IDs with drop item names
```
<Item ID>[space]<Item Name>
Example:
100200 Initial Fire Sand
100300 Initial Fire Essence
```
### price.json
Item price file
```
{
    "<Item Name>":<Item Price>,
    "Initial Fire Sand":999,
    "Initial Fire Essence":0
}
```

When you discover a drop item that doesn't exist in id_table.conf or prices have significantly changed, you can submit an ISSUE or send a PUSH after making changes. Thank you