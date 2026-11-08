import argparse, copy, json
from dataclasses import asdict
from pathlib import Path
from scripts.alice_memory.dialogue_language import DialogueLanguage
from scripts.alice_memory.language import LocalLanguage
from scripts.alice_memory.runtime_store import atomic_json
p=argparse.ArgumentParser();p.add_argument('--checkpoint');p.add_argument('--output',type=Path);p.add_argument('--endpoint');p.add_argument('--model');a=p.parse_args()
r=json.loads(Path('bin/AliceMemory/dialogue-real-v2/report.json').read_text(encoding='utf-8'));t=r['turns'][-1];context=copy.deepcopy(t['receipt']['result']['data']['evidence']);context['history']=[]
a.output.mkdir(parents=True,exist_ok=False);result={'passed':False,'fresh_sensory_inference':False,'scope':'same acquired text and owner evidence, current topic without unrelated generated history'}
try:
 result['proposal']=asdict(DialogueLanguage(LocalLanguage(a.endpoint,a.model,timeout=90,wait_seconds=0,ram_fraction=.9)).express(t['question'],context));result['context']=context;result['passed']=True
finally: atomic_json(a.output/'report.json',result)
print(json.dumps({'passed':result['passed'],'text':result.get('proposal',{}).get('text')},ensure_ascii=True))
