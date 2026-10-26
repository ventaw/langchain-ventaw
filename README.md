# langchain-ventaw

LangChain tools that let an agent create and use Ventaw sandboxes and databases.

```bash
pip install langchain-ventaw
export VENTAW_API_KEY=...
```

```python
from langchain_ventaw import VentawToolkit
from langgraph.prebuilt import create_react_agent

tools = VentawToolkit().get_tools()
agent = create_react_agent("anthropic:claude-sonnet-5-5", tools)
agent.invoke({"messages": [("user", "Make a FastAPI sandbox that serves /hello, and a Postgres database for it.")]})
```

## Tools

| Tool | What it does |
|---|---|
| `list_templates` | Templates a sandbox can start from |
| `create_sandbox` | Create a sandbox and wait until it is running |
| `list_sandboxes` | Your sandboxes |
| `execute_command` | Run a command in a sandbox (up to 30 seconds) |
| `write_file` / `read_file` | Write or read a file in the sandbox workspace |
| `create_database` | Create a PostgreSQL or Valkey database and wait until it is ready |
| `list_databases` | Your databases and their connection strings |
| `run_sql` | Run SQL on a PostgreSQL database |
| `delete_sandbox` / `delete_database` | Only with `VentawToolkit(include_delete=True)` |

Deleting a database deletes its data, so the delete tools are off unless you turn them on.

Options: `api_key` (defaults to `VENTAW_API_KEY`), `api_base`, `wait_timeout` (seconds to wait for a sandbox or database to start, default 180).
