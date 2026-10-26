from unittest.mock import MagicMock, patch

from langchain_ventaw import VentawToolkit


def resp(status, body):
    r = MagicMock(status_code=status, content=b"x")
    r.json.return_value = body
    return r


def test_tools():
    tk = VentawToolkit(api_key="k", wait_timeout=5)
    tools = {t.name: t for t in tk.get_tools()}
    assert "delete_database" not in tools
    assert "delete_database" in {t.name for t in VentawToolkit(api_key="k", include_delete=True).get_tools()}
    assert set(tools["create_database"].args) == {"name", "engine"}

    with patch("requests.request", side_effect=[
        resp(201, {"id": "d1", "state": "starting"}),
        resp(200, {"id": "d1", "state": "starting"}),
        resp(200, {"id": "d1", "name": "db", "engine": "postgres", "state": "running", "connection_string": "pg://"}),
    ]) as req, patch("time.sleep"):
        out = tools["create_database"].invoke({"name": "db"})
    assert out["connection_string"] == "pg://"
    assert req.call_args_list[0].kwargs["json"] == {"name": "db", "engine": "postgres"}

    # API errors reach the agent as text instead of crashing it
    with patch("requests.request", return_value=resp(402, {"detail": "Balance too low"})):
        assert "Balance too low" in tools["create_sandbox"].invoke({"template": "py312", "name": "x"})

    with patch("requests.request", return_value=resp(200, {"ok": False, "output": "syntax error"})):
        assert tools["run_sql"].invoke({"database_id": "d1", "sql": "selec"}) == "syntax error"
