import os

# 1. 修复项目目录下的 Cargo.toml
cargo_toml_path = r"D:\test_broken_rust\Cargo.toml"
try:
    with open(cargo_toml_path, "w") as f:
        f.write("""[package]
name = "test_broken_rust"
version = "0.1.0"
edition = "2021"

[dependencies]
non_existent_crate = "0.1.0"
""")
    print("[OK] Cargo.toml fixed")
except Exception as e:
    print(f"[ERROR] Cargo.toml fix failed: {e}")

# 2. 修复全局 ~/.cargo/config.toml
cargo_conf_path = os.path.expanduser("~/.cargo/config.toml")
os.makedirs(os.path.dirname(cargo_conf_path), exist_ok=True)
try:
    with open(cargo_conf_path, "w") as f:
        f.write("""[source.crates-io]
replace-with = "tuna"
[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
""")
    print("[OK] Cargo config fixed")
except Exception as e:
    print(f"[ERROR] Cargo config fix failed: {e}")
