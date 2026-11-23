"""Check by AST that every product module naming a CORE content route is an allowlisted builder that seals (ADR-195 B2).

This is the second check; it cannot see a body rewritten after the seal, so the
per-builder capture tests stay the primary gate. The scanner folds string
concatenations and f-string text, and reads relative, absolute and query-carrying
paths as httpx would request them; a route built only from values it cannot
resolve, such as a function argument, stays invisible to it.
"""

import ast
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = "runtimes/llama.cpp/tools/server/server.cpp"
ROUTE_COMMIT = "5c8854fd88319125125dc4b836c98b1b215b0f23"
# Every ctx_http.get/post/del registration in ROUTE_SOURCE at ROUTE_COMMIT, in source
# order and without duplicates (the router-mode block, the main table at lines
# 263-304, the stream routes and the optional cors-proxy and tools routes).
# register_gcp_compat only aliases these handlers under an operator-set path.
PINNED_ROUTES = (
    ("post", "/models"),
    ("post", "/models/load"),
    ("post", "/models/unload"),
    ("get", "/models/sse"),
    ("del", "/models"),
    ("get", "/health"),
    ("get", "/v1/health"),
    ("get", "/metrics"),
    ("get", "/props"),
    ("post", "/props"),
    ("get", "/models"),
    ("get", "/v1/models"),
    ("post", "/completion"),
    ("post", "/completions"),
    ("post", "/v1/completions"),
    ("post", "/chat/completions"),
    ("post", "/v1/chat/completions"),
    ("post", "/v1/chat/completions/control"),
    ("post", "/v1/responses"),
    ("post", "/responses"),
    ("post", "/v1/audio/transcriptions"),
    ("post", "/audio/transcriptions"),
    ("post", "/v1/messages"),
    ("post", "/infill"),
    ("post", "/embedding"),
    ("post", "/embeddings"),
    ("post", "/v1/embeddings"),
    ("post", "/rerank"),
    ("post", "/reranking"),
    ("post", "/v1/rerank"),
    ("post", "/v1/reranking"),
    ("post", "/v1/systemone"),
    ("post", "/tokenize"),
    ("post", "/detokenize"),
    ("post", "/apply-template"),
    ("post", "/chat/completions/input_tokens"),
    ("post", "/v1/chat/completions/input_tokens"),
    ("post", "/responses/input_tokens"),
    ("post", "/v1/responses/input_tokens"),
    ("post", "/v1/messages/count_tokens"),
    ("get", "/lora-adapters"),
    ("post", "/lora-adapters"),
    ("get", "/slots"),
    ("post", "/slots/:id_slot"),
    ("get", "/v1/stream"),
    ("post", "/v1/streams/lookup"),
    ("del", "/v1/stream"),
    ("get", "/cors-proxy"),
    ("post", "/cors-proxy"),
    ("get", "/tools"),
    ("post", "/tools"),
)
# Routes that render a chat template, or act on a chat-completion session (control).
TEMPLATE_RENDERING = frozenset(
    {
        "/chat/completions",
        "/v1/chat/completions",
        "/v1/chat/completions/control",
        "/v1/responses",
        "/responses",
        "/v1/audio/transcriptions",
        "/audio/transcriptions",
        "/v1/messages",
        "/v1/systemone",
        "/apply-template",
        "/chat/completions/input_tokens",
        "/v1/chat/completions/input_tokens",
        "/responses/input_tokens",
        "/v1/responses/input_tokens",
        "/v1/messages/count_tokens",
    }
)
# Routes that tokenize caller text with special-token parsing.
TEXT_TOKENIZING = frozenset(
    {
        "/completion",
        "/completions",
        "/v1/completions",
        "/infill",
        "/embedding",
        "/embeddings",
        "/v1/embeddings",
        "/rerank",
        "/reranking",
        "/v1/rerank",
        "/v1/reranking",
        "/tokenize",
    }
)
NON_CONTENT = frozenset(
    {
        "/models",
        "/models/load",
        "/models/unload",
        "/models/sse",
        "/health",
        "/v1/health",
        "/metrics",
        "/props",
        "/v1/models",
        "/detokenize",
        "/lora-adapters",
        "/slots",
        "/slots/:id_slot",
        "/v1/stream",
        "/v1/streams/lookup",
        "/cors-proxy",
        "/tools",
    }
)
GUARDED = TEMPLATE_RENDERING | TEXT_TOKENIZING
# Outbound builders: the content-route literals each holds and its seal_payload calls.
BUILDERS = {
    "apps/api/services/llama_gateway.py": (
        {"/apply-template": 1, "/tokenize": 1, "/v1/chat/completions": 2},
        3,
    ),
    "apps/harness/inference.py": ({"/v1/chat/completions": 2}, 2),
    "apps/harness/summarizer.py": ({"/v1/chat/completions": 1}, 1),
    "src/infrastructure/inference/structured_profile.py": (
        {"/v1/chat/completions": 1},
        1,
    ),
    "src/infrastructure/inference/structured_excerpt_adapter.py": (
        {"/v1/chat/completions": 1},
        1,
    ),
    "src/infrastructure/inference/core_vision_chat.py": (
        {"/v1/chat/completions": 1},
        1,
    ),
    "apps/api/services/vision_ocr.py": ({"/v1/chat/completions": 1}, 1),
}
# Inbound routes this product serves itself; they never call CORE directly.
INBOUND = {
    "apps/harness/browser.py": {"/v1/chat/completions": 2},
    "apps/api/routes/chat.py": {"/completions": 1},
}
# A function that posts a template-rendering route but receives an already sealed body.
SEALED_BY_CALLER = {
    ("src/infrastructure/inference/structured_profile.py", "_complete_native"): (
        "complete"
    ),
}
# The /tokenize body is the rendered template output, which must keep its real control tokens.
UNSEALED_BY_DESIGN = {("apps/api/services/llama_gateway.py", "/tokenize")}


