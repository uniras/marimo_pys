import inspect
import textwrap
import html
import json
import base64

from typing import Callable, Optional, Union, Any

import marimo as mo
from anywidget import AnyWidget
import traitlets


def __create_html(
    code: Union[Callable, str],
    body_style: str = '',
    config: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    add_script: Optional[list[str]] = None,
    add_module: Optional[list[str]] = None,
    add_css: Optional[list[str]] = None,
    add_dangerous_html: str = '',
    terminal: bool = False,
    pys_version: str = '2026.7.3',
    pys_type: str = 'mpy',
) -> str:

    # Set default values for optional parameters
    config = config or {}
    data = data or {}
    add_script = add_script or []
    add_module = add_module or []
    add_css = add_css or []

    # Validate the input function and extract its source code
    if callable(code):
        # Validate that the function has a valid name
        func_name: Optional[str] = getattr(code, '__name__', None)
        if not func_name or not func_name.isidentifier():
            raise ValueError('Provided function must have a valid name.')

        # Validate that the function is a coroutine function
        if not inspect.iscoroutinefunction(code):
          raise TypeError(f'{func_name!r} must be an async function;\ndeclare it as async def {func_name!r}(js, data).')

        # Extract function source code as a string and normalize it by left-justifying it
        clean_source = textwrap.dedent(inspect.getsource(code))

        execute_script = f'''{clean_source}

import js
import json

js.window.parent.postMessage('marimo-pys:ready', '*')
await {func_name}(js, json.loads(js.JSON.stringify(js.globalThis.pys_data)))
'''
    elif isinstance(code, str):
        # If func is a string, treat it as raw source code
        execute_script = code
    else:
        raise TypeError('code must be either a callable or a string representing the source code.')

    # Encode the script in base64 for embedding in the HTML
    b64_script = base64.b64encode(execute_script.encode()).decode()

    # Convert config dictionaries to JSON
    if isinstance(config, dict):
        config_json = html.escape(json.dumps(config, allow_nan=False, ensure_ascii=False, separators=(',', ':')))
    else:
        raise TypeError('data must be a dictionary.')

    # Convert data dictionaries to JSON
    if isinstance(data, dict):
        data_json = json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    else:
        raise TypeError('data must be a dictionary.')

    # Include additional scripts, modules, and CSS
    script_includes = '\n' + '\n'.join([f'<script type="text/javascript" src="{html.escape(script)}"></script>' for script in add_script]) if len(add_script) > 0 else ''
    module_includes = '\n' + '\n'.join([f'<script type="module" src="{html.escape(module)}"></script>' for module in add_module]) if len(add_module) > 0 else ''
    css_includes = '\n' + '\n'.join([f'<link rel="stylesheet" href="{html.escape(css)}" />' for css in add_css]) if len(add_css) > 0 else ''

    # Add attribute if terminal output is enabled in PyScript
    terminal_attr = ' terminal' if terminal else ''

    # Checking the PyScript type
    if pys_type not in ('py', 'mpy', 'py-game'):
        raise ValueError("Invalid pys_type. Must be one of 'mpy', 'py', or 'py-game'.")

    # Assemble the HTML template (CSS {} etc. are doubled for escaping in f-string)
    return f'''
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script>
    // Set the data JSON as a global variable
    globalThis.pys_data = {data_json};

    // polyscript's relative_url defaults its base to location.href:
    //   P = (e, t = location.href) => new URL(e, t.replace(/^blob:/, "")).href
    // Inside an <iframe srcdoc>, location.href is "about:srcdoc", so config
    // resolution (a non-URL config falls back to "./config.txt") throws a
    // TypeError, define() fails, and PyScript never boots.
    // The replace() above already strips "blob:", but "about:" is not handled.
    // Patching URL before core.js loads is the only hook available:
    // <base href> has no effect (the base comes from location.href, not baseURI),
    // On PyScript upgrades, drop this patch and re-test. Verified against 2026.7.3.
    const NativeURL = window.URL;
    class PatchedURL extends NativeURL {{
      constructor(url, base) {{
        const b = base == null ? '' : String(base);
        if (b === '' || b.startsWith('about:')) {{
          base = 'https://pyscript.net/releases/{pys_version}/';
        }}
        super(url, base);
      }}
    }}
    window.URL = PatchedURL;
  </script>
  <link rel="stylesheet" href="https://pyscript.net/releases/{pys_version}/core.css" />{css_includes}{script_includes}
  <script type="module" src="https://pyscript.net/releases/{pys_version}/core.js"></script>{module_includes}
</head>
<body style="margin: 0; {html.escape(body_style)}">
  {add_dangerous_html}
  <script type="{pys_type}" config="{config_json}" src="data:text/python;charset=utf-8;base64,{b64_script}"{terminal_attr}></script>
</body>
</html>
    '''



