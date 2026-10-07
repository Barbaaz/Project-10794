"""
robots.txt rules with wildcards, as Google reads them (RFC 9309): `*` matches anything, `$` ends
the path, the longest matching rule wins and Allow wins a tie. Python's urllib.robotparser has
no wildcards, so a rule like "Disallow: *query=*" (Techinn) or "Disallow: /catalogo/*" read as
allowed there (found 2026-10-03). The group used is the one naming our user agent, else "*".
"""
import re
from urllib.parse import urlsplit


class RobotsRules:
    def __init__(self, rules=()):
        self.rules = list(rules)        # [(allow: bool, pattern text, compiled regex)]

    @classmethod
    def parse(cls, text, user_agent):
        """The rules for `user_agent` from a robots.txt's text."""
        groups, agents, rules, in_rules = [], [], [], False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if in_rules:                    # a new group starts
                    groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(value.lower())
            elif field in ("allow", "disallow"):
                in_rules = True
                if value:                       # "Disallow:" (empty) allows everything
                    rules.append((field == "allow", value))
        if agents:
            groups.append((agents, rules))

        # a group names us by our product token, the User-Agent before the "/" (RFC 9309)
        ours = user_agent.split("/")[0].strip().lower()
        named = [r for a, r in groups if ours in a]
        chosen = named or [r for a, r in groups if "*" in a]
        return cls((allow, pattern, _regex(pattern)) for rules in chosen for allow, pattern in rules)

    def allowed(self, url):
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best = None                     # (length, allow)
        for allow, pattern, regex in self.rules:
            if regex.match(path):
                key = (len(pattern), allow)
                if best is None or key > best:
                    best = key
        return best is None or best[1]


def _regex(pattern):
    """A robots.txt path pattern as a regex matched from the start of the path."""
    end = pattern.endswith("$")
    body = pattern[:-1] if end else pattern
    return re.compile("".join(".*" if c == "*" else re.escape(c) for c in body) + ("$" if end else ""))
