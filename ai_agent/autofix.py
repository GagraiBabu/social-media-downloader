import json
import time
import requests
from .agent import agent
from .config import settings
from .diagnostics import diagnostics
from .github_tools import github
from .render_tools import render

def _json(text):
    text=text.strip()
    if text.startswith('```'):
        lines=text.splitlines(); text='\n'.join(lines[1:-1])
    try: return json.loads(text)
    except json.JSONDecodeError as exc: raise RuntimeError('AI returned invalid JSON') from exc

def _safe(path):
    return isinstance(path,str) and path and not path.startswith('/') and '..' not in path.split('/') and not path.lower().endswith(('.env','.pem','.key'))

def run_autofix(request, auto_apply=True):
    if settings.GITHUB_BRANCH == 'main': raise RuntimeError('AI agent refuses to modify main')
    report=diagnostics.run(); tree=github.list_files('')
    paths=[x.get('path') for x in tree if isinstance(x,dict) and x.get('path')]
    plan=_json(agent._call_ai('''You are the planning stage of a self-healing backend agent. Return ONLY JSON: {"summary":"...","files":["path"],"steps":["..."]}. Select only existing source files needed for the request, max 8. Never select secrets, .env, credentials, deployment keys, or main.''', json.dumps({'request':request,'diagnostics':report,'repository_tree':paths},indent=2)))
    files=plan.get('files')
    if not isinstance(files,list) or len(files)>8 or not all(_safe(p) and p in paths for p in files): raise RuntimeError('AI produced an unsafe file plan')
    sources={p:github.read_file(p) for p in files}
    patch=_json(agent._call_ai('''You are the implementation stage of a self-healing backend agent. Return ONLY JSON: {"summary":"...","changes":[{"path":"existing path","content":"complete file content","reason":"..."}]}. Modify only SOURCE_FILES. Return complete replacement contents, preserve unrelated behavior, do not modify secrets/credentials, do not add dependencies unless essential. Writable branch is ai-agent-dev.''', json.dumps({'request':request,'plan':plan,'SOURCE_FILES':{p:{sha':d['sha'],'content':d['content']} for p,d in sources.items()}},indent=2)))