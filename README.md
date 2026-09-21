# marimo-pys

Run Python functions as PyScript inside [marimo](https://marimo.io/).

**marimo-pys** is a lightweight Python package that allows you to execute Python functions in the browser using [PyScript](https://pyscript.net/) and display the results as HTML elements in marimo notebooks.

Simply define an asynchronous Python function and pass it to `run_pyscript()`. The package handles source code extraction, HTML generation, PyScript initialization, and iframe embedding.

## Features

* Execute Python functions in the browser using PyScript.
* Display HTML content directly in marimo notebooks.
* Access JavaScript APIs through PyScript's `js` module.
* Pass JSON-serializable data from marimo to PyScript.
* Support MicroPython, Pyodide, and PyScript's `py-game` type.
* Customize iframe dimensions, styles, and sandbox attributes.
* Include additional JavaScript, JavaScript modules, and CSS.
* Configure the PyScript runtime and select its version.
* Work without installing the package by copying its source code into a marimo cell.

## Installation

Install using pip:

```bash
pip install marimo marimo-pys
```

Or add the package to your project using uv:

```bash
uv add marimo marimo-pys
```

If marimo is already installed, you only need to install `marimo-pys`.

### Installation without pip or uv

You can also use the package without installing it.

Copy the contents of [`marimo_pys/__init__.py`](https://github.com/uniras/marimo_pys/blob/main/marimo_pys/__init__.py) into a marimo cell.

This makes `run_pyscript()` available directly in your notebook.

## Quick Start

Import `run_pyscript`, define an asynchronous function, and pass it to `run_pyscript()`.

```python
from marimo_pys import run_pyscript

async def hello(js, data):
    element = js.document.createElement("h1")
    element.textContent = "Hello from PyScript!"
    js.document.body.appendChild(element)

run_pyscript(hello)
```

The function executes inside a PyScript runtime in the browser, and the resulting HTML is displayed in an iframe in your marimo notebook.

The function must be declared using `async def` and accept two arguments:

* `js`: The PyScript JavaScript interoperability module.
* `data`: A Python dictionary containing data passed from marimo.

The function is invoked automatically as:

```python
await hello(js, data)
```

The function's return value is not automatically displayed. Use the DOM APIs or other browser-side rendering mechanisms to produce visible output.

## Usage

### Passing data to PyScript

You can pass data from marimo to your Python function using the `data` argument.

```python
from marimo_pys import run_pyscript

async def greeting(js, data):
    element = js.document.createElement("p")

    element.textContent = (
        f"Hello, {data['name']}! "
        f"You are {data['age']} years old."
    )

    js.document.body.appendChild(element)

run_pyscript(
    greeting,
    data={
        "name": "Alice",
        "age": 25,
    },
)
```

The dictionary is serialized to JSON and reconstructed as a Python object inside the PyScript runtime.

Only JSON-serializable values are supported.

### Importing Python modules

PyScript runs in a separate Python environment from the Python interpreter running marimo.

Therefore, Python modules imported in marimo are not automatically available inside PyScript.

Import the modules you need inside your function.

```python
from marimo_pys import run_pyscript

async def show_result(js, data):
    import math

    result = math.sqrt(data["number"])

    element = js.document.createElement("p")
    element.textContent = f"Square root: {result}"

    js.document.body.appendChild(element)

run_pyscript(
    show_result,
    data={"number": 144},
)
```

Additional packages may need to be configured or installed in the selected PyScript runtime.

### Using Pyodide instead of MicroPython

By default, `run_pyscript()` uses MicroPython.

To use Pyodide, set `pys_type="py"`.

```python
run_pyscript(
    hello,
    pys_type="py",
)
```

Supported PyScript types:

| Type      | Description                          |
| --------- | ------------------------------------ |
| `mpy`     | MicroPython (default)                |
| `py`      | Pyodide                              |
| `py-game` | PyScript's game-oriented script type |

### Customizing the iframe

You can customize the iframe dimensions and CSS styles.

```python
run_pyscript(
    hello,
    width="100%",
    height="400px",
    body_style="background: #222; color: white;",
    iframe_style="border: 1px solid #555; border-radius: 8px;",
)
```

The default iframe dimensions are `100%` width and `200px` height.

### Including external resources

Additional JavaScript files, JavaScript modules, and CSS stylesheets can be included in the generated HTML.

```python
run_pyscript(
    hello,
    add_script=[
        "https://example.com/example.js",
    ],
    add_module=[
        "https://example.com/example-module.js",
    ],
    add_css=[
        "https://example.com/example.css",
    ],
)
```

These resources are loaded inside the generated iframe.

Replace the example URLs with the actual resources required by your application.

### Configuring PyScript

Use the `config` argument to provide a PyScript configuration dictionary.

```python
run_pyscript(
    hello,
    config={
        "packages": [
            "numpy",
        ],
    },
    pys_type="py",
)
```

The configuration is passed to PyScript as JSON.

Available configuration options and package support depend on the selected PyScript runtime.

### Enabling terminal output

Enable PyScript's terminal output using the `terminal` argument.

```python
run_pyscript(
    hello,
    terminal=True,
)
```

### Executing raw Python source code

In addition to Python functions, `run_pyscript()` accepts a string containing Python source code.

```python
run_pyscript(
    """
import js

element = js.document.createElement("p")
element.textContent = "Executed from a source string!"
js.document.body.appendChild(element)
"""
)
```

When a string is provided, it is executed as raw source code without automatic function invocation.

## API Reference

### `run_pyscript()`

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
)
```

**Parameters**

| Parameter            | Description                                                                |
| -------------------- | -------------------------------------------------------------------------- |
| `code`               | An asynchronous Python function or a string containing Python source code. |
| `width`              | Width of the iframe. Default: `"100%"`.                                    |
| `height`             | Height of the iframe. Default: `"200px"`.                                  |
| `body_style`         | Additional CSS styles for the HTML body.                                   |
| `iframe_style`       | Additional CSS styles for the iframe.                                      |
| `iframe_sandbox`     | Sandbox attributes for the iframe. Default: `"allow-scripts"`.             |
| `config`             | PyScript configuration dictionary.                                         |
| `data`               | Dictionary containing data to pass to the Python function.                 |
| `add_script`         | List of additional JavaScript file URLs.                                   |
| `add_module`         | List of additional JavaScript module URLs.                                 |
| `add_css`            | List of additional CSS file URLs.                                          |
| `add_dangerous_html` | Additional raw HTML inserted into the iframe body.                         |
| `terminal`           | Enable PyScript terminal output. Default: `False`.                         |
| `pys_version`        | PyScript release version. Default: `"2026.7.3"`.                           |
| `pys_type`           | PyScript type: `"mpy"`, `"py"`, or `"py-game"`.                            |

**Returns**

`marimo.Html`

An HTML object containing an iframe with the generated PyScript execution environment.

## How It Works

When you pass a Python function to `run_pyscript()`, the package performs the following operations:

1. Extracts the function's source code using `inspect.getsource()`.
2. Normalizes indentation using `textwrap.dedent()`.
3. Appends an automatically generated script that invokes the asynchronous function.
4. Encodes the resulting Python source code in Base64.
5. Generates an HTML document containing the PyScript runtime and encoded source code.
6. Embeds the document into an iframe using `srcdoc`.
7. Returns the iframe as a `marimo.Html` object.

The Python function executes in the browser-side PyScript runtime, not in marimo's Python interpreter.

### Why the URL monkey patch is necessary

PyScript uses polyscript internally to resolve relative URLs.

When PyScript is embedded inside an iframe using `srcdoc`, the iframe's `location.href` is `about:srcdoc`.

This can cause polyscript's relative URL resolution to fail during initialization because `about:srcdoc` cannot be used as the base URL for resolving ordinary relative resource paths.

To work around this issue, marimo-pys patches the JavaScript `URL` class before loading PyScript's `core.js`.

The patch replaces empty or `about:` base URLs with the PyScript release URL.

A simplified version of the implementation:

```javascript
const NativeURL = window.URL;

class PatchedURL extends NativeURL {
  constructor(url, base) {
    const b = base == null ? '' : String(base);

    if (b === '' || b.startsWith('about:')) {
      base = 'https://pyscript.net/releases/2026.7.3/';
    }

    super(url, base);
  }
}

window.URL = PatchedURL;
```

This workaround has been verified against PyScript `2026.7.3`.

Because it modifies the global `URL` constructor inside the iframe, it may also affect other code that creates URLs in that environment.

The workaround may need to be reviewed or removed when upgrading PyScript.

## Limitations and Considerations

### Separate execution environments

marimo and PyScript use separate Python environments.

The function's source code is transferred to PyScript, but its surrounding module, global variables, imported modules, and closure variables are not transferred automatically.

Use the `data` argument to pass values explicitly.

### Asynchronous functions are required

When passing a callable, it must be a coroutine function defined using `async def`.

Regular synchronous functions are not supported as callable inputs.

Raw source code strings are handled separately and do not have this requirement.

### Source code must be available

The package uses `inspect.getsource()` to extract the function's source code.

Functions whose source code cannot be retrieved may not work.

Decorated functions are not supported.

### iframe isolation

PyScript executes inside a sandboxed iframe.

The default sandbox setting is:

```text
allow-scripts
```

This allows script execution while maintaining iframe sandbox restrictions.

Access to the parent document and other browser capabilities may be restricted by the sandbox configuration.

Changing `iframe_sandbox` can affect the security and isolation of the embedded content.

### Raw HTML and external resources

The `add_dangerous_html` parameter inserts raw HTML without sanitization.

Only provide trusted HTML content.

Similarly, additional JavaScript and CSS resources should come from trusted sources.

### PyScript compatibility

The URL resolution workaround is designed for the PyScript version used by this package.

When changing `pys_version`, verify that PyScript initializes and executes correctly.

## Links

* [PyPI — marimo-pys](https://pypi.org/project/marimo-pys/)
* [GitHub — marimo-pys](https://github.com/uniras/marimo_pys)
* [marimo Documentation](https://docs.marimo.io/)
* [PyScript Documentation](https://docs.pyscript.net/)
