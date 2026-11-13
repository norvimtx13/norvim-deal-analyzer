"""Run each Streamlit regression in its own clean Python process."""
import ast
from pathlib import Path
import subprocess
import sys

path=Path(__file__).with_name('test_workspace.py')
tree=ast.parse(path.read_text())
cases=[f'{cls.name}.{method.name}' for cls in tree.body if isinstance(cls,ast.ClassDef) for method in cls.body if isinstance(method,ast.FunctionDef) and method.name.startswith('test_')]
failed=[]
for case in cases:
    result=subprocess.run([sys.executable,str(path),case],capture_output=True,text=True,timeout=60)
    print(('PASS' if result.returncode==0 else 'FAIL')+' '+case,flush=True)
    if result.returncode:
        failed.append(case)
        print((result.stdout+result.stderr)[-6000:],file=sys.stderr,flush=True)
print(f'{len(cases)-len(failed)}/{len(cases)} isolated checks passed',flush=True)
raise SystemExit(bool(failed))
