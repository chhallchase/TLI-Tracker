import time
import psutil
import win32gui
import win32process
import win32api
import tkinter
from tkinter import messagebox, BitmapImage, Label, Button
import threading
import re
import json
def parse_log_structure(log_text):
    """解析带有层级结构的日志文本，通过|的数量判断层级关系"""
    # 按行分割日志
    lines = [line.strip() for line in log_text.split('\n') if line.strip()]

    # 构建层级结构
    stack = []  # 用于保存各级节点的栈
    root = {}
    current = root

    for line in lines:
        # 计算当前行的层级（根据|符号的数量）
        level = line.count('|')

        # 提取键值部分（移除所有|和多余空格）
        content = re.sub(r'\|+', '', line).strip()

        # 调整栈以匹配当前层级：层级减少时出栈
        while len(stack) > level:
            stack.pop()

        # 确定父节点：栈顶元素为父节点，空栈时父节点是根节点
        parent = root
        if stack:
            parent = stack[-1]

        # 解析内容为键和值
        if '[' in content and ']' in content:
            # 提取键名和值
            key_part = content[:content.index('[')].strip()
            value_part = content[content.index('[') + 1: content.rindex(']')].strip()

            # 转换值类型
            if value_part.lower() == 'true':
                value = True
            elif value_part.lower() == 'false':
                value = False
            elif value_part.isdigit():
                value = int(value_part)
            elif re.match(r'^-?\d+$', value_part):
                value = int(value_part)
            else:
                value = value_part

            # 处理多级键（如+item+SpecialInfo拆分为item和SpecialInfo）
            keys = [k for k in key_part.split('+') if k]
            current_node = parent

            for i, key in enumerate(keys):
                if i == len(keys) - 1:
                    # 最后一个键，设置值
                    current_node[key] = value
                else:
                    # 中间键，创建嵌套字典
                    if key not in current_node:
                        current_node[key] = {}
                    current_node = current_node[key]

            # 将当前节点入栈
            stack.append(current_node)

        else:
            # 没有值的键（如+item+SpecialInfo），创建为字典
            key_part = content.strip()
            keys = [k for k in key_part.split('+') if k]
            current_node = parent

            for key in keys:
                if key not in current_node:
                    current_node[key] = {}
                current_node = current_node[key]

            # 将当前节点入栈
            stack.append(current_node)

    return root


def log_to_json(log_text):
    """将日志文本转换为JSON字符串"""
    parsed_data = parse_log_structure(log_text)
    #return json.dumps(parsed_data, indent=4, ensure_ascii=False)
    return parsed_data




all_time_passed = 1

hwnd = win32gui.FindWindow(None, "Torchlight: Infinite  ")
tid, pid = win32process.GetWindowThreadProcessId(hwnd)
process = psutil.Process(pid)
position_game = process.exe()
position_log = position_game + "/../../../TorchLight/Saved/Logs/UE_game.log"
position_log = position_log.replace("\\", "/")
print(position_log)
with open(position_log, "r", encoding="utf-8") as f:
    print(f.read()[-100:])

def scanned_log(changed_text):
    name = "+DropItems+1+"
    # 从上之下寻找name
    lines = changed_text.split("\n")
    tmp = []
    write = False
    for line in lines:
        if write:
            if line[0] != "[":
                if line.count("|") == 1:
                    line = line.replace("|         ", "DropItems")
                tmp[-1] += line + "\n"
            else:
                write = False
        if name in line:
            write = True
            tmp.append(line + "\n")

    return tmp

