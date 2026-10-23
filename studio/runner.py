"""Detached, single-training-job runner. Never executes browser-provided commands."""
import fcntl, os, signal, subprocess, sys, time
from pathlib import Path
from core import atomic_json, read_json, now, process_identity

def run(job_dir):
    job_dir = Path(job_dir).resolve()
    data = read_json(job_dir/'job.json')
    lock = (job_dir.parent/'training.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        data.update(status='failed',error='Another Studio training process owns the GPU lock',finished=now())
        atomic_json(job_dir/'job.json',data); return
    data.update(status='loading',pid=os.getpid(),identity=process_identity(os.getpid()),started=now())
    atomic_json(job_dir/'job.json',data)
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUNBUFFERED='1',TOKENIZERS_PARALLELISM='false')
    stopped = False
    try:
        with (job_dir/'train.log').open('ab',buffering=0) as log:
            p = subprocess.Popen([str(Path(data['toolkit'])/'venv/bin/python'), 'run.py',str(job_dir/'config.yaml')],
                    cwd=data['toolkit'],env=env,stdout=log,stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,start_new_session=True)
            data.update(child_pid=p.pid)
            atomic_json(job_dir/'job.json',data)
            while p.poll() is None:
                if (job_dir/'stop.request').exists() and not stopped:
                    # Only this runner's own child process group receives SIGINT.
                    os.killpg(p.pid, signal.SIGINT)
                    stopped = True
                    data.update(status='stopping'); atomic_json(job_dir/'job.json',data)
                time.sleep(1)
        final = Path(data['output'])/data['name']/(data['name']+'.safetensors')
        data.update(exit_code=p.returncode,finished=now(),
                    status='stopped' if stopped else ('completed' if p.returncode==0 and final.exists() else 'failed'))
    except Exception as e:
        data.update(status='failed',error=type(e).__name__+': '+str(e),finished=now())
    atomic_json(job_dir/'job.json',data)

if __name__=='__main__': run(sys.argv[1])
