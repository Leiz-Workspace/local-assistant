"""Run pairing and request-bridge JavaScript against isolated browser API doubles."""

import logging
import shutil
import subprocess

import pytest

LOGGER = logging.getLogger(__name__)


def test_fetch_bridge_blocks_remote_and_removes_authorization():
    """Execute the shipped bridge and verify CSRF tagging and cross-origin refusal."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser-script validation")
    script = r"""
    const fs = require('fs');
    const vm = require('vm');
    const assert = require('assert');
    const calls = [];
    const navigation = [];
    const context = {
      URL, Headers, Request,
      console: {info() {}, warn() {}},
      window: {
        location: {origin: 'http://127.0.0.1:7090', href: 'http://127.0.0.1:7090/', replace(path) {navigation.push(path);}},
        fetch(input, options) { calls.push({input, options}); return Promise.resolve({ok: true, status: input === '/expired' ? 401 : 200}); }
      }
    };
    vm.runInNewContext(fs.readFileSync('apps/harness/static/bridge.js', 'utf8'), context);
    (async () => {
      await context.window.fetch('/props', {headers: {Authorization: 'Bearer private'}});
      assert.equal(calls.length, 1);
      assert.equal(calls[0].options.headers.get('Authorization'), null);
      assert.equal(calls[0].options.headers.get('X-Harness-UI'), '1');
      assert.equal(calls[0].options.redirect, 'error');
      await context.window.fetch('/v1/chat/completions', {body: JSON.stringify({messages: [], tools: [{type: 'function'}], tool_choice: 'auto'}), method: 'POST'});
      const chat = JSON.parse(calls[1].options.body);
      assert.equal(chat.tools, undefined);
      assert.equal(chat.tool_choice, undefined);
      await assert.rejects(context.window.fetch('https://example.com/collect'));
      assert.equal(calls.length, 2);
      await context.window.fetch('/expired');
      assert.equal(navigation[0], '/pair/');
    })().catch(() => { process.exitCode = 1; });
    """
    result = subprocess.run(
        [node, "-e", script], capture_output=True, timeout=5, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    LOGGER.info("test_shipped_browser_bridge_verified")


def test_pairing_scrubs_fragment_before_exchange():
    """Execute pairing and verify secret-free browser history before the one-use exchange."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser-script validation")
    script = r"""
    const fs = require('fs');
    const vm = require('vm');
    const assert = require('assert');
    const observed = [];
    const context = {
      console: {info() {}, warn() {}},
      document: {getElementById() { return {}; }},
      window: {
        location: {hash: '#one-use-code', replace(path) {observed.push(path);}},
        history: {replaceState(state, title, path) {observed.push(path);}}
      },
      fetch(path, options) {
        assert.equal(observed[0], '/pair/');
        assert.equal(path, '/ui/pairings');
        assert.equal(JSON.parse(options.body).code, 'one-use-code');
        return Promise.resolve({ok: true});
      }
    };
    vm.runInNewContext(fs.readFileSync('apps/harness/static/pair.js', 'utf8'), context);
    setImmediate(() => { assert.equal(observed[1], '/aevra-app/'); });
    """
    result = subprocess.run(
        [node, "-e", script], capture_output=True, timeout=5, check=False
    )
    assert result.returncode == 0, result.stderr.decode()


def test_aevra_brand_script_changes_chrome_only():
    """Execute the shipped branding script and verify idempotent title/logo updates without message-tree rewrites."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser-script validation")
    script = r"""
    const fs = require('fs'), vm = require('vm'), assert = require('assert');
    const nodes = new Map();
    const title = {};
    const document = {
      title: 'Search · llama.cpp', readyState: 'complete',
      getElementById(id) {return nodes.get(id);},
      querySelector(selector) {assert.equal(selector, 'title'); return title;},
      createElement(tag) {return {tag, children: [], setAttribute(k, v) {this[k] = v;}, append(...children) {this.children.push(...children);}};},
      body: {prepend(node) {nodes.set(node.id, node);}}
    };
    let observer;
    const context = {document, console: {info() {}}, MutationObserver: class {
      constructor(callback) {observer = callback;}
      observe(target) {assert.equal(target, title);}
    }};
    vm.runInNewContext(fs.readFileSync('apps/harness/static/brand.js', 'utf8'), context);
    assert.equal(document.title, 'Search · Aevra');
    const brand = nodes.get('aevra-brand');
    assert.equal(brand.children[0].src, '/aevra/brand/logo.svg');
    assert.equal(brand.children[1].textContent, 'Aevra');
    document.title = 'My task';
    observer();
    assert.equal(document.title, 'My task · Aevra');
    observer();
    assert.equal(document.title, 'My task · Aevra');
    assert.equal(nodes.size, 1);
    """
    result = subprocess.run(
        [node, "-e", script], capture_output=True, timeout=5, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    LOGGER.info("test_aevra_browser_branding_verified")
