import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Local refund task-tampering pilot')
    parser.add_argument('command',choices=['run','report','plot'])
    parser.add_argument('run_dir',type=Path)
    args=parser.parse_args()
    if args.command=='run':
        from .experiment import run
        print(json.dumps(run(args.run_dir),indent=2))
    elif args.command=='report':
        from .analysis import analyze
        print(json.dumps(analyze(args.run_dir)['summary'],indent=2))
    else:
        from .plot import plot
        plot(args.run_dir)


if __name__=='__main__':
    main()
