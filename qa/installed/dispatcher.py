"""Run inside the newly installed stock Hermes engine. No inference or sessions."""
import json
import time
import importlib.util
# Stock Hermes moved these public entry points into sibling modules. Import the
# installed version's implementation; never replace discovery or dispatch.
if importlib.util.find_spec('tools.mcp_tool_discovery'):
    from tools.mcp_tool_discovery import discover_mcp_tools
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
else:
    from tools.mcp_tool import discover_mcp_tools, shutdown_mcp_servers
from model_tools import handle_function_call
from tools.registry import registry


def decode(raw):
    # Stock Hermes renders an MCP call as {"result": "<text>"} (plus optional
    # structuredContent/_meta); older shapes may still carry MCP content blocks.
    value = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(value, dict) and not value.get('error') and not value.get('isError'), value
    if isinstance(value.get('structuredContent'), dict):
        value = value['structuredContent']
    elif 'result' in value:
        value = value['result']
        value = json.loads(value) if isinstance(value, str) else value
    if isinstance(value, dict) and 'content' in value:
        value = json.loads(next(x['text'] for x in value['content'] if x.get('type') == 'text'))
    assert isinstance(value, dict) and not value.get('error'), value
    return value


try:
    names, matches = [], []
    for attempt in range(12):
        discover_mcp_tools(allowed_mcp_names=['wizard'])
        names = [n for n in registry.get_all_tool_names() if n.startswith('mcp__wizard__')]
        matches = [n for n in names if n.endswith('__search_web')]
        if len(matches) == 1:
            break
        time.sleep(5)
    assert len(matches) == 1, 'Search not uniquely discovered through configured wizard gateway'
    tool = matches[0]
    status_tool = tool.removesuffix('search_web') + 'search_status'
    status = decode(handle_function_call(status_tool, {}, enabled_tools=names))
    assert status['policy']['mode'] == 'free-only', status
    results = None
    for attempt in range(3):
        results = decode(handle_function_call(tool, {'q': 'Python programming language official documentation'}, enabled_tools=names))
        if results.get('results'):
            break
        time.sleep(3)
    assert results and results.get('results'), results
    assert all(r.get('url', '').startswith(('https://', 'http://')) for r in results['results'])
    print('NATIVE_WEB_DISPATCHER=' + json.dumps({'kind': 'stock-Hermes dispatcher; no model', 'tool': tool, 'status': status, 'search': results}))
finally:
    shutdown_mcp_servers()
