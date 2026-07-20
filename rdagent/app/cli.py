"""
CLI entrance for all rdagent application.

This will
- make rdagent a nice entry and
- autoamtically load dotenv
"""

import sys

from dotenv import load_dotenv

load_dotenv(".env")
# 1) Make sure it is at the beginning of the script so that it will load dotenv before initializing BaseSettings.
# 2) The ".env" argument is necessary to make sure it loads `.env` from the current directory.

import subprocess
from importlib.resources import path as rpath
from typing import Optional

import typer
from typing_extensions import Annotated

from rdagent.app.qlib_rd_loop.factor import main as fin_factor
from rdagent.app.qlib_rd_loop.factor_from_report import main as fin_factor_report
from rdagent.app.qlib_rd_loop.model import main as fin_model
from rdagent.app.qlib_rd_loop.quant import main as fin_quant
from rdagent.app.utils.health_check import health_check
from rdagent.app.utils.info import collect_info

app = typer.Typer()

CheckoutOption = Annotated[bool, typer.Option("--checkout/--no-checkout", "-c/-C")]
CheckEnvOption = Annotated[bool, typer.Option("--check-env/--no-check-env", "-e/-E")]
CheckDockerOption = Annotated[bool, typer.Option("--check-docker/--no-check-docker", "-d/-D")]
CheckPortsOption = Annotated[bool, typer.Option("--check-ports/--no-check-ports", "-p/-P")]


def ui(port=19899, log_dir="", debug: bool = False):
    """
    start web app to show the log traces.
    """
    with rpath("rdagent.log.ui", "app.py") as app_path:
        cmds = ["streamlit", "run", app_path, f"--server.port={port}"]
        if log_dir or debug:
            cmds.append("--")
        if log_dir:
            cmds.append(f"--log_dir={log_dir}")
        if debug:
            cmds.append("--debug")
        subprocess.run(cmds)


def server_ui(port=19899):
    """
    start the Flask log server in real time
    """
    from rdagent.log.server.app import main as log_server_main

    log_server_main(port=port)


@app.command(name="fin_factor")
def fin_factor_cli(
    path: Optional[str] = None,
    step_n: Optional[int] = None,
    loop_n: Optional[int] = None,
    all_duration: Optional[str] = None,
    checkout: CheckoutOption = True,
):
    fin_factor(path=path, step_n=step_n, loop_n=loop_n, all_duration=all_duration, checkout=checkout)


@app.command(name="fin_model")
def fin_model_cli(
    path: Optional[str] = None,
    step_n: Optional[int] = None,
    loop_n: Optional[int] = None,
    all_duration: Optional[str] = None,
    checkout: CheckoutOption = True,
):
    fin_model(path=path, step_n=step_n, loop_n=loop_n, all_duration=all_duration, checkout=checkout)


@app.command(name="fin_quant")
def fin_quant_cli(
    path: Optional[str] = None,
    step_n: Optional[int] = None,
    loop_n: Optional[int] = None,
    all_duration: Optional[str] = None,
    checkout: CheckoutOption = True,
):
    fin_quant(path=path, step_n=step_n, loop_n=loop_n, all_duration=all_duration, checkout=checkout)


@app.command(name="fin_factor_report")
def fin_factor_report_cli(
    report_folder: Optional[str] = None,
    path: Optional[str] = None,
    all_duration: Optional[str] = None,
    checkout: CheckoutOption = True,
):
    fin_factor_report(report_folder=report_folder, path=path, all_duration=all_duration, checkout=checkout)


app.command(name="ui")(ui)
app.command(name="server_ui")(server_ui)


@app.command(name="health_check")
def health_check_cli(
    check_env: CheckEnvOption = True,
    check_docker: CheckDockerOption = True,
    check_ports: CheckPortsOption = True,
):
    health_check(check_env=check_env, check_docker=check_docker, check_ports=check_ports)


@app.command(name="collect_info")
def collect_info_cli():
    collect_info()


@app.command(name="sota")
def sota_cli(
    log_path: Optional[str] = None,
    trace_name: Optional[str] = None,
    output: str = "json",
):
    """
    Query SOTA (best) experiment artifacts from a LoopBase session.

    Specify either --log-path (direct session path) or --trace-name (scan log/).
    Output format: json (default) | table | code (factor/model code only).
    """
    import json as json_mod

    from rdagent.log.sota_query import find_session_by_trace_name, query_sota

    if log_path is None and trace_name is None:
        typer.echo("Error: must specify --log-path or --trace-name", err=True)
        raise typer.Exit(1)

    if log_path is None:
        resolved = find_session_by_trace_name(trace_name)
        if resolved is None:
            typer.echo(f"Error: no session matching trace '{trace_name}' in log/", err=True)
            raise typer.Exit(1)
        log_path = str(resolved)

    result = query_sota(log_path)

    if "error" in result:
        typer.echo(f"Error: {result['error']} — {result.get('detail', '')}", err=True)
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json_mod.dumps(result, indent=2, default=str, ensure_ascii=False))
    elif output == "code":
        for f in result.get("sota_factors", []):
            typer.echo(f"--- Factor: {f.get('name', '?')} ---")
            typer.echo(f.get("code", "(no code)"))
        model = result.get("sota_model")
        if model:
            typer.echo(f"--- Model: {model.get('name', '?')} ---")
            typer.echo(model.get("code", "(no code)"))
    else:
        # table format
        typer.echo(f"SOTA Loop ID:    {result.get('sota_loop_id', '?')}")
        typer.echo(f"Experiments:     {result.get('total_experiments', '?')}")
        hyp = result.get("sota_hypothesis", {})
        typer.echo(f"Hypothesis:      {hyp.get('hypothesis', '?')[:80]}...")
        typer.echo(f"Decision:        {result.get('sota_feedback', {}).get('decision', '?')}")
        typer.echo("\nMetrics:")
        for k, v in result.get("sota_metrics", {}).items():
            typer.echo(f"  {k}: {v}")
        for f in result.get("sota_factors", []):
            typer.echo(f"\nFactor: {f.get('name', '?')} — {f.get('description', '?')[:60]}")
            typer.echo(f"  workspace: {f.get('workspace_path', '?')}")
        model = result.get("sota_model")
        if model:
            typer.echo(f"\nModel: {model.get('name', '?')} ({model.get('model_type', '?')})")
            typer.echo(f"  workspace: {model.get('workspace_path', '?')}")


if __name__ == "__main__":
    app()
