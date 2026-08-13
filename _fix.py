import re

file_path = r"d:\My_Project\多智能体小红书发布平台\frontend\src\styles\workbench\_nav.css"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

print(f"文件总字符数: {len(text)}")

lines = text.split("\n")
clean_lines = []
for line in lines:
    if "Groups" in line and ".Value" in line:
        continue
    if "TrimEnd()" in line:
        continue
    if "args[" in line:
        continue
    clean_lines.append(line)

lines = clean_lines
text = "\n".join(lines)
print(f"清理垃圾后行数: {len(lines)}")

mp_positions = [i for i, l in enumerate(lines) if ".magic-particles {" in l]
wf_footer_positions = [i for i, l in enumerate(lines) if ".mint-wf-footer {" in l]
print(f".magic-particles 出现: {[p+1 for p in mp_positions]}")
print(f".mint-wf-footer 出现: {[p+1 for p in wf_footer_positions]}")

def find_block_end(lines_list, start):
    depth = 0
    started = False
    for i in range(start, len(lines_list)):
        if "{" in lines_list[i]:
            depth += lines_list[i].count("{")
            started = True
        if "}" in lines_list[i]:
            depth -= lines_list[i].count("}")
        if started and depth <= 0 and "}" in lines_list[i]:
            return i
    return -1

copy1_end = None
copy2_start = None
copy2_end = None
if len(wf_footer_positions) >= 1:
    copy1_end = find_block_end(lines, wf_footer_positions[0]) + 1
if len(wf_footer_positions) >= 2:
    copy2_end = find_block_end(lines, wf_footer_positions[1]) + 1
if len(mp_positions) >= 2:
    copy2_start = mp_positions[1]
    for i in range(copy2_start, max(0, copy2_start-20), -1):
        if "/* ===" in lines[i]:
            copy2_start = i
            break

copy1_lines = lines[:copy1_end] if copy1_end else []
copy2_lines = lines[copy2_start:copy2_end] if (copy2_start and copy2_end) else []
print(f"第一份行数: {len(copy1_lines)}")
print(f"第二份行数: {len(copy2_lines)}")

def has_block(ls, sel):
    return any(sel in l and l.strip().find(sel) == 0 for l in ls)

print(f"第一份有 mint-logo-box: {has_block(copy1_lines, '.mint-logo-box {')}")
print(f"第一份有 mint-logo-divider: {has_block(copy1_lines, '.mint-logo-divider {')}")
print(f"第二份有 mint-logo-box: {has_block(copy2_lines, '.mint-logo-box {')}")
print(f"第二份有 mint-logo-divider: {has_block(copy2_lines, '.mint-logo-divider {')}")

base_lines = copy1_lines
if has_block(copy2_lines, ".mint-logo-box {") and not has_block(copy1_lines, ".mint-logo-box {"):
    base_lines = copy2_lines
    print("选择第二份作为基础")
else:
    print("选择第一份作为基础")
print(f"基础行数: {len(base_lines)}")
print()
print("=== 打印基础中 mint-logo-box 相关行 (行号245-295) ===")
for i in range(max(0, 244), min(len(base_lines), 295)):
    print(f"  {i+1:4d}: {base_lines[i].rstrip()}")
