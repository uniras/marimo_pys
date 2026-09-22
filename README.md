# marimo-pys

Run Python in the browser with [PyScript](https://pyscript.net/) and display the result in a [marimo](https://marimo.io/) notebook. Use a simple iframe for rendering, or enable an [AnyWidget](https://anywidget.dev/) to **synchronize values in both directions** between marimo and PyScript.

**Two modes:**

- `widget=False` (default) returns `marimo.Html` containing a PyScript iframe.
- `widget=True` returns a `PysWidget` with outgoing `data` and incoming `received` dictionaries. Wrap it with `mo.ui.anywidget()` to use the received values reactively in marimo.

> **Scope: value synchronization, not an event-delivery system.** The widget is designed to reflect the *latest values* on either side. It does not queue every change, guarantee that every intermediate update is observed, or provide event ordering, acknowledgments, or retries. For history, include it in your data (for example, a list with sequence numbers). For stricter event semantics, implement an application-specific protocol or messaging path.

Each iframe has its own browser-side Python runtime. PyScript does not share Python imports, globals, or memory with marimo.

## Installation

```bash
pip install marimo marimo-pys anywidget traitlets
```

Or with uv:

```bash
uv add marimo marimo-pys anywidget traitlets
```

The current implementation imports `marimo`, `anywidget`, and `traitlets`, so ensure they are installed. PyScript assets are loaded in the browser from `pyscript.net`.

## Quick start: render HTML

```python
from marimo_pys import run_pyscript

async def hello(js, data):
    heading = js.document.createElement("h1")
    heading.textContent = f"Hello, {data['name']}!"
    js.document.body.appendChild(heading)

run_pyscript(hello, data={"name": "marimo"})
```

`run_pyscript()` extracts the function's source and runs it in the browser as `await hello(js, data)`. `js` provides access to JavaScript/browser APIs, and `data` is the initial dictionary supplied from marimo. A Python return value is **not** automatically rendered: update the DOM or render through another browser-side mechanism.

Callable inputs must be `async def` functions with source available to `inspect.getsource()`. Import modules needed in PyScript **inside the function**: marimo-side globals, imports, and closures are not copied into the browser runtime.

## Synchronize values with `widget=True`

Create the widget once, then update its values without deliberately restarting its iframe:

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

The `data={"count": 50}` argument supplies the **initial value** to the PyScript function. The example above displays only that initial value; to display later changes, add a `message` listener as in the complete example below.

### marimo → PyScript: `set_data()`

```python
pys_raw.set_data({"count": 75})
```

`set_data()` replaces the outgoing `data` dictionary. After the widget's built-in ready signal, its JavaScript view sends the latest dictionary to the iframe via `postMessage()`. A PyScript message listener is needed to apply the update to your application. `set_data()` does **not** change the initial `data` argument already passed to the running function, merge individual keys, await a reply, or guarantee delivery of every intermediate value.

### PyScript → marimo: `received`

PyScript can post a dictionary-shaped update to the parent window:

```python
# Inside the PyScript function:
from pyscript import ffi

js.window.parent.postMessage(
    ffi.to_js({
        "channel": "marimo-pys",
        "type": "set",
        "payload": {"count": 76},
    }),
    "*",
)
```

The widget stores the last valid `payload` in `received`. From a marimo cell, read the reactive AnyWidget wrapper:

```python
pys.received.get("count")
```

`received` is **replaced**, not merged or appended. It does not automatically update outgoing `data`; if you want both sides to reflect the same value, connect the incoming value to your marimo state and use `set_data()` for the other direction.

### Message shapes

The built-in protocol uses the browser's `postMessage()`:

**marimo → PyScript**

```javascript
{
  channel: "marimo-pys",
  type: "update",
  payload: { count: 75 }
}
```

**PyScript → marimo**

```javascript
{
  channel: "marimo-pys",
  type: "set",
  payload: { count: 76 }
}
```

Both payloads should be JSON-compatible objects/dictionaries. Inbound `set` payloads must be an object, not a bare number or array. The widget verifies that incoming messages come from **its own iframe**, so separate widget instances do not accept one another's messages.

## Example: synchronize a marimo slider and PyScript buttons

Moving the marimo slider changes the displayed number inside PyScript. Clicking **−** or **+** inside the PyScript iframe changes the slider. Use **three separate marimo cells**. The separation lets marimo rerun synchronization cells without recreating the PyScript iframe.

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

The initial count comes from the function's `data` argument. Later `update` messages are handled by `receive_update()`. Button clicks send the current count back as a `set` payload.

**Cell 2 — create the slider and send current state to PyScript:**

```python
count = get_count()

# Also handles state changes originating outside the slider.
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

**Cell 3 — reflect PyScript values in marimo state:**

```python
incoming = pys.received.get("count")
if type(incoming) is int and 0 <= incoming <= 100:
    set_count(incoming)
```

`mo.state()` drives the slider's value. Do not assign directly to `slider.value`. Keep the widget-construction cell independent of calls to `get_count()`; otherwise a state change can rerun that cell and recreate the iframe. The slider cell may rerun to reflect the latest value, but the `PysWidget` instance remains the same.

This is a **current-value synchronization example**, not a guarantee that every rapid slider movement or button click is individually delivered or processed.

## Initial values, readiness, and long-running functions

For async callable inputs, marimo-pys sends the built-in string signal `"marimo-pys:ready"` **before invoking your function**. This tells the widget's JavaScript view to send the latest outgoing `data`; it does **not** mean your own Python message listener has been registered.

Use the callable's `data` argument for initial values:

```python
async def my_app(js, data):
    current_value = data["value"]  # Initial value
    # Register your listener for later updates here.
    # A long-running async loop may follow.
```

This is intentional for long-running applications such as games: an `async` function may keep running indefinitely, even if it regularly `await`s and yields control. Sending ready **after** `await my_app(...)` would mean the signal might never be sent.

An update sent before your application listener is registered can be missed. If it matters to receive the *current* value after your own initialization, you can use the existing `set` message format for an **application-level initialization signal**. Register the listener first, then send, for example:

```python
# Inside your PyScript function, after registering the message listener:
js.window.parent.postMessage(
    ffi.to_js({
        "channel": "marimo-pys",
        "type": "set",
        "payload": {"app_ready": True},
    }),
    "*",
)
```

A marimo cell can watch `pys.received.get("app_ready")` and call `pys_raw.set_data(...)` with its current values. This uses the **same** `postMessage` path; it does not require a separate transport. Treat this as an application convention rather than a built-in delivery guarantee.

For a **raw source string**, marimo-pys does not insert its own ready signal. If you need subsequent `set_data()` updates in that mode, register your `message` listener and then send `js.window.parent.postMessage("marimo-pys:ready", "*")` yourself.

## What value synchronization does—and does not—provide

The built-in `data` and `received` traits contain the latest dictionaries, **not a log of changes**. Several updates may be coalesced or overwritten before a reactive marimo cell processes them. Repeated identical values may not trigger a new observable change. Do not use this mechanism as a reliable event queue for commands such as *fire once*, *record every click*, or *process every frame*.

If you need a history **as data**, you can include a list and an increasing ID in a dictionary and send the updated list:

```python
history = [
    {"id": 1, "kind": "click"},
    {"id": 2, "kind": "click"},
]
pys_raw.set_data({"history": history})
```

The receiving application can track processed IDs and read the history from the most recently received value. This is an application-level technique, not a guarantee that the list itself will be delivered: you must manage retention, size, and recovery if that matters. For exact event ordering, acknowledgments, retries, or other strict delivery requirements, implement your own protocol or communication path.

## Other usage

### Choose MicroPython or Pyodide

`pys_type="mpy"` (MicroPython) is the default. Use `"py"` for Pyodide or `"py-game"` for PyScript's game-oriented script type:

```python
run_pyscript(hello, data={"name": "Pyodide"}, pys_type="py")
```

Package availability depends on the selected browser-side interpreter; consult the [PyScript documentation](https://docs.pyscript.net/).

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

Use `config` for PyScript settings, or `add_script`, `add_module`, and `add_css` for additional resources *inside the iframe*:

```python
run_pyscript(
    hello,
    data={"name": "NumPy"},
    pys_type="py",
    config={"packages": ["numpy"]},
    add_css=["https://example.com/styles.css"],
)
```

Replace example URLs with real, trusted resources and use Python packages compatible with the selected runtime.

### Raw Python source

`code` can be a Python source string instead of an async callable. It is executed as provided; marimo-pys does not automatically invoke a function or add a ready signal for raw source:

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

### Insert raw HTML

`add_dangerous_html` inserts HTML into the iframe body **without sanitizing it**:

```python
run_pyscript(
    hello,
    data={"name": "marimo"},
    add_dangerous_html='<div id="app"></div>',
)
```

Only insert HTML and load external resources that you trust.

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
| `width`, `height` | Iframe dimensions; defaults: `"100%"`, `"200px"`. |
| `body_style` | CSS declarations for the iframe document's body. |
| `iframe_style` | CSS declarations for the iframe element. |
| `iframe_sandbox` | Iframe sandbox tokens; default: `"allow-scripts"`. |
| `config` | PyScript configuration dictionary. |
| `data` | JSON-serializable initial dictionary; also the widget's initial outgoing value. |
| `add_script` | URLs of extra classic JavaScript scripts. |
| `add_module` | URLs of extra JavaScript modules. |
| `add_css` | URLs of extra CSS stylesheets. |
| `add_dangerous_html` | Unsanitized HTML inserted into the iframe body. |
| `terminal` | Add the PyScript `terminal` attribute; default: `False`. |
| `pys_version` | PyScript release to load; default: `"2026.7.3"`. |
| `pys_type` | `"mpy"` (default), `"py"`, or `"py-game"`. |
| `widget` | Return `PysWidget` when `True`; otherwise `marimo.Html` (default). |

### `PysWidget`

`run_pyscript(..., widget=True)` returns this AnyWidget subclass.

| Member | Meaning |
| --- | --- |
| `set_data(mapping)` | Replace the outgoing dictionary with a new value. |
| `data` | Latest outgoing dictionary. |
| `received` | Latest valid dictionary received from PyScript. |
| `srcdoc` | HTML document loaded into the iframe. |
| `width`, `height`, `iframe_style`, `iframe_sandbox` | Iframe attributes read when the view is rendered. |

`set_data()` replaces the whole dictionary; it does not merge keys or wait for an acknowledgment. Multiple changes before the built-in ready signal are represented by the latest outgoing value. Changes to `srcdoc` or iframe creation-time attributes do not automatically rebuild an existing view.

## How it works

1. For async callables, extract and dedent the source and append an invocation using the JSON-decoded initial `data`.
2. Encode the Python source as Base64 and generate a PyScript HTML document.
3. Load the document in an iframe using `srcdoc`.
4. In widget mode, synchronize `data` and `received` dictionaries via AnyWidget traits and per-iframe `postMessage()`.
5. Check `event.source` against the specific iframe window so different widgets do not consume one another's messages. The implementation accepts messages from the parent origin or `"null"` for sandboxed iframe messages.

PyScript's relative URL resolution inside `about:srcdoc` requires a compatibility workaround: marimo-pys patches the iframe's `URL` constructor to use the selected PyScript release URL as a fallback for empty or `about:` base URLs. The workaround was written for PyScript `2026.7.3`; recheck it when upgrading PyScript.

## Limitations and security

- **Separate runtimes:** PyScript does not inherit marimo's imports, globals, or closures. The browser needs access to PyScript and any additional resources.
- **Source extraction:** `inspect.getsource()` must be able to retrieve callable source. Decorated and dynamically created functions are not supported as documented callable inputs.
- **Values, not event delivery:** Use JSON-compatible dictionaries for `data`, `set_data()`, and incoming `set` payloads. Intermediate changes and event delivery are not guaranteed.
- **Widget lifecycle:** Recreating the Widget/view also recreates its iframe and PyScript runtime. Keep its construction cell independent of changing state.
- **Sandboxed storage:** With the default `iframe_sandbox="allow-scripts"`, the iframe has an opaque origin; browser storage APIs such as IndexedDB may be denied and produce a console `SecurityError` even when your code runs.
- **`allow-same-origin` changes isolation:** `iframe_sandbox="allow-scripts allow-same-origin"` may enable origin-dependent APIs, but a `srcdoc` iframe then shares its parent's origin. Scripts may access the parent page and potentially remove the sandbox. Only consider this with code you fully trust; see [MDN's iframe security warning](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe#sandbox).
- **Trust boundary:** `add_dangerous_html` is not sanitized and external scripts run in the iframe. The message protocol is for exchanging data, **not** a security boundary.

## Links

- [GitHub repository](https://github.com/uniras/marimo_pys)
- [PyPI package](https://pypi.org/project/marimo-pys/)
- [marimo documentation](https://docs.marimo.io/)
- [PyScript documentation](https://docs.pyscript.net/)
- [AnyWidget documentation](https://anywidget.dev/)