def derive_routes(source):
    """Return every (method, path) registration in a llama.cpp server.cpp, in order, without duplicates."""
    routes = []
    for match in re.finditer(r'ctx_http\.(get|post|del)\s*\(\s*"([^"]+)"', source):
        if (match.group(1), match.group(2)) not in routes:
            routes.append((match.group(1), match.group(2)))
    return tuple(routes)


# Marks a dynamic part (a name, call or f-string field) inside a folded string expression.
HOLE = "\x00"
# HTTP client methods whose URL argument may be a bare relative path; every guarded route is a POST.
URL_ARGUMENT = {"post": 0, "request": 1, "stream": 1, "build_request": 1}


def folded(node):
    """Return the static text of a string expression, with HOLE for each dynamic part, or None."""
    if isinstance(node, ast.Constant):
        return node.value if type(node.value) is str else None
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else HOLE
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = folded(node.left), folded(node.right)
        if left is None and right is None:
            return None
        return (HOLE if left is None else left) + (HOLE if right is None else right)
    return None


def route_of(value, url_argument=False):
    """Return the guarded route a folded string names, or None.

    Each static segment is reduced to the path httpx would request: an absolute URL
    keeps its path (a guarded suffix counts, for a base URL with a prefix), the query
    and fragment are dropped, and a relative path is joined at the root. A bare word
    such as "tokenize" counts only as the URL argument of an HTTP call.
    """
    for segment in value.split(HOLE):
        absolute = "://" in segment
        if absolute:
            rest = segment.split("://", 1)[1]
            if "/" not in rest:
                continue
            segment = rest[rest.index("/") :]
        path = re.split(r"[?#]", segment, maxsplit=1)[0]
        if not path.startswith("/"):
            if "/" not in path and not url_argument:
                continue
            path = "/" + path
        if path in GUARDED:
            return path
        if absolute:
            suffixes = [route for route in GUARDED if path.endswith(route)]
            if suffixes:
                return max(suffixes, key=len)
    return None


def scan_source(source):
    """Return (routes, seal calls, per-function marks, tree) for one module's source."""
    tree = ast.parse(source)
    routes, seals, functions, per_function = Counter(), 0, {}, {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(function):
                functions.setdefault(id(node), function.name)

    def mark(node, route):
        """Count one guarded route against the function that holds node."""
        routes[route] += 1
        per_function.setdefault(functions.get(id(node)), set()).add(route)

    assigned, inner = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                assigned.setdefault(node.target.id, []).append(node.value)
        if id(node) not in inner:
            value = folded(node)
            if value is not None:
                # Count each maximal string expression once, never its parts.
                inner.update(id(child) for child in ast.walk(node) if child is not node)
                route = route_of(value)
                if route is not None:
                    mark(node, route)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "seal_payload"
        ):
            seals += 1
            per_function.setdefault(functions.get(id(node)), set()).add("SEAL")
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in URL_ARGUMENT
        ):
            continue
        index = URL_ARGUMENT[node.func.attr]
        if len(node.args) > index:
            argument = node.args[index]
        else:
            argument = next(
                (word.value for word in node.keywords if word.arg == "url"), None
            )
        if isinstance(argument, ast.Name):
            candidates = assigned.get(argument.id, [])
        else:
            candidates = [] if argument is None else [argument]
        for candidate in candidates:
            value = folded(candidate)
            # A value the string pass already counted is not counted again.
            if value is None or route_of(value) is not None:
                continue
            route = route_of(value, url_argument=True)
            if route is not None:
                mark(node, route)
    return dict(routes), seals, per_function, tree


