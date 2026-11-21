"""Validate role wire values before they enter scheduling or publication."""

def validate(result, role, phase):
    if not isinstance(result, dict):
        raise ValueError('result must be a JSON object')
    if result.get('status') not in ('passed', 'failed'):
        raise ValueError('status must be passed or failed')
    for key in ('evidence', 'messages'):
        if not isinstance(result.get(key, []), list):
            raise ValueError(key+' must be a list')
    if any(not isinstance(ref, str) for ref in result.get('evidence', [])):
        raise ValueError('evidence must contain relative path strings')
    for i, message in enumerate(result.get('messages', [])):
        if not isinstance(message, dict) or message.get('to') not in ('manager','engineer','researcher'):
            raise ValueError(f'messages[{i}] requires object with to=manager/engineer/researcher')
        if not isinstance(message.get('refs', []), list) or any(not isinstance(r,str) for r in message.get('refs', [])):
            raise ValueError(f'messages[{i}].refs must be path strings')
    return result
