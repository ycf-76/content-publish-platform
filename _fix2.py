file_path = r"d:\My_Project\多智能体小红书发布平台\frontend\src\styles\workbench\_nav.css"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
clean_lines = []
for line in lines:
    if "Groups" in line and ".Value" in line:
        continue
    if "TrimEnd()" in line:
        continue
    if "args[" in line:
        continue
    if "$oldPad" in line or "$newPad" in line or "$prefix" in line or "$suffix" in line:
        continue
    clean_lines.append(line)
lines = clean_lines

# ========== 裁剪第一份内容 ==========
wf_footer_positions = [i for i, l in enumerate(lines) if ".mint-wf-footer {" in l]
def find_block_end(ls, start):
    depth = 0; started = False
    for i in range(start, len(ls)):
        if "{" in ls[i]: depth += ls[i].count("{"); started = True
        if "}" in ls[i]: depth -= ls[i].count("}")
        if started and depth <= 0 and "}" in ls[i]: return i
    return -1

if len(wf_footer_positions) >= 1:
    copy1_end = find_block_end(lines, wf_footer_positions[0]) + 1
    lines = lines[:copy1_end]

print(f"裁剪后基础行数: {len(lines)}")

# ========== 修改点5: collapsed mint-logo-box -> mint-logo-top ==========
for i, line in enumerate(lines):
    if ".mint-shell.mint-collapsed .mint-logo-box" in line:
        lines[i] = line.replace(
            ".mint-shell.mint-collapsed .mint-logo-box { justify-content: center; padding: 14px 8px; }",
            ".mint-shell.mint-collapsed .mint-logo-top { padding: 14px 8px 0; }"
        )
        print(f"[OK] 修改点5 (collapsed引用) 第{i+1}行")
        break

# ========== 修改点3: mint-logo-top 加 padding ==========
# 同时补回注释掉的 mint-logo-box 和 mint-logo-divider 块
commented_logo_box = """/* .mint-logo-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 14px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease;
}
.mint-logo-box:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,0,0,0.06);
} */"""

commented_logo_divider = """/* .mint-logo-divider {
  height: 1px;
  background: rgba(16,185,129,0.12);
  margin: 0 2px;
} */"""

# 找 mint-logo-top { 的位置（非 collapsed 版本）
for i, line in enumerate(lines):
    stripped = line.strip()
    # 精确匹配：行首就是 .mint-logo-top {（不带前缀）
    if stripped.startswith(".mint-logo-top {") and ".mint-collapsed" not in line:
        logo_top_idx = i
        # 在它前面插入 mint-logo-box 注释块
        insert_pos = i
        # 向前跳过空行
        while insert_pos > 0 and lines[insert_pos-1].strip() == "":
            insert_pos -= 1
        lines_insert = []
        lines_insert.append("")
        lines_insert.extend(commented_logo_box.split("\n"))
        lines_insert.append("")
        lines = lines[:insert_pos] + lines_insert + lines[insert_pos:]
        print(f"[OK] 补回 mint-logo-box 注释块 (插入到第{insert_pos+1}行)")
        break

# 重新计算位置
# 给 mint-logo-top 加 padding
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith(".mint-logo-top {") and ".mint-collapsed" not in line:
        # 找块的 }
        block_start = i
        block_end = find_block_end(lines, i)
        has_padding = False
        for j in range(block_start, block_end+1):
            if "padding:" in lines[j]:
                # 替换 padding
                indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                lines[j] = indent + "padding: 16px 16px 0;"
                has_padding = True
                print(f"[OK] 修改点3 (mint-logo-top padding 替换) 第{j+1}行")
                break
        if not has_padding:
            # 在 } 前插入
            indent = "  "
            # 找 body 行的缩进
            for j in range(block_start+1, block_end):
                if lines[j].strip():
                    indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                    break
            lines.insert(block_end, indent + "padding: 16px 16px 0;")
            print(f"[OK] 修改点3 (mint-logo-top padding 新增) 第{block_end+1}行前")
        break

# 补回 mint-logo-divider 注释（在 mint-logo-top 块之后、mint-logo-icon 之前）
for i, line in enumerate(lines):
    if ".mint-logo-icon {" in line.strip() and "::" not in line and ":hover" not in line:
        insert_pos = i
        while insert_pos > 0 and lines[insert_pos-1].strip() == "":
            insert_pos -= 1
        # 检查是否已经有 mint-logo-divider 的注释
        already = False
        for k in range(max(0, insert_pos-10), insert_pos):
            if "mint-logo-divider" in lines[k]:
                already = True
                break
        if not already:
            lines_insert = []
            lines_insert.append("")
            lines_insert.extend(commented_logo_divider.split("\n"))
            lines_insert.append("")
            lines = lines[:insert_pos] + lines_insert + lines[insert_pos:]
            print(f"[OK] 补回 mint-logo-divider 注释块 (插入到第{insert_pos+1}行)")
        break

