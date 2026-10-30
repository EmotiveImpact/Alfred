"""ALFRED's tool gate for the sealed Hermes box (docs/HERMES_BOX.md).

Hermes calls ``pre_tool_call`` before every tool. This hook asks ALFRED about the exact tool
and arguments and blocks the call unless ALFRED says yes. Hermes ignores a hook that raises,
so this one never raises: any failure is a block.
"""

BLOCKED = 'ALFRED refused this tool.'


def _check(tool_name=None, args=None, **_):
    try:
        import alfred_box_link
        decision = alfred_box_link.check_tool(tool_name or '', args)
        if decision.get('allow') is True:
            return None
        message = decision.get('message')
        return {'action': 'block', 'message': message if isinstance(message, str) and message else BLOCKED}
    except BaseException:
        return {'action': 'block', 'message': BLOCKED}


def register(ctx):
    ctx.register_hook('pre_tool_call', _check)