def scan(root=ROOT):
    """Map every Python file under src/ and apps/ to the guarded routes and seal calls it holds."""
    found = {}
    for path in sorted([*root.glob("src/**/*.py"), *root.glob("apps/**/*.py")]):
        routes, seals, per_function, tree = scan_source(
            path.read_text(encoding="utf-8")
        )
        if routes or seals:
            found[path.relative_to(root).as_posix()] = (
                routes,
                seals,
                per_function,
                tree,
            )
    return found


def test_vendored_route_table_is_pinned_to_the_llama_cpp_commit():
    assert (ROOT / "configs/llama-cpp-commit.txt").read_text().strip() == ROUTE_COMMIT
    paths = {path for _, path in PINNED_ROUTES}
    assert len(PINNED_ROUTES) == 51 and len(paths) == 44
    assert TEMPLATE_RENDERING | TEXT_TOKENIZING | NON_CONTENT == paths
    assert not TEMPLATE_RENDERING & TEXT_TOKENIZING
    assert not GUARDED & NON_CONTENT
    for route in (
        "/chat/completions/input_tokens",
        "/responses/input_tokens",
        "/v1/responses/input_tokens",
        "/v1/chat/completions/control",
        "/infill",
        "/apply-template",
        "/tokenize",
        "/v1/audio/transcriptions",
        "/embedding",
        "/embeddings",
        "/v1/embeddings",
        "/rerank",
        "/reranking",
        "/v1/rerank",
        "/v1/reranking",
    ):
        assert route in GUARDED


def test_vendored_route_table_matches_the_runtime_source_when_present():
    source = ROOT / ROUTE_SOURCE
    if not source.is_file():
        pytest.skip("runtimes/llama.cpp is not checked out here")
    assert derive_routes(source.read_text(encoding="utf-8")) == PINNED_ROUTES


