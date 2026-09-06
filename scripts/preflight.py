"""Check external access without printing credentials or provider error bodies."""
import os
import sys
from langsmith import Client
from openai import OpenAI
from chinook_support import db  # loads the local .env


def main():
    failures = []
    if not os.getenv('OPENAI_API_KEY'):
        failures.append('OPENAI_API_KEY is missing')
    else:
        try:
            OpenAI(timeout=15, max_retries=0).chat.completions.create(
                model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
                messages=[{'role': 'user', 'content': 'Reply READY.'}], max_completion_tokens=10)
            print('OpenAI model: reachable')
        except Exception as exc:
            failures.append(f'OpenAI: {type(exc).__name__} (HTTP {getattr(exc, "status_code", "unknown")})')
    if not os.getenv('LANGSMITH_API_KEY'):
        failures.append('LANGSMITH_API_KEY is missing')
    else:
        try:
            client = Client(timeout_ms=15000)
            list(client.list_projects(limit=1))
            list(client.list_annotation_queues(limit=1))
            print('LangSmith projects and annotation queues: reachable')
        except Exception as exc:
            failures.append(f'LangSmith: {type(exc).__name__}; check workspace/key/endpoint')
    for failure in failures:
        print('NEEDS SETUP:', failure)
    if failures:
        print('Add working keys to .env. No keys or provider error bodies have been printed.')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