def deal_change(changed_text):
    global is_in_map, all_time_passed, drop_list, income, t, drop_list_all, income_all
    if "[Game] LevelMgr@ EnterLevel" in changed_text:
        is_in_map = not is_in_map
        if is_in_map:
            drop_list = {}
            income = 0


    texts = scanned_log(changed_text)
    for i in texts:
        data = log_to_json(i)
        data = data["DropItems"]
        for item in data:
            print(data[item])
            if is_in_map == False:
                is_in_map = True
            if not data[item].get("Picked", False):
                continue
            if data[item]["item"].get("SpecialInfo", True):
                data[item]["item"]["BaseId"] = data[item]["item"]["SpecialInfo"]["BaseId"]
                data[item]["item"]["Num"] = data[item]["item"]["SpecialInfo"]["Num"]
            item_id = data[item]["item"]["BaseId"]
            with open("id_table.conf", 'r', encoding="utf-8") as f:
                id_table = f.readlines()
                for i in id_table:
                    _id = i.split(" ")[0]
                    name = i.split(" ")[1].replace("\n", "")
                    if _id == str(item_id):
                        item_id = name
                        break
            drop_list[item_id] = drop_list.get(item_id, 0) + data[item]["item"]["Num"]
            drop_list_all[item_id] = drop_list_all.get(item_id, 0) + data[item]["item"]["Num"]
            price = 0
            with open("price.json", "r", encoding="utf-8") as f:
                j = json.load(f)
                if item_id in j.keys():
                    income += j[item_id]
                    income_all += j[item_id]
                    price = j[item_id]
            print("掉落:" + str(item_id))
            with open("drop.txt", 'a', encoding="utf-8") as f:
                now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                f.write(f"[{now}] 掉落: {item_id} x{data[item]['item']['Num']} 份 （{round(price, 3)}/份)\n")

is_in_map = False
drop_list = {}
drop_list_all = {}
income = 0
income_all = 0
t = time.time()
show_all = False
def change_states(words: tkinter.StringVar):
    global show_all
    show_all = not show_all
    if not show_all:
        words.set("目前：当前地图掉落 点击切换总掉落")
    else:
        words.set("目前：总掉落 点击切换当前地图掉落")
class MyThread(threading.Thread):
    history = ""

    def run(self):
        global all_time_passed, income, drop_list, t
        self.history = open(position_log, "r", encoding="utf-8")
        self.history.read()
        from tkinter import Widget, Label
        import time
        label_time = Label(text="地图耗时: 0m0s", font=("Arial", 12, "bold"), anchor="w")
        label_time.pack()
        label_drop = Label(text="该地图掉落统计: 暂无", font=("Arial", 12, "bold"), anchor="w")
        label_drop_all = Label(text="掉落总计: 0 火", font=("Arial", 12, "bold"), anchor="w")
        words = tkinter.StringVar()
        words.set("目前：当前地图掉落 点击切换总掉落")
        button_change = Button(textvariable=words, font=("Arial", 12, "bold"), command=lambda: change_states(words))
        button_change.pack()
        label_drop.pack()
        label_drop_all.pack()
        while True:
            time.sleep(1)
            try:
                if is_in_map:
                    m = int((time.time() - t) // 60)
                    s = int((time.time() - t) % 60)
                    label_time.config(text=f"地图耗时: {m}m{s}s")
                else:
                    t = time.time()
                things = self.history.read()
                print(things)
                print("=------=")
                deal_change(things)
                if show_all:
                    label_drop_tmp = ""
                    for i in drop_list_all.keys():
                        label_drop_tmp += f"{i} x{drop_list_all[i]} \n"
                    label_drop.config(text=f"总掉落统计: \n{label_drop_tmp}")
                    label_drop_all.config(text=f"掉落总计: {round(income_all, 3)} 火")
                else:
                    label_drop_tmp = ""
                    for i in drop_list.keys():
                        label_drop_tmp += f"{i} x{drop_list[i]} \n"
                    label_drop.config(text=f"该地图掉落统计: \n{label_drop_tmp}")
                    label_drop_all.config(text=f"该地图掉落总计: {round(income, 3)} 火")
            except Exception as e:
                print("发生异常，但问题不大，除非一直显示这个")
                print("------------异常内容------------------\n")
                print(e)
                print("\n-------------------------------------")


root = tkinter.Tk()
root.wm_attributes('-topmost', 1)
# 背景透明
root.wm_attributes('-alpha', 0.7)
MyThread().start()
root.mainloop()