def test_content_routes_appear_only_in_allowlisted_builders_that_seal():
    found = scan()
    holders = {path for path, (routes, _, _, _) in found.items() if routes}
    assert holders == set(BUILDERS) | set(INBOUND)
    for path, (routes, seals) in BUILDERS.items():
        assert found[path][0] == routes, path
        assert found[path][1] == seals, path
        imports = {
            (node.module, alias.name)
            for node in ast.walk(found[path][3])
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert (
            "src.infrastructure.inference.core_request_seal",
            "seal_payload",
        ) in imports, path
    for path, routes in INBOUND.items():
        assert found[path][0] == routes and found[path][1] == 0, path


def test_every_function_posting_a_template_route_seals_its_body():
    found = scan()
    for path in BUILDERS:
        per_function = found[path][2]
        for name, marks in per_function.items():
            routes = marks - {"SEAL"}
            if not routes:
                continue
            unsealed = {
                route for route in routes if (path, route) not in UNSEALED_BY_DESIGN
            }
            if not unsealed or "SEAL" in marks:
                continue
            sealer = SEALED_BY_CALLER.get((path, name))
            assert sealer is not None, (path, name)
            assert "SEAL" in per_function[sealer], (path, sealer)
            assert unsealed <= TEMPLATE_RENDERING


def test_grounded_precheck_seals_without_naming_a_route():
    found = scan()
    routes, seals, _, _ = found["apps/api/services/grounded.py"]
    assert routes == {} and seals == 1


# Forms that reach a guarded CORE route through httpx without spelling it as an exact constant.
ROGUE = {
    "relative": (
        "async def send(client, messages):\n"
        '    return await client.post("v1/chat/completions", json=dict(messages=messages))\n',
        "/v1/chat/completions",
    ),
    "query": ('CHAT = "/v1/chat/completions?x=1"\n', "/v1/chat/completions"),
    "fragment": ('TOKENIZE = "/tokenize#count"\n', "/tokenize"),
    "concatenated": ('CHAT = "/v1/chat/" + "completions"\n', "/v1/chat/completions"),
    "base_plus_route": (
        'def url(base):\n    return base + "/tokenize?x=1"\n',
        "/tokenize",
    ),
    "f_string": (
        'def url(base, value):\n    return f"{base}/v1/embeddings?x={value}"\n',
        "/v1/embeddings",
    ),
    "absolute_url": (
        'CHAT = "http://127.0.0.1:8080/v1/chat/completions?stream=1"\n',
        "/v1/chat/completions",
    ),
    "prefixed_base_url": (
        'CHAT = "http://127.0.0.1:8080/proxy/v1/chat/completions"\n',
        "/v1/chat/completions",
    ),
    "bare_post": (
        'async def send(client):\n    await client.post("embeddings", json={})\n',
        "/embeddings",
    ),
    "bare_url_keyword": (
        'async def send(client):\n    await client.post(url="completion", json={})\n',
        "/completion",
    ),
    "bare_request": (
        'async def send(client):\n    await client.request("POST", "rerank", json={})\n',
        "/rerank",
    ),
    "bare_stream": (
        "async def send(client):\n"
        '    async with client.stream("POST", "infill", json={}) as response:\n'
        "        return response\n",
        "/infill",
    ),
    "bare_f_string": (
        'async def send(client, base):\n    await client.post(f"{base}tokenize", json={})\n',
        "/tokenize",
    ),
    "bare_name": (
        'ROUTE = "tokenize"\n\n\nasync def send(client):\n'
        "    await client.post(ROUTE, json={})\n",
        "/tokenize",
    ),
}
BENIGN = (
    'PATH = "configs/embedding-selected.json"\n',
    'PREFIX = "embeddings/"\n',
    'ROLES = {"embedding": 1, "tokenize": 2}\n',
    'def role(row):\n    return row.get("embedding")\n',
    'NOTE = "Post to /v1/chat/completions with care."\n',
    'OWN = "/api/v1/embeddings"\n',
    "async def send(client, path):\n    await client.post(path, json={})\n",
)


@pytest.mark.parametrize("case", sorted(ROGUE))
def test_scanner_finds_routes_that_are_not_exact_constants(case):
    source, route = ROGUE[case]
    routes, seals, _, _ = scan_source(source)
    assert routes == {route: 1} and seals == 0


@pytest.mark.parametrize("source", BENIGN)
def test_scanner_ignores_text_that_does_not_name_a_core_route(source):
    assert scan_source(source)[0] == {}


def test_a_new_unsealed_builder_becomes_an_unallowlisted_holder(tmp_path):
    rogue = tmp_path / "apps" / "api" / "services" / "unsealed_probe.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text(ROGUE["relative"][0], encoding="utf-8")
    found = scan(tmp_path)
    assert set(found) == {"apps/api/services/unsealed_probe.py"}
    assert found["apps/api/services/unsealed_probe.py"][:2] == (
        {"/v1/chat/completions": 1},
        0,
    )


# Every recorded digest of a CORE request, with the label it must carry (ADR-195 section 3).
DIGEST_LABELS = (
    (
        "src/application/services/grounded_extract.py",
        "    prompt_sha256: str",
        "pre-seal",
    ),
    (
        "src/application/services/grounded_extract.py",
        "        digest = hashlib.sha256(canonical(dict(messages=messages))).hexdigest()",
        "pre-seal",
    ),
    (
        "src/application/services/grounded_extract.py",
        "            prompt_sha256=provenance.prompt_sha256,",
        "pre-seal",
    ),
    (
        "src/application/services/profile_prompts.py",
        "            digest = hashlib.sha256(canonical(dict(messages=messages))).hexdigest()",
        "pre-seal",
    ),
    (
        "apps/harness/summarizer.py",
        '        payload, _ = seal_payload(payload, "summarizer")',
        "pre-seal",
    ),
    (
        "src/infrastructure/inference/structured_excerpt_adapter.py",
        "    prompt_sha256: str",
        "pre-seal",
    ),
    (
        "src/infrastructure/inference/structured_excerpt_adapter.py",
        "    native_request_sha256: str",
        "post-seal",
    ),
    (
        "src/infrastructure/inference/structured_profile.py",
        "    request_sha256: str",
        "post-seal",
    ),
)


@pytest.mark.parametrize("path,anchor,label", DIGEST_LABELS)
def test_recorded_digests_are_labelled_pre_or_post_seal(path, anchor, label):
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    (index,) = [number for number, line in enumerate(lines) if line == anchor]
    comments = [
        line.strip().lower()
        for line in lines[max(0, index - 3) : index]
        if line.strip().startswith("#")
    ]
    assert any(label in line for line in comments), (path, anchor)
