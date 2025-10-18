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

def get_price_info(text):
    try:
        pattern_id = r'XchgSearchPrice----SynId = (\d+).*?\+filters\+1\+refer \[(\d+)\]'
        match = re.findall(pattern_id, text, re.DOTALL)
        result = list(match)
        for i, item in enumerate(result, 1):
            ids = item[1]
            synid = item[0]
            pattern = re.compile(
                rf'----Socket RecvMessage STT----XchgSearchPrice----SynId = {synid}\s+'  # 匹配目标SynId
                r'\[.*?\]\s*GameLog: Display: \[Game\]\s+'  # 匹配时间和固定前缀
                r'(.*?)(?=----Socket RecvMessage STT----|$)',  # 匹配数据块内容（到下一个数据块或结束）
                re.DOTALL  # 允许.匹配换行
            )

            # 查找目标数据块
            match = pattern.search(text)
            data_block = match.group(1)
            if not match:
                print(f'发现记录： ID:{item[1]}, 价格:-1')
            if int(item[1]) == 100300:
                continue
            # 提取所有+数字 [数值]中的数值（忽略currency）
            value_pattern = re.compile(r'\+\d+\s+\[([\d.]+)\]')  # 匹配+数字 [x.x]格式
            values = value_pattern.findall(data_block)
            # 获得前30个values的平均值，但若values的长度小于30，则取全部的平均值
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
                    #full_table[ids]['from'] = "Local"
                    full_table[ids]['from'] = "FurryHeiLi"
                    full_table[ids]['price'] = round(average_value, 4)
                except:
                    pass
            with open("full_table.json", 'w', encoding="utf-8") as f:
                json.dump(full_table, f, indent=4, ensure_ascii=False)
            print(f'更新物品价值： ID:{ids}, 名称:{full_table[ids]["name"]}, 价格:{round(average_value, 4)}')
    except:
        pass




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
    global is_in_map, all_time_passed, drop_list, income, t, drop_list_all, income_all, total_time
    if "PageApplyBase@ _UpdateGameEnd: LastSceneName = World'/Game/Art/Maps/01SD/XZ_YuJinZhiXiBiNanSuo200/XZ_YuJinZhiXiBiNanSuo200.XZ_YuJinZhiXiBiNanSuo200' NextSceneName = World'/Game/Art/Maps" in changed_text:
        is_in_map = True
        drop_list = {}
        income = 0
    if "NextSceneName = World'/Game/Art/Maps/01SD/XZ_YuJinZhiXiBiNanSuo200/XZ_YuJinZhiXiBiNanSuo200.XZ_YuJinZhiXiBiNanSuo200'" in changed_text:
        is_in_map = False
        total_time += time.time() - t
    texts = scanned_log(changed_text)
    for i in texts:
        data = log_to_json(i)
        data = data["DropItems"]
        for item in data:
            #print(data[item])
            if is_in_map == False:
                is_in_map = True
            if not data[item].get("Picked", False):
                continue
            if data[item]["item"].get("SpecialInfo", True):
                data[item]["item"]["BaseId"] = data[item]["item"]["SpecialInfo"]["BaseId"]
                data[item]["item"]["Num"] = data[item]["item"]["SpecialInfo"]["Num"]
            item_id = str(data[item]["item"]["BaseId"])
            with open("full_table.json", 'r', encoding="utf-8") as f:
                full = json.load(f)
            item_name = full[item_id]["name"]
            price = full[item_id]["price"]
            drop_list[item_name] = drop_list.get(item_name, 0) + data[item]["item"]["Num"]
            drop_list_all[item_name] = drop_list_all.get(item_name, 0) + data[item]["item"]["Num"]
            income += price * data[item]["item"]["Num"]
            income_all += price * data[item]["item"]["Num"]
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
total_time = 0
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
        scrollbar = tkinter.Scrollbar(root)
        label_time = Label(text="地图耗时: 0m0s", font=("宋体", 12, "bold"), anchor="w")
        label_time.pack()
        label_time_all = Label(text="总耗时: 0m0s", font=("宋体", 12, "bold"), anchor="w")
        label_time_all.pack()
        label_drop = Label(text="该地图掉落统计: 暂无", font=("宋体", 12, "bold"), anchor="center", height=20)
        label_drop_all = Label(text="掉落总计: 0 火", font=("宋体", 12, "bold"), anchor="w")
        words = tkinter.StringVar()
        words.set("目前：当前地图掉落 点击切换总掉落")
        button_change = Button(textvariable=words, font=("宋体", 12, "bold"), command=lambda: change_states(words))
        button_change.pack()
        label_drop_all.pack()
        label_drop.pack()
        button_clear = Button(text="清除掉落物记录", font=("宋体", 12, "bold"), command=lambda: {drop_list_all.clear()})
        button_clear.pack()
        while True:
            time.sleep(1)
            try:
                things = self.history.read()
                #print(things)
                deal_change(things)
                get_price_info(things)
                if is_in_map:
                    m = int((time.time() - t) // 60)
                    s = int((time.time() - t) % 60)
                    label_time.config(
                        text=f"地图耗时: {m}m{s}s 效率： {round(income / ((time.time() - t) / 60), 3)} 火/分钟")
                    tmp_total_time = total_time + (time.time() - t)
                    m = int(tmp_total_time // 60)
                    s = int(tmp_total_time % 60)
                    label_time_all.config(
                        text=f"总耗时: {m}m{s}s 效率： {round(income_all / (tmp_total_time / 60), 2)} 火/分钟")
                else:
                    t = time.time()
                if show_all:
                    label_drop_tmp = ""
                    for i in drop_list_all.keys():
                        label_drop_tmp += f"{i} x{drop_list_all[i]}\n"
                    if len(drop_list) < 15 :
                        label_drop.config(text=f"该地图掉落统计: \n{label_drop_tmp}")
                    else:
                        label_drop.config(wraplength=650)
                        label_drop_tmp = label_drop_tmp.replace("\n", "|")
                        label_drop.config(text=f"总掉落统计:\n{label_drop_tmp}", width=70)
                    label_drop_all.config(text=f"掉落总计: {round(income_all, 3)} 火")
                else:
                    label_drop_tmp = ""
                    for i in drop_list.keys():
                        label_drop_tmp += f"{i} x{drop_list[i]} \n"
                    if len(drop_list) < 15:
                        label_drop.config(text=f"该地图掉落统计: \n{label_drop_tmp}")
                    else:
                        label_drop.config(wraplength=650)
                        label_drop_tmp = label_drop_tmp.replace("\n", "|")
                        label_drop.config(text=f"该地图掉落统计: \n{label_drop_tmp}", width=70)
                    label_drop_all.config(text=f"该地图掉落总计: {round(income, 3)} 火")

            except Exception as e:
                print("发生异常，但问题不大，除非一直显示这个")
                print("------------异常内容------------------\n")
                print(e)
                print("\n-------------------------------------")


root = tkinter.Tk()
root.wm_attributes('-topmost', 1)
# 背景透明
root.wm_attributes('-alpha', 0.6)
root.title("FurTorch V0.0.1a3")
MyThread().start()
root.mainloop()