# ========== 修改点4: mint-logo-box:hover .mint-logo-icon 注释 + 新增 mint-logo-top:hover ==========
# 先找 mint-logo-box:hover .mint-logo-icon 的注释（可能已经存在）
found_old_comment = False
for i, line in enumerate(lines):
    if ".mint-logo-box:hover .mint-logo-icon" in line:
        if line.strip().startswith("/*"):
            found_old_comment = True
            print(f"[OK] 旧规则已注释 第{i+1}行")
        else:
            # 这个块需要注释
            block_end = find_block_end(lines, i)
            # 注释整个块
            lines[i] = "/* " + lines[i].lstrip()
            # 找到块结束的 }，在其后加 */
            depth_count = 0
            for j in range(i, block_end+1):
                if "{" in lines[j]: depth_count += lines[j].count("{")
                if "}" in lines[j]:
                    depth_count -= lines[j].count("}")
                    if j == block_end or depth_count == 0:
                        lines[j] = lines[j].rstrip() + " */"
                        block_end_act = j
                        break
            print(f"[OK] 修改点4 (旧规则注释) 第{i+1}-{block_end_act+1}行")
        break

# 确保 mint-logo-top:hover 规则存在（在 mint-logo-icon 规则之后的合适位置）
has_new_rule = False
for line in lines:
    if ".mint-logo-top:hover .mint-logo-icon" in line and not line.strip().startswith("/*"):
        has_new_rule = True
        print("[OK] 新规则已存在")
        break

if not has_new_rule:
    # 在 mint-logo-box:hover 注释块之后插入
    for i, line in enumerate(lines):
        if "mint-logo-box:hover .mint-logo-icon" in line and line.strip().startswith("/*"):
            block_end = i
            depth = 0; started = False
            for j in range(i, len(lines)):
                if "/*" in lines[j]: depth += 1; started = True
                if "*/" in lines[j]: depth -= 1
                if started and depth == 0 and "*/" in lines[j]:
                    block_end = j
                    break
            insert_pos = block_end + 1
            new_rule = ".mint-logo-top:hover .mint-logo-icon { transform: translateY(-1px) scale(1.03); }"
            lines.insert(insert_pos, new_rule)
            print(f"[OK] 修改点4 (新增 mint-logo-top:hover 规则) 第{insert_pos+1}行")
            break

# ========== 修改点6: mint-user-card 去卡片 ==========
for i, line in enumerate(lines):
    stripped = line.strip()
    if (stripped == ".mint-user-card {" or stripped.startswith(".mint-user-card {")) \
       and ":hover" not in line and "-active" not in line and ">" not in line \
       and ".mint-collapsed" not in line:
        block_start = i
        block_end = find_block_end(lines, i)
        # 重写这个块的属性
        new_block = [
            ".mint-user-card {",
            "  display: flex;",
            "  align-items: center;",
            "  gap: 10px;",
            "  padding: 8px 16px;",
            "  background: transparent;",
            "  border: none;",
            "  border-radius: 0;",
            "  transition: border-color 0.2s ease, background 0.2s ease;",
            "}"
        ]
        lines = lines[:block_start] + new_block + lines[block_end+1:]
        print(f"[OK] 修改点6 (mint-user-card去卡片) 第{block_start+1}行")
        break

# ========== 修改点7: mint-user-card:hover 透明 ==========
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith(".mint-user-card:hover {") and ".mint-collapsed" not in line:
        block_start = i
        block_end = find_block_end(lines, i)
        new_block = [
            ".mint-user-card:hover {",
            "  border-color: transparent;",
            "  background: transparent;",
            "}"
        ]
        lines = lines[:block_start] + new_block + lines[block_end+1:]
        print(f"[OK] 修改点7 (mint-user-card:hover透明) 第{block_start+1}行")
        break

# ========== 修改点8: mint-user-card-active 透明 ==========
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith(".mint-user-card-active {"):
        block_start = i
        block_end = find_block_end(lines, i)
        new_block = [
            ".mint-user-card-active {",
            "  border-color: transparent;",
            "  background: transparent;",
            "}"
        ]
        lines = lines[:block_start] + new_block + lines[block_end+1:]
        print(f"[OK] 修改点8 (mint-user-card-active透明) 第{block_start+1}行")
        break

# ========== 保存 ==========
with open(file_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n=== 完成！最终文件总行数: {len(lines)} ===")
