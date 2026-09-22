# marimo-pys

Run Python in the browser with [PyScript](https://pyscript.net/) and embed the result in a [marimo](https://marimo.io/) notebook. Use a simple HTML iframe for one-way rendering, or opt into an [AnyWidget](https://anywidget.dev/) for two-way messages between marimo and PyScript.

**Two display modes:**

- `widget=False` (default): returns `marimo.Html` containing a PyScript iframe.
- `widget=True`: returns a `PysWidget` with synchronized `data` (marimo → PyScript) and `received` (PyScript → marimo) dictionaries.

Each iframe runs its own browser-side Python environment. The Python code running in marimo and the Python code running in PyScript do **not** share imports, globals, or memory.

## Install

```bash
pip install marimo marimo-pys anywidget traitlets
```

Or with uv:

```bash
uv add marimo marimo-pys anywidget traitlets
```

The current package imports `marimo`, `anywidget`, and `traitlets`, so make sure all three are installed. PyScript itself is loaded in the browser from `pyscript.net`; the initial page load requires access to those assets.

## Quick start: render HTML

```python
from marimo_pys import run_pyscript

async def hello(js, data):
    heading = js.document.createElement("h1")
    heading.textContent = f"Hello, {data['name']}!"
    js.document.body.appendChild(heading)

run_pyscript(hello, data={"name": "marimo"})
```

`run_pyscript()` extracts the source of `hello`, loads it into PyScript, and calls it in the browser as `await hello(js, data)`. Here, `js` provides access to JavaScript and browser APIs, while `data` is a JSON-decoded Python dictionary. The function's *return value* is not automatically displayed: create DOM elements or use another browser-side rendering API.

Callable inputs must be defined with `async def` and have source code available to `inspect.getsource()`. Put imports needed by the browser runtime **inside** the callable; its enclosing Python globals and closure are not transferred.

## Two-way communication with `widget=True`

For a live widget, request `widget=True` and wrap the returned `PysWidget` with marimo's `mo.ui.anywidget()`:

```python
import marimo as mo
from marimo_pys import run_pyscript

async def show_count(js, data):
    label = js.document.createElement("div")
    label.textContent = str(data["count"])
    js.document.body.appendChild(label)

pys_raw = run_pyscript(
    show_count,
    widget=True,
    data={"count": 50},
)
pys = mo.ui.anywidget(pys_raw)
pys
```

The initial `data={"count": 50}` is passed as the callable's `data` argument. Later calls to `pys_raw.set_data(...)` update the widget's synchronized `data` trait and send an **`update` message** to the running iframe. They do not reassign the callable's original `data` argument or intentionally reload the iframe; your PyScript code must register a message listener if it needs to handle subsequent updates.

### Message protocol

The widget uses browser `postMessage` with the following message shapes:

**marimo → PyScript:**

```javascript
{
  channel: "marimo-pys",
  type: "update",
  payload: { count: 75 }
}
```

**PyScript → marimo:**

```javascript
{
  channel: "marimo-pys",
  type: "set",
  payload: { count: 76 }
}
```

The payload sent to marimo must be a JSON-serializable **object** (a Python dictionary), not a bare number or array. Incoming `set` payloads replace the widget's `received` dictionary; they are not merged with previous payloads. `data` and `received` are separate channels, not one automatically synchronized shared object.

The widget also listens for a string readiness signal, `"marimo-pys:ready"`. For callable inputs, the generated script emits it automatically **just before calling** the async function. Keep the initial value in the callable's `data` argument: the first `update` message may arrive before a listener created inside that function is registered. Once the listener is registered, later updates are received normally. When `code` is a raw source string, no readiness signal is added automatically; see [Raw Python source](#raw-python-source).

### Complete example: a marimo slider and PyScript buttons

The following example lets you move a marimo slider to update the number inside PyScript, or click PyScript's **−** and **+** buttons to update the marimo slider. Put the three Python snippets into **three separate marimo cells**, in order. Keeping widget construction out of cells that read `get_count()` avoids recreating the iframe on every state update.

**Cell 1 — create state and the widget once:**

```python
import marimo as mo
from marimo_pys import run_pyscript

async def counter_ui(js, data):
    import json
    from pyscript import ffi

    count = int(data.get("count", 50))

    minus = js.document.createElement("button")
    minus.textContent = "−"
    label = js.document.createElement("span")
    label.style.margin = "0 1rem"
    plus = js.document.createElement("button")
    plus.textContent = "+"

    def display_count():
        label.textContent = str(count)

    def change_by(amount):
        nonlocal count
        count = max(0, min(100, count + amount))
        display_count()
        js.window.parent.postMessage(
            ffi.to_js({
                "channel": "marimo-pys",
                "type": "set",
                "payload": {"count": count},
            }),
            "*",
        )

    def receive_update(event):
        nonlocal count
        try:
            message = json.loads(js.JSON.stringify(event.data))
        except (TypeError, ValueError):
            return
        if not isinstance(message, dict):
            return
        if message.get("channel") != "marimo-pys" or message.get("type") != "update":
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        incoming = payload.get("count")
        if type(incoming) is int and 0 <= incoming <= 100:
            count = incoming
            display_count()

    minus.addEventListener("click", ffi.create_proxy(lambda event: change_by(-1)))
    plus.addEventListener("click", ffi.create_proxy(lambda event: change_by(1)))
    js.window.addEventListener("message", ffi.create_proxy(receive_update))

    display_count()
    js.document.body.appendChild(minus)
    js.document.body.appendChild(label)
    js.document.body.appendChild(plus)

get_count, set_count = mo.state(50)

pys_raw = run_pyscript(
    counter_ui,
    widget=True,
    data={"count": 50},
    height="100px",
)
pys = mo.ui.anywidget(pys_raw)
pys
```

**Cell 2 — show the slider and send state changes to the existing iframe:**

```python
count = get_count()

# Also handles state changes coming from outside the slider.
if pys_raw.data.get("count") != count:
    pys_raw.set_data({"count": count})

def on_slider_change(value):
    pys_raw.set_data({"count": value})
    set_count(value)

slider = mo.ui.slider(
    start=0,
    stop=100,
    step=1,
    value=count,
    on_change=on_slider_change,
    label="Count",
)
slider
```

**Cell 3 — reflect messages from the PyScript buttons in marimo state:**

```python
incoming = pys.received.get("count")
if type(incoming) is int and 0 <= incoming <= 100:
    set_count(incoming)
```

Use `pys.received` in a reactive marimo cell to process incoming messages. The underlying `PysWidget` also exposes a traitlets `received` trait, but the marimo-facing reactive property is a straightforward integration path. This example deliberately separates **initialization**, **marimo → PyScript**, and **PyScript → marimo** to avoid a circular cell dependency or an unnecessary PyScript restart.

For a direct Python-side check without a slider, you can also call:

```python
pys_raw.set_data({"count": 25})
```

Run that statement in a separate cell or a callback; don't put a top-level `set_data()` call in a cell that re-runs for unrelated reasons.

## Other usage

### Choose MicroPython or Pyodide

The default PyScript type is MicroPython (`"mpy"`). Use `"py"` for Pyodide or `"py-game"` for PyScript's game-oriented script type:

```python
run_pyscript(hello, data={"name": "Pyodide"}, pys_type="py")
```

Python package availability differs between MicroPython and Pyodide. See [PyScript's package configuration guide](https://docs.pyscript.net/2026.7.3/user-guide/configuration/).

### Customize the iframe and runtime

```python
run_pyscript(
    hello,
    data={"name": "custom view"},
    width="100%",
    height="320px",
    body_style="background: #20242a; color: white; padding: 12px;",
    iframe_style="border: 1px solid #777; border-radius: 8px;",
    terminal=True,
    pys_version="2026.7.3",
)
```

Use `config` for PyScript settings, and `add_script`, `add_module`, or `add_css` to include additional resources *inside the iframe*:

```python
run_pyscript(
    hello,
    data={"name": "NumPy"},
    pys_type="py",
    config={"packages": ["numpy"]},
    add_css=["https://example.com/styles.css"],
)
```

Replace example URLs with real, trusted resources. Extra Python packages must be compatible with your selected browser-side interpreter.

### Raw Python source

`code` may also be a string instead of an async callable. The source is executed as provided; marimo-pys does **not** automatically invoke a function or add a readiness message in this mode.

```python
run_pyscript(
    """
import js

message = js.document.createElement("p")
message.textContent = "Hello from raw PyScript source!"
js.document.body.appendChild(message)
"""
)
```

If you use raw source with `widget=True` and want `set_data()` updates, register your `message` listener first, then signal readiness yourself:

```python
# Inside the raw PyScript source, after registering the listener:
js.window.parent.postMessage("marimo-pys:ready", "*")
```

### HTML inserted before execution

`add_dangerous_html` inserts the supplied HTML directly into the iframe body, without sanitization. Use only trusted content:

```python
run_pyscript(
    hello,
    data={"name": "marimo"},
    add_dangerous_html='<div id="app"></div>',
)
```

## API reference

### `run_pyscript(...)`

```python
run_pyscript(
    code,
    width="100%",
    height="200px",
    body_style="",
    iframe_style="",
    iframe_sandbox="allow-scripts",
    config=None,
    data=None,
    add_script=None,
    add_module=None,
    add_css=None,
    add_dangerous_html="",
    terminal=False,
    pys_version="2026.7.3",
    pys_type="mpy",
    widget=False,
)
```

| Parameter | Meaning |
| --- | --- |
| `code` | Async callable or raw Python source string. |
| `width`, `height` | iframe dimensions; defaults: `"100%"`, `"200px"`. |
| `body_style` | Extra CSS declarations for the iframe document's `<body>`. |
| `iframe_style` | Extra CSS declarations for the iframe element. |
| `iframe_sandbox` | iframe sandbox tokens; default: `"allow-scripts"`. |
| `config` | PyScript configuration dictionary. |
| `data` | JSON-serializable dictionary passed initially to the callable; also the widget's initial outgoing state. |
| `add_script` | URLs of extra classic JavaScript scripts. |
| `add_module` | URLs of extra JavaScript modules. |
| `add_css` | URLs of extra CSS stylesheets. |
| `add_dangerous_html` | Unsanitized HTML inserted into the iframe body. |
| `terminal` | Add the PyScript `terminal` attribute; default: `False`. |
| `pys_version` | PyScript release to load; default: `"2026.7.3"`. |
| `pys_type` | `"mpy"` (default), `"py"`, or `"py-game"`. |
| `widget` | Return `PysWidget` when `True`; otherwise return `marimo.Html` (default). |

### `PysWidget`

Returned by `run_pyscript(..., widget=True)`.

| Member | Meaning |
| --- | --- |
| `set_data(mapping)` | Replace outgoing `data` with a dictionary; the iframe receives the latest value after its ready signal. |
| `data` | Synchronized outgoing dictionary. |
| `received` | Synchronized dictionary last received from a PyScript `set` message. |
| `srcdoc` | Generated HTML document loaded into the iframe. |
| `width`, `height`, `iframe_style`, `iframe_sandbox` | Synchronized iframe attributes read when its view is rendered. |

`set_data()` replaces the whole dictionary; it does not merge individual keys or await a reply. Multiple updates before readiness are represented by the latest `data` value. When changing `srcdoc` or the iframe's creation-time attributes, do not assume an existing view will automatically rebuild: the view reads them on initial render.

## How it works

1. For async callables, extract and dedent the function source, then append an invocation with the JSON-decoded initial `data`.
2. Encode the Python source as Base64 and include it in a generated PyScript HTML document.
3. Load the HTML through an iframe's `srcdoc` attribute.
4. In widget mode, use AnyWidget's synchronized traits and per-iframe `postMessage` handling to exchange dictionaries without deliberately reloading the iframe for ordinary `data` changes.
5. Check each incoming message's `event.source` against the specific iframe window so multiple widgets do not consume one another's messages. The implementation accepts the parent origin or `"null"` for sandboxed iframe messages.

PyScript's URL resolution inside `about:srcdoc` needs a compatibility workaround: marimo-pys patches the iframe's `URL` constructor to use the selected PyScript release URL as a fallback for empty or `about:` base URLs. This behavior was written for PyScript `2026.7.3`; recheck it when upgrading PyScript.

## Limitations and security

- **Browser-side isolation:** The callable's imports, module globals, and closure are not copied to PyScript. The browser must be able to load PyScript and any extra resources.
- **Source extraction:** `inspect.getsource()` must be able to find the callable's source. Decorated functions and dynamically created functions are not supported as documented callable inputs.
- **JSON messages only:** Use JSON-serializable dictionaries for `data`, `set_data()`, and inbound `set` payloads. The widget stores only the most recent inbound payload; it is not an event queue.
- **Iframe lifecycle:** If marimo recreates the widget/view, its iframe and browser-side Python runtime start again. Keep the widget construction cell independent of rapidly changing state.
- **Sandbox and browser storage:** The default `iframe_sandbox="allow-scripts"` gives the iframe an opaque origin and may block IndexedDB or other storage APIs. You might see a browser-console `SecurityError` even when your PyScript code runs.
- **`allow-same-origin` is a security trade-off:** `iframe_sandbox="allow-scripts allow-same-origin"` may permit origin-dependent APIs, but with `srcdoc` it makes the iframe same-origin with its parent. Scripts may then access the parent page and potentially remove the sandbox. Use this combination only with code you fully trust; see [MDN's iframe security warning](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe#sandbox).
- **Trusted content:** `add_dangerous_html` is not sanitized, and external scripts run inside the iframe. Do not use untrusted HTML or JavaScript. The `postMessage` protocol is a data exchange mechanism, **not** a security boundary.
- **Readiness timing:** For callable inputs, the automatically generated ready message is sent before the user function runs. Use its initial `data` argument for the first render, and install your listener to receive subsequent `update` messages.

## Links

- [GitHub repository](https://github.com/uniras/marimo_pys)
- [PyPI package](https://pypi.org/project/marimo-pys/)
- [marimo documentation](https://docs.marimo.io/)
- [PyScript documentation](https://docs.pyscript.net/2026.7.3/)
- [AnyWidget documentation](https://anywidget.dev/)