class PysWidget(AnyWidget):
    """A PyScript iframe with last-value-wins, bidirectional state sync.

    ``data`` is both the initial run_pyscript() argument and the initial
    outgoing state. ``set_data()`` updates the latter without reloading the iframe.
    The browser waits for an automatic ready signal before sending that state.
    """

    _esm = r'''
function render({ model, el }) {
  const iframe = document.createElement('iframe');
  iframe.setAttribute("sandbox", model.get('iframe_sandbox'));
  iframe.setAttribute("width", model.get('width'));
  iframe.setAttribute("height", model.get('height'));
  iframe.setAttribute("style", model.get('iframe_style'));

  let ready = false;
  let disposed = false;

  function sendLatest() {
    if (!ready || disposed || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage({
      channel: 'marimo-pys',
      type: 'update',
      payload: model.get('data'),
    }, '*');
  }

  function receive(event) {
    // Never accept a message from another PysWidget's iframe.
    if (event.source !== iframe.contentWindow) return;
    if (event.origin !== window.location.origin && event.origin !== 'null') return;

    if (event.data === 'marimo-pys:ready') {
      ready = true;
      sendLatest();
      return;
    }

    const message = event.data;
    if (!message || typeof message !== 'object' ||
        message.channel !== 'marimo-pys' || message.type !== 'set') return;

    const payload = message.payload;
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return;

    // Keep the synced trait JSON-compatible; reject malformed/non-serializable data.
    try {
      const normalized = JSON.parse(JSON.stringify(payload));
      if (!normalized || Array.isArray(normalized) ||
          typeof normalized !== 'object') return;
      model.set('received', normalized);
      model.save_changes();
    } catch (error) {
      console.warn('marimo-pys: rejected message payload', error);
    }
  }

  window.addEventListener('message', receive);
  model.on('change:data', sendLatest);
  el.appendChild(iframe);

  // Set srcdoc only once: data updates never restart the PyScript runtime.
  iframe.srcdoc = model.get('srcdoc');

  return () => {
    disposed = true;
    window.removeEventListener('message', receive);
    model.off('change:data', sendLatest);
    iframe.remove();
  };
}

export default { render };
'''

    srcdoc = traitlets.Unicode('').tag(sync=True)
    width = traitlets.Unicode('100%').tag(sync=True)
    height = traitlets.Unicode('200px').tag(sync=True)
    iframe_style = traitlets.Unicode('').tag(sync=True)
    iframe_sandbox = traitlets.Unicode('allow-scripts').tag(sync=True)
    data = traitlets.Dict(default_value={}).tag(sync=True)
    received = traitlets.Dict(default_value={}).tag(sync=True)

    def __init__(
        self,
        html_data: str,
        width: str,
        height: str,
        iframe_style: str,
        iframe_sandbox: str,
        data: dict[str, Any]
    ) -> None:
        data = data or {}
        super().__init__(
            srcdoc=html_data,
            width=width,
            height=height,
            iframe_style=iframe_style,
            iframe_sandbox=iframe_sandbox,
            data=data,
            received={}
        )

    def set_data(self, data: dict[str, Any]) -> None:
        """Synchronize the latest state, without waiting for PyScript readiness."""
        if isinstance(data, dict):
            self.data = data
        else:
            raise('data must be a dictionary.')


def run_pyscript(
    code: Union[Callable, str],
    width: str = '100%',
    height: str = '200px',
    body_style: str = '',
    iframe_style: str = '',
    iframe_sandbox: str = 'allow-scripts',
    config: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    add_script: Optional[list[str]] = None,
    add_module: Optional[list[str]] = None,
    add_css: Optional[list[str]] = None,
    add_dangerous_html: str = '',
    terminal: bool = False,
    pys_version: str = '2026.7.3',
    pys_type: str = 'mpy',
    widget: bool = False
) -> Union[mo.Html, PysWidget]:
    """
    Generates HTML to execute the specified Python function as a PyScript and returns it as an Marimo iframe.

    Args:
        code (Union[Callable, str]): The async function or raw source code to be executed.
            A callable must be a coroutine function; it is awaited in the browser as
            ``await code(js, data)``, where ``js`` is the PyScript ``js`` module and
            ``data`` is the ``data`` argument decoded back into a plain Python object.
            Only the function's own source is transferred: it runs in a fresh
            interpreter with no access to the surrounding module's imports, globals or
            closure variables, so every import must happen inside the function body.
            Decorators are not supported.
        width (str): Width of the iframe. Default is '100%'.
        height (str): Height of the iframe. Default is '200px'.
        body_style (str): Additional CSS styles for the body. Default is ''.
        iframe_style (str): Additional CSS styles for the iframe. Default is ''.
        iframe_sandbox (str): Sandbox attributes for the iframe. Default is 'allow-scripts'.
        config (Optional[dict[str, Any]]): Configuration dictionary for PyScript. Default is None.
        data (Optional[dict[str, Any]]): Data dictionary to be passed to the function. Default is None.
        add_script (Optional[list[str]]): List of additional JavaScript files to include. Default is None.
        add_module (Optional[list[str]]): List of additional JavaScript modules to include. Default is None.
        add_css (Optional[list[str]]): List of additional CSS files to include. Default is None.
        add_dangerous_html (str): Additional HTML content to include in the body. note: This can be dangerous if it includes untrusted content. Default is ''.
        terminal (bool): Whether to enable terminal output in PyScript. Default is False.
        pys_version (str): Version of PyScript to use. Default is '2026.7.3'.
        pys_type (str): Type of PyScript to use. Default is 'mpy'.
        widget (bool): Specifies whether to generate a dedicated widget for bidirectional communication; if False, an iframe is generated within mo.Html. Default is False.

    Returns:
        Union[mo.Html, PysWidget]: An HTML object containing the iframe with the PyScript execution, or a PysWidget if `widget` is True.
    """

    html_data = __create_html(code, body_style, config, data, add_script, add_module, add_css, add_dangerous_html, terminal, pys_version, pys_type)
 
    if widget:
        return PysWidget(html_data, width, height, iframe_style, iframe_sandbox, data or {})
    else:
        # Wrap in an iframe and return
        return mo.Html(f'<iframe srcdoc="{html.escape(html_data)}" width="{html.escape(width)}" height="{html.escape(height)}" style="{html.escape(iframe_style)}" sandbox="{html.escape(iframe_sandbox)}"></iframe>')
