"""OpenMob command-line interface."""

import typer

from openmob import server

app = typer.Typer(help="OpenMob engine: control mobile devices from your machine.")


@app.command()
def serve(port: int = typer.Option(server.PORT, help="Port to listen on.")) -> None:
    """Start the HTTP/WebSocket API server."""
    server.serve(port=port)


@app.command()
def mcp() -> None:
    """Start the MCP stdio server for AI agents."""
    from openmob import mcp_server

    mcp_server.run()


@app.command()
def devices() -> None:
    """Print detected devices."""
    from openmob.manager import DeviceManager

    found = DeviceManager().refresh()
    if not found:
        typer.echo("No devices found.")
        return
    for device in found:
        size = ""
        if device.status == "online":
            try:
                size = f"  {device.width}x{device.height}"
            except Exception:
                pass
        typer.echo(f"{device.id}  {device.platform}  {device.status}  {device.name}{size}")


def main() -> None:
    app()
