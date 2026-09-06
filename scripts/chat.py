"""Terminal fallback for rehearsal; the presentation uses LangSmith Studio."""
import argparse
import json
import uuid

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from chinook_support import db
from chinook_support.agent import build_agent
from chinook_support.tools import CustomerContext


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--customer', type=int, required=True)
    parser.add_argument('--variant', choices=['baseline', 'improved'], default='improved')
    args = parser.parse_args()
    db.initialize()
    db.require_customer(args.customer)
    graph = build_agent(variant=args.variant, checkpointer=InMemorySaver())
    context = CustomerContext(args.customer)
    config = {'configurable': {'thread_id': str(uuid.uuid4())}, 'metadata': {'variant': args.variant}}
    print('Local demo; identity fixed for this session. /quit to exit. Review actions as the operator.')
    while True:
        try:
            message = input('Customer> ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message == '/quit':
            break
        if not message:
            continue
        result = graph.invoke({'messages': [{'role': 'user', 'content': message}]}, config=config, context=context)
        while result.get('__interrupt__'):
            actions = result['__interrupt__'][0].value['action_requests']
            decisions = []
            for action in actions:
                print(json.dumps(action, indent=2))
                approved = input('Reviewer: type approve to create this demo ticket; anything else rejects> ').strip() == 'approve'
                decisions.append({'type': 'approve'} if approved else {'type': 'reject', 'message': 'Do not create the ticket or retry.'})
            result = graph.invoke(Command(resume={'decisions': decisions}), config=config, context=context)
        message = result['messages'][-1]
        if isinstance(message, AIMessage):
            print('Support>', message.text)


if __name__ == '__main__':
    main()
