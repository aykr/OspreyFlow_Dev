"""Plant one fault (old -> new, exactly once) in a file, run one pytest selection, restore."""
import subprocess, sys, pathlib
path, old, new, sel = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = pathlib.Path(path); text = p.read_text()
assert text.count(old) == 1, f"plant site not unique: {text.count(old)}"
p.write_text(text.replace(old, new, 1))
try:
    r = subprocess.run([sys.argv[5], *sel.split()], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "ERROR")) or " passed" in l or " failed" in l]
    print("\n".join(lines[-8:]))
finally:
    p.write_text(text)
