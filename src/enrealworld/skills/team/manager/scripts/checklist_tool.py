#!/usr/bin/env python3
"""Request runner submission of a Markdown checklist and read its receipt."""
import argparse
import json
import sys
from pathlib import Path


def write_request(context_path, *, ref=None, error=None):
    context = json.loads(context_path.read_text())
    payload = {'request_id': context['request_id']}
    payload['error' if error is not None else 'path'] = error if error is not None else ref
    path = Path(context['request_path'])
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False)+'\n')
    temporary.replace(path)
    return {'status': 'requested', 'request_id': context['request_id']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checklist', type=Path, default=Path('/role/checklist.md'))
    sub = parser.add_subparsers(dest='action', required=True)
    submit = sub.add_parser('submit')
    submit.add_argument('--context', type=Path, help='runner context; defaults next to the checklist')
    receipt = sub.add_parser('receipt')
    receipt.add_argument('--path', type=Path, default=Path('/coordination/requirement-receipt.json'))
    receipt.add_argument('--request-id', required=True, help='accept a receipt only for this submission')
    args = parser.parse_args(argv)
    try:
        if args.action == 'receipt':
            result = json.loads(args.path.read_text())
            if result.get('request_id') != args.request_id:
                print(json.dumps(dict(status='pending', error='Receipt is for another request.'), ensure_ascii=False))
                return 1
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get('status') == 'accepted' else 1
        context = args.context or args.checklist.parent/'requirement-request-context.json'
        root = context.parent.resolve()
        source = args.checklist.resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError('checklist file is missing or outside the Manager role directory')
        source.read_text(encoding='utf-8')
        result = write_request(context, ref=str(source.relative_to(root)))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        if args.action == 'submit':
            try:
                context = args.context or args.checklist.parent/'requirement-request-context.json'
                write_request(context, error=str(exc))
            except (ValueError, TypeError, KeyError, OSError):
                pass
        print(json.dumps(dict(status='error', error=str(exc)), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
