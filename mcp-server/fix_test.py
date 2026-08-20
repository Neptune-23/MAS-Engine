import os
import sys

project_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
test_file = os.path.join(project_path, "test_main.py")

# 读取文件
with open(test_file, "r") as f:
    content = f.read()

# 将失败的断言改为正确（2+2==4）
new_content = content.replace("assert add(2, 2) == 5", "assert add(2, 2) == 4")

# 写回
with open(test_file, "w") as f:
    f.write(new_content)

print("[Fixer] 已修复 test_main.py 中的断言")