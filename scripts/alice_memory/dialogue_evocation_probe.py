"""Evaluate pretrained expression against captured synthetic evocation contexts."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .dialogue_language import DialogueLanguage, validate_context
from .language import AdmissionDeferred, LocalLanguage
from .interaction_inbox import atomic as atomic_json


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    raw = checkpoint.read_bytes()
    if len(raw) > 65536:
        raise ValueError('Evocation expression fixture exceeds its byte budget.')
    fixture = json.loads(raw)
    if not isinstance(fixture, dict) or set(fixture) != {'format', 'kind', 'cases'} or fixture['format'] != 1 or fixture['kind'] != 'synthetic_dialogue_evocation_fixture' or not isinstance(fixture['cases'], list) or not 1 <= len(fixture['cases']) <= 4:
        raise ValueError('Invalid evocation expression fixture.')
    for case in fixture['cases']:
        if not isinstance(case, dict) or set(case) != {'question', 'context'}:
            raise ValueError('Invalid expression case.')
        validate_context(case['context'], case['question'])
    checksum = hashlib.sha256(raw).hexdigest()
    language = DialogueLanguage(LocalLanguage(endpoint, model, timeout=90, wait_seconds=0, ram_fraction=.9))
    report = {'protocol_completed': False, 'quality_approved': False, 'manual_review_required': True,
              'synthetic_contexts': True, 'fresh_encoder_inference': False, 'live_sensors': False,
              'new_model_downloaded': False, 'source_sha256': checksum, 'model': model, 'cases': []}
    for case in fixture['cases']:
        item = {'question': case['question'], 'completed': False}
        try:
            item.update(proposal=asdict(language.express(case['question'], case['context'])), completed=True)
        except AdmissionDeferred as error:
            item.update(deferred=True, error=str(error))
            report['cases'].append(item)
            break  # No repeated attempts under the same resource observation.
        except (OSError, RuntimeError, ValueError) as error:
            item['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        report['cases'].append(item)
        atomic_json(output / 'report.json', report)
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('Expression changed its captured evocation source.')
    report.update(protocol_completed=len(report['cases']) == len(fixture['cases']) and all(item['completed'] for item in report['cases']),
                  source_unchanged=True, completed=sum(item['completed'] for item in report['cases']),
                  total=len(fixture['cases']))
    atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True, help='Captured synthetic JSON fixture, not neural weights.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.endpoint, args.model)
    print({key: result[key] for key in ('completed', 'total', 'protocol_completed', 'quality_approved')})


if __name__ == '__main__':
    main()
