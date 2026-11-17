"""MCP stdio tools backed by the same Spectra Harness used in Python."""


def create_server():
    """Create the OpenMolSpec MCP server and register its spectroscopy tools.

    Returns
    -------
    mcp.server.MCPServer
        Server exposing ``spectra_tasks``, ``spectra_datasets``,
        ``spectra_validate`` and ``spectra_predict``. Prediction and validation
        tools take ``task``, ``inputs`` and ``model_settings``; prediction also
        accepts ``repeats``.

    Raises
    ------
    RuntimeError
        If the optional MCP dependency is absent.

    Examples
    --------
    >>> server = create_server()
    >>> server.run(transport='stdio')
    """
    try:
        from mcp.server import MCPServer
    except ImportError as error:
        raise RuntimeError('Install the MCP extra: pip install "openmolspec[mcp]"') from error
    from .harness import SpectraHarness
    from .dataset import list_datasets,dataset_info
    server=MCPServer('OpenMolSpec v1.0',version='1.0')
    harness=SpectraHarness()

    @server.tool()
    def spectra_tasks() -> list[dict]:
        """List direct NMR, MS and vibrational tasks and input modalities."""
        return harness.catalog()

    @server.tool()
    def spectra_datasets(name: str = '') -> list[dict] | dict:
        """Read versioned dataset metadata without downloading data or weights."""
        return dataset_info(name) if name else list_datasets()

    @server.tool()
    def spectra_validate(task: str, inputs: dict, model_settings: dict) -> dict:
        """Validate a spectroscopy request before any model call."""
        try:return harness.validate(task,inputs,model_settings)
        except ValueError as error:return {'valid':False,'task':task,'error':str(error)}

    @server.tool()
    def spectra_predict(task: str, inputs: dict, model_settings: dict, repeats: int = 1) -> dict:
        """Run an explicit frozen model request and return result plus execution trace."""
        return harness.run(task,inputs,model_settings,repeats=repeats)

    return server


def main():
    """Start the ``openmolspec-mcp`` stdio service."""
    create_server().run(transport='stdio')


if __name__=='__main__':main()
