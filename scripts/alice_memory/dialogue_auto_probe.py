"""Actual typed text and encoder trigger recall from a learned name, without a selected report."""
import argparse
from pathlib import Path

from .dialogue_probe import run


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--name', default='hami')
    parser.add_argument('--native-models', type=Path, default=root / 'bin/AliceMemory/EmbeddingGemma2/914f7f89142e33e77833254d9c9b90c3cef7303b')
    parser.add_argument('--native-python', type=Path, default=root / 'bin/AliceMemory/perception-venv/Scripts/python.exe')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.endpoint, args.model, args.native_models,
                 args.native_python, automatic_name=args.name)
    print({'integration_passed': result['integration_passed'], 'explicit_topic_selected': False,
           'free_text_semantics_verified': False})


if __name__ == '__main__':
    main()
