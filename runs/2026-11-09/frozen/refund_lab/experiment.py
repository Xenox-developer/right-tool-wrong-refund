"""Bounded local inference with immutable inputs and durable trial evidence."""
import datetime as dt
import hashlib
import json
import platform
import random
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from .fixtures import load_cases
from .ledger import initialize, execute, snapshot
from .protocol import request_for, parse_proposal

ROOT=Path(__file__).resolve().parents[1]
MODELS=('qwen2.5:7b','qwen3:8b')
MODES=('allowlist','policy')


def save(path,value):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def http(endpoint,payload=None,timeout=30):
    # Deliberately fixed to local Ollama: never pull models or call a paid service.
    body=None if payload is None else json.dumps(payload).encode()
    request=urllib.request.Request('http://127.0.0.1:11434'+endpoint,data=body,
                                   headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        return json.load(response)


def schedule_for(cases):
    rng=random.Random(20261109)
    schedule=[]
    for model in MODELS:
        block=[{'model':model,'case_id':case['id'],'seed':seed}
               for case in cases for seed in (42,43)]
        rng.shuffle(block)
        schedule.extend(block)
    return [{'trial_id':f'trial-{i:03d}',**trial} for i,trial in enumerate(schedule,1)]


def frozen_files():
    return sorted([*ROOT.glob('refund_lab/*.py'),*ROOT.glob('tests/*.py'),
                   ROOT/'data/cases.json',ROOT/'PROTOCOL.md',ROOT/'pyproject.toml'])


def freeze(run_dir,metadata,commit):
    cases=load_cases(ROOT/'data/cases.json')
    run_dir.mkdir(parents=True,exist_ok=False)
    files={}
    for source in frozen_files():
        relative=source.relative_to(ROOT).as_posix()
        target=run_dir/'frozen'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        files[relative]=digest(target)
    schedule=schedule_for(cases)
    save(run_dir/'schedule.json',schedule)
    manifest={'schema':1,'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'tested_commit':commit,'python':platform.python_version(),
              'platform':platform.platform(),'ollama':metadata,
              'files_sha256':files,'schedule_sha256':digest(run_dir/'schedule.json'),
              'max_attempts':50,'wall_seconds':1200,'request_timeout_seconds':90,
              'authorization':'One-off additional 50 local generations authorized in setup chat on 2026-11-09; no paid APIs.'}
    save(run_dir/'manifest.json',manifest)
    return cases,schedule


def replay(run_dir,trial,case,proposal):
    outcomes={}
    for mode in MODES:
        database=run_dir/'ledgers'/f'{trial["trial_id"]}-{mode}.sqlite'
        initialize(database,case['orders'])
        receipt={'status':'not_executed','reason':'no_valid_native_proposal'}
        if proposal is not None:
            receipt=execute(database,mode=mode,principal=case['principal'],
                            scope_order_id=case['scope_order_id'],
                            request_id=trial['trial_id'],**proposal)
        outcomes[mode]={'database':database.relative_to(run_dir).as_posix(),
                        'receipt':receipt,'snapshot':snapshot(database)}
    return outcomes


def run(run_dir,transport=http,commit=None):
    if commit is None:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
        if dirty:
            raise ValueError('Commit tracked changes before measurement')
    installed=transport('/api/tags')['models']
    by_name={model['name']:model for model in installed}
    if any(model not in by_name for model in MODELS):
        raise ValueError('Required local models missing; downloads are not permitted')
    metadata={'version':transport('/api/version'),
              'models':{model:by_name[model] for model in MODELS}}
    cases,schedule=freeze(Path(run_dir),metadata,commit)
    cases={case['id']:case for case in cases}
    started=time.monotonic()
    state={'status':'running','attempts':0,'measured':0,'warmups':0}
    warmed=set()
    active=None
    journal=Path(run_dir)/'attempts.jsonl'

    def generate(kind,payload):
        remaining=1200-(time.monotonic()-started)
        if state['attempts']>=50 or remaining<=0:
            raise RuntimeError('Generation or wall-time budget exhausted')
        state['attempts']+=1
        # Charge before sending; interrupted attempts must never disappear.
        with journal.open('a') as handle:
            handle.write(json.dumps({'attempt':state['attempts'],'kind':kind,
                                    'model':payload['model']})+'\n')
            handle.flush()
        save(Path(run_dir)/'state.json',state)
        before=time.monotonic()
        try:
            response=transport('/api/chat',payload,timeout=min(90,remaining))
            return response,None,time.monotonic()-before
        except Exception as error:
            return None,{'type':type(error).__name__,'message':str(error)},time.monotonic()-before

    try:
        with (Path(run_dir)/'trials.jsonl').open('x') as handle:
            for trial in schedule:
                model=trial['model']
                if model not in warmed:
                    if active:
                        transport('/api/generate',{'model':active,'keep_alive':0})
                    active=model
                    warmup={'model':model,'messages':[{'role':'user','content':'Reply OK.'}],
                            'stream':False,'think':False,'keep_alive':'5m',
                            'options':{'temperature':0,'num_predict':8,'num_ctx':4096}}
                    response,error,elapsed=generate('warmup',warmup)
                    save(Path(run_dir)/f'warmup-{len(warmed)+1}.json',
                         {'request':warmup,'response':response,'error':error,'elapsed_seconds':elapsed})
                    warmed.add(model)
                    state['warmups']+=1
                case=cases[trial['case_id']]
                payload=request_for(model,case,trial['seed'])
                response,error,elapsed=generate('measured',payload)
                proposal,protocol_error=parse_proposal(response)
                record={**trial,'kind':case['kind'],'request':payload,'response':response,
                        'transport_error':error,'protocol_error':protocol_error,
                        'elapsed_seconds':elapsed,'proposal':proposal,
                        'outcomes':replay(Path(run_dir),trial,case,proposal)}
                handle.write(json.dumps(record,sort_keys=True)+'\n')
                handle.flush()
                state['measured']+=1
                save(Path(run_dir)/'state.json',state)
                print(f'{state["measured"]}/48 {model} {case["id"]} '+
                      (protocol_error or 'native tool call'),flush=True)
        state['status']='complete'
    except BaseException as error:
        state['status']='incomplete'
        state['failure']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        state['elapsed_seconds']=time.monotonic()-started
        save(Path(run_dir)/'state.json',state)
        if active:
            try:
                transport('/api/generate',{'model':active,'keep_alive':0})
            except Exception:
                pass
    return state
