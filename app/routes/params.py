from flask import abort, request


def int_arg(name, default, minimum=None, maximum=None):
    """Integer query parameter, 400 if it isn't a number or is out of range."""
    raw = request.args.get(name)
    if raw in (None, ""):
        return default

    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"'{name}' must be a number")

    if minimum is not None and value < minimum:
        abort(400, description=f"'{name}' must be at least {minimum}")
    if maximum is not None and value > maximum:
        abort(400, description=f"'{name}' must be at most {maximum}")

    return value


def text_arg(name):
    """Text query parameter, stripped; None when missing or empty."""
    return (request.args.get(name) or "").strip() or None


def choice_arg(name, default, choices):
    """A query parameter that must be one of `choices`, 400 otherwise."""
    value = text_arg(name) or default
    if value not in choices:
        abort(400, description=f"'{name}' must be one of: {', '.join(choices)}")
    return value


def page_args():
    return int_arg("page", 1, minimum=1), int_arg("per_page", 20, minimum=1, maximum=100)
