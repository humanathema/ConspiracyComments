# src/reassemble_explorer.py
import re
import os
import sys

def reassemble(output_path="scratch/index_reassembled.html"):
    print("=== Reassembling Explorer ===")
    
    # 1. Read components
    part1_path = "src/templates/explorer/part1_head_body.html"
    part2_path = "src/templates/explorer/part2_chartjs.html"
    app_logic_path = "src/templates/explorer/app_logic.js"
    
    if not (os.path.exists(part1_path) and os.path.exists(part2_path) and os.path.exists(app_logic_path)):
        print("❌ Error: One or more component files are missing!")
        sys.exit(1)
        
    with open(part1_path, "r", encoding="utf-8") as f:
        part1 = f.read()
    with open(part2_path, "r", encoding="utf-8") as f:
        part2 = f.read()
    with open(app_logic_path, "r", encoding="utf-8") as f:
        app_logic = f.read()

    # 2. Extract DATA block from original index_gce.html
    # If a custom data file exists, use that. Otherwise, extract from scratch/index_gce.html.
    data_js_path = "scratch/explorer_data.js"
    if os.path.exists(data_js_path):
        print(f"  Loading static DATA from {data_js_path}...")
        with open(data_js_path, "r", encoding="utf-8") as f:
            data_block = f.read().strip()
    else:
        print("  Extracting static DATA from scratch/index_gce.html...")
        gce_html_path = "scratch/index_gce.html"
        if not os.path.exists(gce_html_path):
            print(f"❌ Error: {gce_html_path} not found. Cannot extract DATA!")
            sys.exit(1)
            
        with open(gce_html_path, "r", encoding="utf-8") as f:
            gce_content = f.read()
            
        matches = list(re.finditer(r"<script[^>]*>(.*?)</script>", gce_content, re.DOTALL))
        if len(matches) < 2:
            print("❌ Error: Could not find script blocks in original file!")
            sys.exit(1)
            
        last_body = matches[-1].group(1)
        data_match = re.search(r"const DATA\s*=\s*\{", last_body)
        if not data_match:
            print("❌ Error: Could not locate 'const DATA =' inside script block!")
            sys.exit(1)
            
        func_matches = list(re.finditer(r"function\s+[a-zA-Z0-9_]+\s*\(", last_body))
        first_func_start = None
        for f_m in func_matches:
            if f_m.start() > data_match.end():
                first_func_start = f_m.start()
                break
                
        if first_func_start is None:
            print("❌ Error: Could not find any functions after DATA!")
            sys.exit(1)
            
        prefix = last_body[:first_func_start]
        last_semicolon = prefix.rfind("};")
        if last_semicolon != -1:
            data_end_idx = last_semicolon + 2
        else:
            data_end_idx = prefix.rfind("}") + 1
            
        data_block = last_body[:data_end_idx].strip()
        
        # Save DATA block to cache
        with open(data_js_path, "w", encoding="utf-8") as f:
            f.write(data_block)
        print(f"  Cached DATA block to {data_js_path} ({len(data_block)} bytes)")

    # 3. Assemble
    # part1 + part2 + <script> + DATA + \n\n + app_logic + </script> + \n\n + </body></html>
    # Wait, let's verify if part2 already contains closing script tag or needs one.
    # In index_gce.html:
    # block 0 (Chart.js) was: matches[-2].group(0) which is <script>...</script>
    # then matches[-1] starts with <script> and ends with </script>.
    # So we write:
    # part1_head_body + part2_chartjs + "\n<script>\n" + DATA + "\n\n" + app_logic + "\n</script>\n</body>\n</html>"
    
    # Wait, let's check how part1 ends and what follows matches[-2].
    # Matches[-2] is the Chart.js script tag.
    # Let's inspect index_gce.html to see if there are closing body tags or if they are in last block.
    # Our split script did:
    # part1_content = content[:chartjs_start]
    # part2_content = matches[-2].group(0)
    # So part1 has everything before the Chart.js script tag.
    # Chart.js is matches[-2].group(0) (which includes <script>...</script>).
    # Then we have the final script block: matches[-1].group(0) (which is <script>DATA + app_logic</script>).
    # Then we have </body></html>.
    # Let's see: we want the final file to have:
    # part1_content + part2_content + "\n<script>\n" + data_block + "\n\n" + app_logic + "\n</script>\n\n</body>\n</html>"
    # Let's make sure this matches. We can verify with a test build!
    
    assembled = part1 + part2 + "\n<script>\n" + data_block + "\n\n" + app_logic + "\n</script>\n\n</body>\n</html>"
    
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(assembled)
        
    print(f"🎉 Successfully reassembled explorer to {output_path}!")
    print(f"  Final Size: {len(assembled):,} bytes")
    return assembled

if __name__ == "__main__":
    out_file = "scratch/index_reassembled.html"
    if len(sys.argv) > 1:
        out_file = sys.argv[1]
    reassemble(out_file)
