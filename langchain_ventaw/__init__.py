"""LangChain tools for creating and using Ventaw sandboxes and databases."""
import os
import time
from typing import Dict, List, Literal, Optional

import requests
from langchain_core.tools import BaseTool, BaseToolkit, StructuredTool, ToolException
from pydantic import ConfigDict, Field

__all__ = ["VentawToolkit"]


class VentawToolkit(BaseToolkit):
    """Tools that let an agent create and use Ventaw sandboxes and databases.

    Delete tools are left out unless include_delete=True, because deleting a database deletes its data.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: Optional[str] = Field(default=None, repr=False)
    api_base: str = "https://api.ventaw.com/v1"
    include_delete: bool = False
    wait_timeout: float = 180

    def _request(self, method: str, path: str, **kwargs):
        key = self.api_key or os.environ.get("VENTAW_API_KEY")
        if not key:
            raise ToolException("No Ventaw API key. Set VENTAW_API_KEY or pass api_key.")
        try:
            r = requests.request(method, f"{self.api_base.rstrip('/')}{path}",
                                 headers={"Authorization": f"Bearer {key}"}, timeout=60, **kwargs)
        except requests.RequestException as e:
            raise ToolException(f"Could not reach Ventaw: {e}")
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise ToolException(f"Ventaw returned {r.status_code}: {detail}")
        return r.json() if r.content else None

    def _wait_running(self, path: str) -> dict:
        deadline = time.monotonic() + self.wait_timeout
        while True:
            obj = self._request("GET", path)
            if obj["state"] == "running":
                return obj
            if obj["state"] == "error" or time.monotonic() > deadline:
                raise ToolException(f"{path} is {obj['state']}, not running")
            time.sleep(2)

    def get_tools(self) -> List[BaseTool]:
        req = self._request

        def list_templates() -> list:
            """List the templates a sandbox can be created from (e.g. nextjs, fastapi, django, py312)."""
            return [{"code": t.get("code"), "name": t.get("name"), "description": t.get("description")}
                    for t in req("GET", "/templates")]

        def create_sandbox(template: str, name: str, env_vars: Optional[Dict[str, str]] = None,
                           internet_enabled: Optional[bool] = None) -> dict:
            """Create a sandbox (a small Linux microVM) from a template code and wait until it is running.
            Returns its id and access_url (public URL of the app it serves)."""
            payload = {"template_id": template, "name": name, "env_vars": env_vars,
                       "internet_enabled": internet_enabled}
            sb = req("POST", "/sandboxes", json={k: v for k, v in payload.items() if v is not None})
            sb = self._wait_running(f"/sandboxes/{sb['id']}")
            return {k: sb.get(k) for k in ("id", "name", "template_id", "state", "access_url", "private_host")}

        def list_sandboxes() -> list:
            """List your sandboxes with their id, name, state and access_url."""
            return [{k: s.get(k) for k in ("id", "name", "template_id", "state", "access_url")}
                    for s in req("GET", "/sandboxes")]

        def execute_command(sandbox_id: str, command: str,
                            language: Literal["bash", "python"] = "bash") -> dict:
            """Run a bash command (or a Python script with language="python") in a running sandbox.
            Runs as root in the workspace directory; at most 30 seconds. Returns stdout, stderr, exit_code."""
            return req("POST", f"/sandboxes/{sandbox_id}/execute", json={"code": command, "language": language})

        def write_file(sandbox_id: str, path: str, content: str) -> str:
            """Write a text file in the sandbox workspace, creating parent directories."""
            req("POST", f"/sandboxes/{sandbox_id}/files/write",
                json={"path": path, "content": content, "encoding": "utf-8", "create_dirs": True})
            return f"Wrote {path}"

        def read_file(sandbox_id: str, path: str) -> str:
            """Read a text file from the sandbox workspace."""
            return req("GET", f"/sandboxes/{sandbox_id}/files/content", params={"path": path})["content"]

        def create_database(name: str, engine: Literal["postgres", "valkey"] = "postgres") -> dict:
            """Create a PostgreSQL or Valkey (Redis-compatible) database and wait until it accepts connections.
            Returns its id and connection_string, which works from your sandboxes (not the public internet)."""
            db = req("POST", "/databases", json={"name": name, "engine": engine})
            db = self._wait_running(f"/databases/{db['id']}")
            return {k: db.get(k) for k in ("id", "name", "engine", "state", "connection_string")}

        def list_databases() -> list:
            """List your databases with their id, engine, state and connection_string."""
            return [{k: d.get(k) for k in ("id", "name", "engine", "state", "connection_string")}
                    for d in req("GET", "/databases")]

        def run_sql(database_id: str, sql: str) -> str:
            """Run SQL on a PostgreSQL database and return what psql printed. Statements stop at the first error."""
            res = req("POST", f"/databases/{database_id}/query", json={"sql": sql})
            if not res["ok"]:
                raise ToolException(res["output"])
            return res["output"]

        def delete_sandbox(sandbox_id: str) -> str:
            """Stop and delete a sandbox and its files."""
            req("DELETE", f"/sandboxes/{sandbox_id}")
            return f"Deleted sandbox {sandbox_id}"

        def delete_database(database_id: str) -> str:
            """Stop and delete a database, including all its data. This cannot be undone."""
            req("DELETE", f"/databases/{database_id}")
            return f"Deleted database {database_id}"

        fns = [list_templates, create_sandbox, list_sandboxes, execute_command, write_file, read_file,
               create_database, list_databases, run_sql]
        if self.include_delete:
            fns += [delete_sandbox, delete_database]
        return [StructuredTool.from_function(f, handle_tool_error=True) for f in fns]
