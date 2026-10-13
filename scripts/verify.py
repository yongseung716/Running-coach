"""Run verification suites; 0=all passed, 1=failed, 2=blocked. No package installation."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env['PYTHONPATH'] = str(root/'apps/api')
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': []}


def check(name, command, missing=None):
    if missing:
        print(f'BLOCKED {name}: {", ".join(missing)}', flush=True)
        report['checks'].append({'name':name, 'status':'blocked', 'missing':missing})
        return
    print(f'RUN {name}', flush=True)
    result = subprocess.run(command, cwd=root, env=env)
    report['checks'].append({'name':name, 'status':'passed' if result.returncode==0 else 'failed',
                             'exit_code':result.returncode})


def missing_python(*packages):
    return [name for name in packages if importlib.util.find_spec(name) is None]


def missing_node(*packages):
    return [name for name in packages if not (root/'node_modules'/name/'package.json').is_file()]


for pattern, name, packages in [
    ('test_analysis.py','GPX analysis',('lxml',)),
    ('test_coaching.py','Rule coaching',()),
    ('test_security.py','JWT/password/storage security',('jwt','fastapi','pydantic_settings')),
    ('test_api.py','API lifecycle',('sqlalchemy','email_validator','fastapi','jwt','pydantic_settings')),
]:
    check(name,[sys.executable,'-m','unittest','discover','-s','apps/api/tests','-p',pattern,'-v'],missing_python(*packages))
check('Python source syntax',[sys.executable,'-m','compileall','-q','apps/api','scripts'])
check('Service worker syntax',['node','--check','apps/web/public/sw.js'],[] if shutil.which('node') else ['node'])
check('PostgreSQL/RLS',['npm','run','test:rls'],missing_node('@electric-sql/pglite'))
check('TypeScript',['npm','run','typecheck'],missing_node('typescript','next','react'))
check('Next build',['npm','run','build'],missing_node('next','react','@tailwindcss/postcss'))
check('Browser lifecycle',['npm','run','test:web'],missing_python('sqlalchemy','email_validator')+missing_node('@playwright/test','next','react'))
output = root/'docs/verification-results.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(f'Report: {output}',flush=True)
statuses = [item['status'] for item in report['checks']]
raise SystemExit(1 if 'failed' in statuses else 2 if 'blocked' in statuses else 0)
